
from ..config.config import AppConfig
from ..config.logging_config import configure_logging
from ..integrations.jira_service import JiraService
from ..review.agentic.generator import AgenticReviewGenerator
from ..tagging.gemini_classifier import GeminiTagClassifier
from ..vcs.gitlab_service import GitLabService
from ..webhook.processor import WebhookProcessor

_LOGGER = configure_logging()


def build_services(cfg: AppConfig) -> WebhookProcessor:
	gl_service = GitLabService(cfg.gitlab_url, cfg.gitlab_token)
	reviewer = AgenticReviewGenerator(
		provider=cfg.agentic_provider,
		model=cfg.agentic_model,
		openai_api_key=cfg.openai_api_key or "",
		google_api_key=cfg.google_api_key or "",
		project_context_path=cfg.project_context_path,
		timeout=cfg.agentic_timeout,
	)
	classifier = GeminiTagClassifier(api_key=cfg.gemini_api_key, model=cfg.gemini_model, max_labels=cfg.label_max)
	jira = None
	if cfg.jira_url and cfg.jira_email and cfg.jira_api_token:
		jira = JiraService(
			base_url=cfg.jira_url,
			email=cfg.jira_email,
			api_token=cfg.jira_api_token,
			project_keys=cfg.jira_project_keys,
			max_issues=cfg.jira_max_issues,
			search_window=cfg.jira_search_window,
		)
		_LOGGER.info("Jira integration enabled", extra={"projects": cfg.jira_project_keys, "max_issues": cfg.jira_max_issues})
	else:
		_LOGGER.info("Jira integration disabled (missing JIRA_URL/JIRA_EMAIL/JIRA_API_TOKEN)")
	return WebhookProcessor(
		service=gl_service,
		reviewer=reviewer,
		webhook_secret=cfg.webhook_secret,
		tag_classifier=classifier,
		label_candidates=cfg.label_candidates,
		jira_service=jira,
	)


