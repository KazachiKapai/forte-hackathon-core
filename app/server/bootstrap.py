from ..config.config import AppConfig
from ..integrations.jira_service import JiraService
from ..review.agentic.generator import AgenticReviewGenerator
from ..review.agentic.agents.discussion_agent import DiscussionAgent
from ..tagging.gemini_classifier import GeminiTagClassifier
from ..webhook.processor import WebhookProcessor


def build_services(cfg: AppConfig) -> WebhookProcessor:
    reviewer = AgenticReviewGenerator(
        provider=cfg.agentic_provider,
        model=cfg.agentic_model,
        openai_api_key=cfg.openai_api_key,
        google_api_key=cfg.google_api_key,
        project_context_path=cfg.project_context_path,
        timeout=cfg.agentic_timeout,
    )
    discussion_agent = DiscussionAgent(api_key=cfg.gemini_api_key, model=cfg.gemini_model)
    classifier = GeminiTagClassifier(api_key=cfg.gemini_api_key, model=cfg.gemini_model, max_labels=cfg.label_max)
    jira = JiraService(
        base_url=cfg.jira_url,
        email=cfg.jira_email,
        api_token=cfg.jira_api_token,
        project_keys=cfg.jira_project_keys,
        max_issues=cfg.jira_max_issues,
        search_window=cfg.jira_search_window,
    )

    return WebhookProcessor(
        reviewer=reviewer,
        webhook_secret=cfg.webhook_secret,
        discussion_agent=discussion_agent,
        tag_classifier=classifier,
        label_candidates=cfg.label_candidates,
        jira_service=jira,
        gitlab_url=cfg.gitlab_url,
    )


