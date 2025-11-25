from typing import Any, Dict, Optional
import os
import time
import uuid
from fastapi import Request, Response, HTTPException
from ..storage.json_store import load_json, save_json

SESSION_COOKIE = "sid"
SESSION_MAX_AGE = 7 * 24 * 3600
COOKIE_SECURE = (os.environ.get("ENV", "dev").lower() == "prod")


def get_session(request: Request) -> Optional[Dict[str, Any]]:
	sid = request.cookies.get(SESSION_COOKIE)
	if not sid:
		return None
	sessions: Dict[str, Any] = load_json("sessions.json", {})
	return sessions.get(sid)


def set_session(response: Response, user: Dict[str, Any], oauth_token: Optional[str] = None) -> str:
	sessions: Dict[str, Any] = load_json("sessions.json", {})
	sid = str(uuid.uuid4())
	sessions[sid] = {"user": user, "oauth_token": oauth_token, "created_at": int(time.time())}
	save_json("sessions.json", sessions)
	response.set_cookie(
		key=SESSION_COOKIE,
		value=sid,
		max_age=SESSION_MAX_AGE,
		httponly=True,
		secure=COOKIE_SECURE,
		samesite="lax",
	)
	return sid


def clear_session(response: Response, request: Request) -> None:
	sid = request.cookies.get(SESSION_COOKIE)
	if not sid:
		return
	sessions: Dict[str, Any] = load_json("sessions.json", {})
	if sid in sessions:
		del sessions[sid]
		save_json("sessions.json", sessions)
	response.delete_cookie(SESSION_COOKIE)


def require_auth(request: Request) -> Dict[str, Any]:
	sess = get_session(request)
	if not sess or "user" not in sess:
		raise HTTPException(status_code=401, detail="Unauthorized")
	return sess


