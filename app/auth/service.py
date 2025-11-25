from typing import Any, Dict, Optional
import os
import urllib.request
import urllib.parse
from ..storage.json_store import load_json, save_json

GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com")
OAUTH_CLIENT_ID = os.environ.get("GITLAB_OAUTH_CLIENT_ID")
OAUTH_CLIENT_SECRET = os.environ.get("GITLAB_OAUTH_CLIENT_SECRET")
OAUTH_REDIRECT_URI = os.environ.get("GITLAB_OAUTH_REDIRECT_URI", "http://localhost:8080/auth/callback")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


def build_authorize_url(state: str) -> str:
	params = {
		"client_id": OAUTH_CLIENT_ID or "",
		"redirect_uri": OAUTH_REDIRECT_URI,
		"response_type": "code",
		"scope": "read_user read_api",
		"state": state,
	}
	return f"{GITLAB_URL}/oauth/authorize?{urllib.parse.urlencode(params)}"


def exchange_code(code: str) -> Dict[str, Any]:
	data = {
		"client_id": OAUTH_CLIENT_ID or "",
		"client_secret": OAUTH_CLIENT_SECRET or "",
		"code": code,
		"grant_type": "authorization_code",
		"redirect_uri": OAUTH_REDIRECT_URI,
	}
	req = urllib.request.Request(
		f"{GITLAB_URL}/oauth/token",
		data=urllib.parse.urlencode(data).encode("utf-8"),
		headers={"Content-Type": "application/x-www-form-urlencoded"},
		method="POST",
	)
	with urllib.request.urlopen(req, timeout=15) as resp:
		body = resp.read().decode("utf-8")
		return __import__("json").loads(body)


def api_get_user(access_token: str) -> Dict[str, Any]:
	req = urllib.request.Request(
		f"{GITLAB_URL}/api/v4/user",
		headers={"Authorization": f"Bearer {access_token}"},
	)
	with urllib.request.urlopen(req, timeout=15) as resp:
		body = resp.read().decode("utf-8")
		return __import__("json").loads(body)


