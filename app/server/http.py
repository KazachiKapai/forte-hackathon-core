import os
import re
import urllib.parse
from collections import deque

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..auth.middleware import get_auth
from ..auth import router as auth_router
from ..config.logging_config import configure_logging
from ..infra.cooldown import get_cooldown_store
from ..infra.dedupe import get_dedupe_store
from ..infra.ipfilter import get_effective_allowlist, is_ip_allowed
from ..infra.ratelimit import get_rate_limiter
from ..infra.task_executor import get_shared_executor
from ..repos import router as repos_router
from ..tokens import router as tokens_router
from ..webhook import WebhookProcessor

_LOGGER = configure_logging()

_SEEN_EVENT_MAX = 1024
_seen_event_ids = deque(maxlen=_SEEN_EVENT_MAX)
_seen_event_set = set()


def _normalize_origin(url: str) -> str:
	"""
	Extract scheme://host[:port] and strip trailing slash.
	Falls back to the raw value if parsing fails.
	"""
	try:
		parsed = urllib.parse.urlparse(url.strip())
		if parsed.scheme and parsed.netloc:
			return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
	except Exception:
		pass
	return url.rstrip("/")


def _get_frontend_origins() -> list[str]:
	raw = os.environ.get("FRONTEND_URL", "http://localhost:3000") or "http://localhost:3000"
	# Support comma-separated list
	parts = [p.strip() for p in raw.split(",") if p.strip()]
	if not parts:
		parts = ["http://localhost:3000"]
	origins = [_normalize_origin(p) for p in parts]
	# Deduplicate while preserving order
	seen = set()
	out: list[str] = []
	for o in origins:
		if o not in seen:
			seen.add(o)
			out.append(o)
	return out


_FRONTEND_ORIGINS = _get_frontend_origins()


def _record_event_uuid(event_uuid: str | None) -> bool:
	if not event_uuid:
		return False
	dup = event_uuid in _seen_event_set
	if not dup:
		_seen_event_ids.append(event_uuid)
		_seen_event_set.add(event_uuid)
		if len(_seen_event_ids) == _SEEN_EVENT_MAX:
			_seen_event_set.clear()
			_seen_event_set.update(_seen_event_ids)
	return dup


def _determine_client_ip(request: Request, trust_proxy: bool) -> str | None:
	client_ip = getattr(request.client, "host", None)
	if not trust_proxy:
		return client_ip
	fwd = request.headers.get("X-Forwarded-For")
	if not fwd:
		return client_ip
	first = fwd.split(",")[0].strip()
	if re.match(r"^[0-9a-fA-F\.:]+$", first):
		return first
	return client_ip


def _enforce_ip_policies(client_ip: str | None) -> None:
	allowlist = get_effective_allowlist()
	if allowlist and not is_ip_allowed(client_ip, allowlist):
		_LOGGER.warning("IP not allowed", extra={"client_ip": client_ip})
		raise HTTPException(status_code=403, detail="Forbidden")
	rl = get_rate_limiter()
	if client_ip and not rl.allow(client_ip):
		_LOGGER.warning("Rate limit exceeded", extra={"client_ip": client_ip})
		raise HTTPException(status_code=429, detail="Too Many Requests")


def _validate_webhook_headers(processor: WebhookProcessor, x_gitlab_event: str | None, x_gitlab_token: str | None) -> None:
	try:
		processor.validate_secret(x_gitlab_token)
	except PermissionError:
		raise HTTPException(status_code=401, detail="Invalid webhook token")
	if x_gitlab_event != "Merge Request Hook":
		# non-MR events are explicitly ignored
		raise HTTPException(status_code=202, detail="ignored")


def _extract_mr_identifiers(payload: dict[str, any]) -> tuple[int, int, str, str, str | None, str | None]:
	attrs = payload.get("object_attributes", {}) or {}
	project_info = payload.get("project", {}) or {}
	project_id = int(project_info.get("id"))
	mr_iid = int(attrs.get("iid"))
	action = attrs.get("action") or ""
	updated_at = attrs.get("updated_at") or ""
	last_commit = (attrs.get("last_commit") or {}).get("id") if isinstance(attrs.get("last_commit"), dict) else None
	title = attrs.get("title") or ""
	description = attrs.get("description") or ""
	return project_id, mr_iid, action, updated_at, last_commit, title or description


def _compute_idempotency_key(attrs: dict[str, any], project_id: int, mr_iid: int, event_uuid: str | None) -> str:
	commit_sha = (attrs.get("last_commit") or {}).get("id") if isinstance(attrs.get("last_commit"), dict) else None
	updated_at = attrs.get("updated_at") or ""
	action = attrs.get("action") or ""
	return event_uuid or f"{project_id}:{mr_iid}:{commit_sha or updated_at}:{action}"


