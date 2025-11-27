import os
from typing import Any

from .provider import GitLabOAuthProvider, OAuthProvider

GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com")
OAUTH_CLIENT_ID = os.environ.get("GITLAB_OAUTH_CLIENT_ID")
OAUTH_CLIENT_SECRET = os.environ.get("GITLAB_OAUTH_CLIENT_SECRET")
OAUTH_REDIRECT_URI = os.environ.get("GITLAB_OAUTH_REDIRECT_URI", "http://localhost:8080/auth/callback")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


_provider: OAuthProvider | None = None


def _get_provider() -> OAuthProvider:
	global _provider
	if _provider is None:
		_provider = GitLabOAuthProvider(
			base_url=GITLAB_URL,
			client_id=OAUTH_CLIENT_ID,
			client_secret=OAUTH_CLIENT_SECRET,
			redirect_uri=OAUTH_REDIRECT_URI,
		)
	return _provider


def exchange_code(code: str) -> dict[str, Any]:
	return _get_provider().exchange_code(code)


def api_get_user(access_token: str) -> dict[str, Any]:
	return _get_provider().api_get_user(access_token)


def build_authorize_url(state: str) -> str:
	return _get_provider().build_authorize_url(state)


