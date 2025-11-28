from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..config.logging_config import configure_logging
from ..auth.auth import get_current_user
from ..storage.json_store import load_json, save_json
from . import service as token_service

_LOGGER = configure_logging()
router = APIRouter()


@router.get("/api/onboarding/status")
async def onboarding_status(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
	user_id = current_user["user_id"]
	user_tokens = token_service.list_user_tokens(user_id)
	return {
		"completed": True,
		"has_tokens": len(user_tokens) > 0,
		"token_count": len(user_tokens),
	}


@router.post("/api/onboarding/token")
async def add_token(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
	user_id = current_user["user_id"]
	body = await request.json()
	token = (body.get("token") or "").strip()
	name = (body.get("name") or "").strip() or "Token"
	if not token.startswith("glpat-"):
		raise HTTPException(status_code=400, detail="Invalid token format")
	ok, proj_id = token_service.validate_token_with_gitlab(token)
	if not ok:
		raise HTTPException(status_code=400, detail="Token validation failed with GitLab")
	token_id = token_service.add_user_token(user_id, token, name)
	# patch project_id if known
	tokens: dict[str, list[dict[str, Any]]] = load_json("tokens.json", {})
	for t in tokens.get(user_id, []):
		if t.get("id") == token_id:
			t["project_id"] = proj_id
	save_json("tokens.json", tokens)
	return {"success": True, "message": "Token added successfully", "token_id": token_id}


@router.get("/api/tokens")
async def list_tokens(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
	user_id = current_user["user_id"]
	user_tokens = token_service.list_user_tokens(user_id)
	out = []
	for t in user_tokens:
		out.append(
			{
				"id": t.get("id"),
				"name": t.get("name"),
				"project_id": t.get("project_id"),
				"scopes": t.get("scopes") or [],
				"created_at": t.get("created_at"),
				"last_used_at": t.get("last_used_at"),
			}
		)
	return {"data": out}


@router.delete("/api/tokens/{token_id}")
async def delete_token_route(token_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> Response:
	user_id = current_user["user_id"]
	token_service.delete_user_token(user_id, token_id)
	return Response(status_code=204)