def create_app(processor: WebhookProcessor) -> FastAPI:
	app = FastAPI()
	app.add_middleware(
		CORSMiddleware,
		allow_origins=_FRONTEND_ORIGINS,
		allow_credentials=True,
		allow_methods=["*"],
		allow_headers=["*"],
	)

	# All routes in this router will be protected by the get_auth dependency
	api_router = APIRouter(dependencies=[Depends(get_auth)])

	@app.get("/health")
	async def health() -> dict[str, str]:
		return {"status": "ok"}

	# Mount feature routers
	api_router.include_router(auth_router)
	api_router.include_router(tokens_router)
	api_router.include_router(repos_router)

	app.include_router(api_router, prefix="/api")

	@app.post("/gitlab/webhook")
	async def gitlab_webhook(
		request: Request,
		background_tasks: BackgroundTasks,
		x_gitlab_event: str | None = Header(default=None, alias="X-Gitlab-Event"),
		x_gitlab_token: str | None = Header(default=None, alias="X-Gitlab-Token"),
		x_gitlab_event_uuid: str | None = Header(default=None, alias="X-Gitlab-Event-UUID"),
	) -> JSONResponse:
		trust_proxy = (os.environ.get("TRUST_PROXY", "false") or "false").lower() in {"1", "true", "yes"}
		client_ip = _determine_client_ip(request, trust_proxy)
		_enforce_ip_policies(client_ip)
		try:
			_validate_webhook_headers(processor, x_gitlab_event, x_gitlab_token)
		except HTTPException as e:
			# 202 with "ignored" should return body per previous behavior
			if e.status_code == 202:
				return JSONResponse({"status": "ignored", "reason": "unsupported_event"}, status_code=202)
			raise

		payload = await request.json()
		attrs = payload.get("object_attributes", {}) or {}
		project_info = payload.get("project", {}) or {}
		project_id = project_info.get("id")
		mr_iid = attrs.get("iid")
		action = attrs.get("action")
		updated_at = attrs.get("updated_at")
		last_commit = (attrs.get("last_commit") or {}).get("id") if isinstance(attrs.get("last_commit"), dict) else None
		client_ip = getattr(request.client, "host", None)

		dup = _record_event_uuid(x_gitlab_event_uuid)
		_LOGGER.info(
			"Webhook received",
			extra={
				"event_uuid": x_gitlab_event_uuid,
				"duplicate": dup,
				"project_id": project_id,
				"mr_iid": mr_iid,
				"action": action,
				"updated_at": updated_at,
				"last_commit": last_commit,
				"client_ip": client_ip,
			},
		)
		# Validate and extract minimal info first
		result = processor.handle_merge_request_event(payload)
		if result.get("status") == "error":
			code = result.get("code", 500)
			raise HTTPException(status_code=code, detail=result.get("message"))
		# Schedule heavy processing asynchronously
		project_id = int(project_id)
		mr_iid = int(mr_iid)
		title = attrs.get("title") or ""
		description = attrs.get("description") or ""
		# Per-MR short cooldown to avoid immediate feedback loops and rapid repeats
		cd = get_cooldown_store()
		cd_key = f"mr:{project_id}:{mr_iid}"
		if not cd.acquire(cd_key):
			_LOGGER.info(
				"Per-MR cooldown active, skipping",
				extra={"project_id": project_id, "mr_iid": mr_iid},
			)
			return JSONResponse({"status": "cooldown_skipped"}, status_code=202)
		# Build idempotency key when Event-UUID not present
		idempotency_key = _compute_idempotency_key(attrs, project_id, mr_iid, x_gitlab_event_uuid)
		dedupe = get_dedupe_store()
		if not dedupe.should_process(idempotency_key):
			_LOGGER.info(
				"Duplicate webhook skipped",
				extra={"event_uuid": x_gitlab_event_uuid, "project_id": project_id, "mr_iid": mr_iid, "action": action},
			)
			return JSONResponse({"status": "duplicate_skipped"}, status_code=202)
		# Use a bounded global executor to avoid unbounded background tasks
		exec_ = get_shared_executor()
		exec_.submit(processor.process_merge_request, project_id, mr_iid, title, description, x_gitlab_event_uuid)
		_LOGGER.info(
			"Processing queued",
			extra={"event_uuid": x_gitlab_event_uuid, "project_id": project_id, "mr_iid": mr_iid, "action": action},
		)
		return JSONResponse({"status": "queued"}, status_code=202)

	return app


