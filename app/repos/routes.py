from typing import Any

from fastapi import APIRouter, Request

from ..security.session import require_auth
from . import service as repos_service

router = APIRouter()


@router.get("/api/repositories")
async def list_repositories(request: Request, search: str | None = None, page: int = 1, per_page: int = 10) -> dict[str, Any]:
	sess = require_auth(request)
	user_id = sess["user"]["id"]
	items = repos_service.load_repos(user_id)
	if search:
		q = search.lower()
		items = [r for r in items if q in (r.get("name") or "").lower() or q in (r.get("full_path") or "").lower()]
	total = len(items)
	start = max(0, (page - 1) * per_page)
	end = start + per_page
	return {"data": items[start:end], "pagination": {"page": page, "per_page": per_page, "total": total}}


@router.post("/api/repositories/sync")
async def sync_repositories_route(request: Request) -> dict[str, Any]:
	sess = require_auth(request)
	user_id = sess["user"]["id"]
	count = repos_service.sync_repositories(user_id)
	return {"synced": count}


