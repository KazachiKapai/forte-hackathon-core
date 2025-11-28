from typing import Any

from fastapi import APIRouter, Depends
from ..auth.auth import get_current_user
from . import service as repos_service

router = APIRouter()


@router.get("/repositories")
async def list_repositories(
	search: str | None = None,
	page: int = 1,
	per_page: int = 10,
	current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
	user_id = current_user["user_id"]
	items = repos_service.load_repos(user_id)
	if search:
		q = search.lower()
		items = [r for r in items if q in (r.get("name") or "").lower() or q in (r.get("full_path") or "").lower()]
	total = len(items)
	start = max(0, (page - 1) * per_page)
	end = start + per_page
	return {"data": items[start:end], "pagination": {"page": page, "per_page": per_page, "total": total}}


@router.post("/repositories/sync")
async def sync_repositories_route(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
	user_id = current_user["user_id"]
	count = repos_service.sync_repositories(user_id)
	return {"synced": count}


