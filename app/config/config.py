import os
from pathlib import Path


def read_env(name: str, default: str | None = None, required: bool = False) -> str | None:
	value = os.environ.get(name, default)
	if required and (value is None or value == ""):
		raise RuntimeError(f"Missing required environment variable: {name}")
	return value


class AppConfig:
	def __init__(self) -> None:
		base_dir = Path(__file__).resolve().parent
		self.gitlab_url = read_env("GITLAB_URL", "https://gitlab.com")
		self.gitlab_token = read_env("GITLAB_TOKEN", required=True)
		self.webhook_secret = read_env("GITLAB_WEBHOOK_SECRET", required=True)
		self.webhook_url = read_env("WEBHOOK_URL")
		self.host = read_env("HOST", "0.0.0.0")
		self.port = int(read_env("PORT", "8080") or "8080")
		self.gemini_api_key = read_env("GEMINI_API_KEY")
		self.gemini_model = read_env("GEMINI_MODEL", "gemini-2.5-pro")
		self.env = (read_env("ENV", "prod") or "prod").lower()
		self.label_candidates: list[str] = self._read_label_candidates()
		self.label_max: int = self._read_label_max()
		self.jira_url = read_env("JIRA_URL")
		self.jira_email = read_env("JIRA_EMAIL")
		self.jira_api_token = read_env("JIRA_API_TOKEN")
		self.jira_project_keys: list[str] = self._read_jira_projects()
		self.jira_max_issues: int = int(read_env("JIRA_MAX_ISSUES", "5") or "5")
		self.jira_search_window: str = read_env("JIRA_SEARCH_WINDOW", "-30d") or "-30d"
		self.agentic_provider = read_env("AGENTIC_PROVIDER", "google")
		raw_model = read_env("AGENTIC_MODEL", "models/gemini-2.5-flash")
		self.agentic_model = self._normalize_model_name(self.agentic_provider, raw_model)
		self.openai_api_key = read_env("OPENAI_API_KEY")
		self.google_api_key = read_env("GOOGLE_API_KEY") or self.gemini_api_key
		default_context = base_dir / "review" / "agentic" / "context" / "project_context.json"
		self.project_context_path = read_env("PROJECT_CONTEXT_PATH", str(default_context))
		timeout_raw = read_env("AGENTIC_TIMEOUT", "60")
		try:
			self.agentic_timeout = float(timeout_raw or "60")
		except Exception:
			self.agentic_timeout = 60.0

	@staticmethod
	def _normalize_model_name(provider: str | None, model: str | None) -> str | None:
		if not model:
			return model
		if (provider or "").lower().strip() in {"google", "gemini"} and not model.startswith("models/"):
			return f"models/{model}"
		return model

	def _read_label_candidates(self) -> list[str]:
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

	def _read_jira_projects(self) -> list[str]:
		raw = read_env("JIRA_PROJECT_KEYS", "")
		if not raw:
			return ["KZKP"]
		return [p.strip() for p in raw.split(",") if p.strip()]


