import os
import logging
from typing import Any

import gitlab
from fastapi import HTTPException
from gitlab.exceptions import GitlabError

from ..storage.json_store import load_json, save_json

GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com")
_LOGGER = logging.getLogger(__name__)


def load_repos(user_id: str) -> list[dict[str, Any]]:
	all_repos: dict[str, list[dict[str, Any]]] = load_json("repos.json", {})
	return all_repos.get(user_id) or []


def save_repos(user_id: str, items: list[dict[str, Any]]) -> None:
	all_repos: dict[str, list[dict[str, Any]]] = load_json("repos.json", {})
	all_repos[user_id] = items
	save_json("repos.json", all_repos)


def sync_repositories(user_id: str) -> int:
	tokens: dict[str, list[dict[str, Any]]] = load_json("tokens.json", {})
	user_tokens = tokens.get(user_id) or []
	if not user_tokens:
		save_repos(user_id, [])
		return 0
	projects_map: dict[int, dict[str, Any]] = {}
	for t in user_tokens:
		private_token = t.get("token")
		if not private_token:
			continue
		try:
			gl = gitlab.Gitlab(GITLAB_URL, private_token=private_token)
			gl.auth()
			projs = gl.projects.list(membership=True, all=True)
			for p in projs:
				try:
					pid = int(getattr(p, "id", 0) or 0)
					if not pid:
						continue
					projects_map[pid] = {
						"id": f"repo_{pid}",
						"gitlab_repo_id": pid,
						"name": getattr(p, "name", None),
						"full_path": getattr(p, "path_with_namespace", None),
						"visibility": getattr(p, "visibility", None),
						"description": getattr(p, "description", None),
						"last_review_at": None,
					}
				except Exception as e:
					_LOGGER.warning(f"Failed to process project {getattr(p, 'id', 'N/A')}: {e}")
					continue
		except GitlabError as e:
			_LOGGER.warning(f"GitLab API error for user {user_id} with token ID {t.get('id')}: {e}")
			if e.response_code == 401:
				continue
			raise HTTPException(status_code=502, detail=f"GitLab API error: {e.error_message}")
		except Exception as e:
			_LOGGER.error(f"Unexpected error during GitLab sync for user {user_id}: {e}", exc_info=True)
			raise HTTPException(status_code=500, detail="An internal error occurred during repository sync.")
	repos = list(projects_map.values())
	save_repos(user_id, repos)
	return len(repos)


