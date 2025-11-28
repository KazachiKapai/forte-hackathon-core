from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..config.config import AppConfig
from ..config.logging_config import configure_logging
from ..auth.auth import get_current_user
from ..storage.json_store import load_json, save_json
from . import service as token_service
from ..vcs.gitlab_service import GitLabService

_LOGGER = configure_logging()
router = APIRouter()

cfg = AppConfig()
gl_service = GitLabService(cfg.gitlab_url, cfg.gitlab_token)

@router.get("/onboarding/status")
async def onboarding_status(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_id = current_user["user_id"]
    user_tokens = token_service.list_user_tokens(user_id)
    return {
        "completed": True,
        "has_tokens": len(user_tokens) > 0,
        "token_count": len(user_tokens),
    }


@router.post("/onboarding/token")
async def add_token(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_id = current_user["user_id"]

    # Parse JSON body with error handling
    try:
        body = await request.json()
    except Exception as e:
        _LOGGER.error(f"Failed to parse JSON body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON in request body")

    token = (body.get("token") or "").strip()
    name = (body.get("name") or "").strip() or "Token"

    if not token:
        raise HTTPException(status_code=400, detail="Token is required")

    if not token.startswith("glpat-"):
        raise HTTPException(status_code=400, detail="Invalid token format")

    ok, proj_id = token_service.validate_token_with_gitlab(token)
    if not ok:
        raise HTTPException(status_code=400, detail="Token validation failed with GitLab")

    new_token = token_service.add_user_token(user_id, token, name)
    new_token["project_id"] = proj_id

    project = gl_service.get_project(proj_id)
    gl_service.ensure_webhook_for_project(project, cfg.webhook_url, cfg.webhook_secret)

    # To avoid saving the token twice, we can update the project_id in the stored token
    tokens: dict[str, list[dict[str, Any]]] = load_json("tokens.json", {})
    user_tokens = tokens.get(user_id, [])
    for t in user_tokens:
        if t.get("id") == new_token["id"]:
            t["project_id"] = proj_id
            break
    save_json("tokens.json", tokens)

    # For security, don't return the raw token in the response
    token_response = new_token.copy()
    token_response.pop("token", None)

    return {"success": True, "message": "Token added successfully", "token": token_response}


@router.get("/tokens")
async def list_tokens(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
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


@router.delete("/tokens/{token_id}")
async def delete_token_route(request: Request, token_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> Response:
    user_id = current_user["user_id"]
    token_service.delete_user_token(user_id, token_id)
    return Response(status_code=204)
