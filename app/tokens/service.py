import datetime
import os
import uuid
from typing import Any

import gitlab

from ..storage.json_store import load_json, save_json

GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com")


def validate_token_with_gitlab(token: str) -> tuple[bool, int | None]:
	try:
		gl = gitlab.Gitlab(GITLAB_URL, private_token=token)
		gl.auth()
		proj_id = None
		try:
			projects = gl.projects.list(membership=True, per_page=1)
			if projects:
				proj_id = getattr(projects[0], "id", None)
		except Exception:
			proj_id = None
		return True, proj_id
	except Exception:
		return False, None


def add_user_token(user_id: str, token: str, name: str) -> dict[str, Any]:
	tokens: dict[str, list[dict[str, Any]]] = load_json("tokens.json", {})
	user_tokens = tokens.get(user_id) or []
	
	# Use timezone-aware UTC timestamp
	now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
	
	new_token = {
		"id": f"token_{uuid.uuid4().hex[:8]}",
		"name": name,
		"project_id": None,
		"scopes": ["api"],
		"created_at": now_iso,
		"last_used_at": None,
		"token": token,
	}
	
	user_tokens.append(new_token)
	tokens[user_id] = user_tokens
	save_json("tokens.json", tokens)
	
	return new_token


def list_user_tokens(user_id: str) -> list[dict[str, Any]]:
	tokens: dict[str, list[dict[str, Any]]] = load_json("tokens.json", {})
	return tokens.get(user_id) or []


def delete_user_token(user_id: str, token_id: str) -> None:
	tokens: dict[str, list[dict[str, Any]]] = load_json("tokens.json", {})
	user_tokens = tokens.get(user_id) or []
	new_list = [t for t in user_tokens if t.get("id") != token_id]
	tokens[user_id] = new_list
	save_json("tokens.json", tokens)


