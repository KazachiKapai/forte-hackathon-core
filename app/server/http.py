from typing import Dict, Optional, List
from fastapi import FastAPI, Header, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from collections import deque
import os
import re
import urllib.parse

from ..webhook import WebhookProcessor
from ..infra.task_executor import get_shared_executor
from ..infra.dedupe import get_dedupe_store
from ..infra.ipfilter import get_effective_allowlist, is_ip_allowed
from ..infra.ratelimit import get_rate_limiter
from ..infra.cooldown import get_cooldown_store
from ..config.logging_config import configure_logging
from ..auth import router as auth_router
from ..tokens import router as tokens_router
from ..repos import router as repos_router

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


def _get_frontend_origins() -> List[str]:
	raw = os.environ.get("FRONTEND_URL", "http://localhost:3000") or "http://localhost:3000"
	# Support comma-separated list
	parts = [p.strip() for p in raw.split(",") if p.strip()]
	if not parts:
		parts = ["http://localhost:3000"]
	origins = [_normalize_origin(p) for p in parts]
	# Deduplicate while preserving order
	seen = set()
	out: List[str] = []
	for o in origins:
		if o not in seen:
			seen.add(o)
			out.append(o)
	return out


_FRONTEND_ORIGINS = _get_frontend_origins()


def _record_event_uuid(event_uuid: Optional[str]) -> bool:
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


def create_app(processor: WebhookProcessor) -> FastAPI:
	app = FastAPI()
	app.add_middleware(
		CORSMiddleware,
		allow_origins=_FRONTEND_ORIGINS,
		allow_credentials=True,
		allow_methods=["*"],
		allow_headers=["*"],
	)

	@app.get("/health")
	async def health() -> Dict[str, str]:
		return {"status": "ok"}

	# Mount feature routers
	app.include_router(auth_router)
	app.include_router(tokens_router)
	app.include_router(repos_router)

	@app.post("/gitlab/webhook")
	async def gitlab_webhook(
		request: Request,
		background_tasks: BackgroundTasks,
		x_gitlab_event: Optional[str] = Header(default=None, alias="X-Gitlab-Event"),
		x_gitlab_token: Optional[str] = Header(default=None, alias="X-Gitlab-Token"),
		x_gitlab_event_uuid: Optional[str] = Header(default=None, alias="X-Gitlab-Event-UUID"),
	) -> JSONResponse:
		# Determine client IP (optionally trusting proxy headers)
		trust_proxy = (os.environ.get("TRUST_PROXY", "false") or "false").lower() in {"1", "true", "yes"}
		client_ip = getattr(request.client, "host", None)
		if trust_proxy:
			fwd = request.headers.get("X-Forwarded-For")
			if fwd:
				# Take the left-most IP
				first = fwd.split(",")[0].strip()
				# Basic sanity check for IPv4/IPv6 literal
				if re.match(r"^[0-9a-fA-F\.:]+$", first):
					client_ip = first
		# IP allowlist check (if configured)
		allowlist = get_effective_allowlist()
		if allowlist and not is_ip_allowed(client_ip, allowlist):
			_LOGGER.warning("IP not allowed", extra={"client_ip": client_ip})
			raise HTTPException(status_code=403, detail="Forbidden")
		# Rate limiting per IP
		rl = get_rate_limiter()
		if client_ip and not rl.allow(client_ip):
			_LOGGER.warning("Rate limit exceeded", extra={"client_ip": client_ip})
			raise HTTPException(status_code=429, detail="Too Many Requests")
		try:
			processor.validate_secret(x_gitlab_token)
		except PermissionError:
			raise HTTPException(status_code=401, detail="Invalid webhook token")
		if x_gitlab_event != "Merge Request Hook":
			return JSONResponse({"status": "ignored", "reason": "unsupported_event"}, status_code=202)

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
		commit_sha = (attrs.get("last_commit") or {}).get("id") if isinstance(attrs.get("last_commit"), dict) else None
		updated_at = attrs.get("updated_at") or ""
		action = attrs.get("action") or ""
		idempotency_key = x_gitlab_event_uuid or f"{project_id}:{mr_iid}:{commit_sha or updated_at}:{action}"
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


