import os
from typing import Optional


def read_env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
	value = os.environ.get(name, default)
	if required and (value is None or value == ""):
		raise RuntimeError(f"Missing required environment variable: {name}")
	return value


class AppConfig:
	def __init__(self) -> None:
		self.gitlab_url = read_env("GITLAB_URL", "https://gitlab.com")
		self.gitlab_token = read_env("GITLAB_TOKEN", required=True)
		self.webhook_secret = read_env("GITLAB_WEBHOOK_SECRET", required=True)
		self.webhook_url = read_env("WEBHOOK_URL")
		self.host = read_env("HOST", "0.0.0.0")
		self.port = int(read_env("PORT", "8080") or "8080")
		self.gemini_api_key = read_env("GEMINI_API_KEY")
		self.gemini_model = read_env("GEMINI_MODEL", "gemini-2.5-pro")


