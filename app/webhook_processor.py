from typing import Any, Dict, Optional
import gitlab

from .gitlab_service import GitLabService
from .review.base import ReviewGenerator


class WebhookProcessor:
	def __init__(self, service: GitLabService, reviewer: ReviewGenerator, webhook_secret: str) -> None:
		self.service = service
		self.reviewer = reviewer
		self.webhook_secret = webhook_secret

	def validate_secret(self, provided: Optional[str]) -> None:
		if not provided or provided != self.webhook_secret:
			raise PermissionError("Invalid webhook token")

	def handle_merge_request_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
		object_kind = payload.get("object_kind")
		if object_kind != "merge_request":
			return {"status": "ignored", "reason": "not_merge_request"}

		attributes = payload.get("object_attributes", {}) or {}
		action = attributes.get("action")
		project_info = payload.get("project", {}) or {}
		project_id = project_info.get("id")
		mr_iid = attributes.get("iid")
		title = attributes.get("title") or ""
		description = attributes.get("description") or ""

		if project_id is None or mr_iid is None:
			return {"status": "error", "code": 400, "message": "Missing project_id or mr_iid"}
		try:
			project_id = int(project_id)
			mr_iid = int(mr_iid)
		except Exception:
			return {"status": "error", "code": 400, "message": "project_id and mr_iid must be integers"}
		if project_id <= 0 or mr_iid <= 0:
			return {"status": "error", "code": 400, "message": "project_id and mr_iid must be positive integers"}

		if action not in {"open", "reopen", "update"}:
			return {"status": "ignored", "action": action}

		try:
			project = self.service.get_project(project_id)
		except gitlab.exceptions.GitlabGetError as e:
			return {"status": "error", "code": 404, "message": f"GitLab project not found: {e}"}
		try:
			_ = project.mergerequests.get(mr_iid)
		except gitlab.exceptions.GitlabGetError as e:
			return {"status": "error", "code": 404, "message": f"GitLab merge request not found: {e}"}

		diff_text = self.service.collect_mr_diff_text(project, mr_iid)
		review_body = self.reviewer.generate_review(diff_text, title=title, description=description)
		self.service.post_mr_note(project, mr_iid, review_body)
		return {"status": "ok", "posted": True}


