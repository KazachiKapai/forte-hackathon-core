import os
from typing import Optional, List


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
		self.env = (read_env("ENV", "prod") or "prod").lower()
		self.label_candidates: List[str] = self._read_label_candidates()
		self.label_max: int = self._read_label_max()

	def _read_label_candidates(self) -> List[str]:
		raw = read_env("LABEL_CANDIDATES", "")
		if not raw:
			return []
		cands = [c.strip() for c in raw.split(",")]
		return [c for c in cands if c]
	
	def _read_label_max(self) -> int:
		raw = read_env("LABEL_MAX", "2")
		try:
			val = int(raw or "2")
		except Exception:
			val = 2
		return max(1, min(val, 5))


