from typing import Any, Dict, List, Optional, Tuple
import datetime
import uuid
import gitlab
import os
from ..storage.json_store import load_json, save_json

GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com")


def validate_token_with_gitlab(token: str) -> Tuple[bool, Optional[int]]:
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


def add_user_token(user_id: str, token: str, name: str) -> str:
	tokens: Dict[str, List[Dict[str, Any]]] = load_json("tokens.json", {})
	user_tokens = tokens.get(user_id) or []
	token_id = f"token_{uuid.uuid4().hex[:8]}"
	now_iso = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
	user_tokens.append(
		{
			"id": token_id,
			"name": name,
			"project_id": None,
			"scopes": ["api"],
			"created_at": now_iso,
			"last_used_at": None,
			"token": token,
		}
	)
	tokens[user_id] = user_tokens
	save_json("tokens.json", tokens)
	return token_id


def list_user_tokens(user_id: str) -> List[Dict[str, Any]]:
	tokens: Dict[str, List[Dict[str, Any]]] = load_json("tokens.json", {})
	return tokens.get(user_id) or []


def delete_user_token(user_id: str, token_id: str) -> None:
	tokens: Dict[str, List[Dict[str, Any]]] = load_json("tokens.json", {})
	user_tokens = tokens.get(user_id) or []
	new_list = [t for t in user_tokens if t.get("id") != token_id]
	tokens[user_id] = new_list
	save_json("tokens.json", tokens)


