from __future__ import annotations

import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any


class OAuthProvider(ABC):
	@abstractmethod
	def build_authorize_url(self, state: str) -> str: ...

	@abstractmethod
	def exchange_code(self, code: str) -> dict[str, Any]: ...

	@abstractmethod
	def api_get_user(self, access_token: str) -> dict[str, Any]: ...


class GitLabOAuthProvider(OAuthProvider):
	def __init__(self, base_url: str, client_id: str | None, client_secret: str | None, redirect_uri: str) -> None:
		self.base_url = base_url.rstrip("/")
		self.client_id = client_id or ""
		self.client_secret = client_secret or ""
		self.redirect_uri = redirect_uri

	def build_authorize_url(self, state: str) -> str:
		params = {
			"client_id": self.client_id,
			"redirect_uri": self.redirect_uri,
			"response_type": "code",
			"scope": "read_user read_api",
			"state": state,
		}
		return f"{self.base_url}/oauth/authorize?{urllib.parse.urlencode(params)}"

	def exchange_code(self, code: str) -> dict[str, Any]:
		data = {
			"client_id": self.client_id,
			"client_secret": self.client_secret,
			"code": code,
			"grant_type": "authorization_code",
			"redirect_uri": self.redirect_uri,
		}
		req = urllib.request.Request(
			f"{self.base_url}/oauth/token",
			data=urllib.parse.urlencode(data).encode("utf-8"),
			headers={"Content-Type": "application/x-www-form-urlencoded"},
			method="POST",
		)
		with urllib.request.urlopen(req, timeout=15) as resp:
			body = resp.read().decode("utf-8")
			return __import__("json").loads(body)

	def api_get_user(self, access_token: str) -> dict[str, Any]:
		req = urllib.request.Request(
			f"{self.base_url}/api/v4/user",
			headers={"Authorization": f"Bearer {access_token}"},
		)
		with urllib.request.urlopen(req, timeout=15) as resp:
			body = resp.read().decode("utf-8")
			return __import__("json").loads(body)


