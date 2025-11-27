import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from ..config.logging_config import configure_logging
from ..security.session import clear_session, require_auth, set_session
from ..storage.json_store import load_json, save_json
from . import service as auth_service

_LOGGER = configure_logging()
router = APIRouter()


@router.get("/auth/login")
async def auth_login() -> Response:
	if not (auth_service.OAUTH_CLIENT_ID and auth_service.OAUTH_CLIENT_SECRET):
		raise HTTPException(status_code=500, detail="OAuth not configured")
	state = str(uuid.uuid4())
	states: dict[str, Any] = load_json("oauth_state.json", {})
	states[state] = {"created_at": int(time.time())}
	save_json("oauth_state.json", states)
	return RedirectResponse(auth_service.build_authorize_url(state))


@router.get("/auth/callback")
async def auth_callback(request: Request, code: str | None = None, state: str | None = None) -> Response:
	if not code or not state:
		raise HTTPException(status_code=400, detail="Missing code or state")
	states: dict[str, Any] = load_json("oauth_state.json", {})
	if state not in states:
		raise HTTPException(status_code=400, detail="Invalid state")
	try:
		token_res = auth_service.exchange_code(code)
		access_token = token_res.get("access_token")
		if not access_token:
			raise RuntimeError("No access_token")
		user_raw = auth_service.api_get_user(access_token)
		user = {
			"id": f"gitlab:{user_raw.get('id')}",
			"username": user_raw.get("username"),
			"email": user_raw.get("email"),
			"name": user_raw.get("name"),
			"avatar_url": user_raw.get("avatar_url"),
		}
	except Exception:
		_LOGGER.exception("OAuth callback failed")
		raise HTTPException(status_code=500, detail="OAuth exchange failed")
	users: dict[str, Any] = load_json("users.json", {})
	users[user["id"]] = user
	save_json("users.json", users)
	resp = RedirectResponse(url=auth_service.FRONTEND_URL)
	set_session(resp, user, oauth_token=access_token)  # type: ignore[name-defined]
	tokens: dict[str, list[dict[str, Any]]] = load_json("tokens.json", {})
	user_tokens = tokens.get(user["id"]) or []
	target = "/dashboard" if user_tokens else "/onboarding"
	resp.headers["Location"] = f"{auth_service.FRONTEND_URL}{target}"
	return resp


@router.get("/auth/me")
async def auth_me(request: Request) -> dict[str, Any]:
	sess = require_auth(request)
	return sess.get("user", {})


@router.post("/auth/logout")
async def auth_logout(request: Request) -> JSONResponse:
	resp = JSONResponse({"status": "ok"})
	clear_session(resp, request)
	return resp


