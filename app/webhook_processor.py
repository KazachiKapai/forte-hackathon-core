from typing import Any, Dict, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import gitlab

from .vcs.base import VCSService
from .review.base import ReviewGenerator
from .tagging.base import TagClassifier
from .logging_config import configure_logging

_LOGGER = configure_logging()


class WebhookProcessor:
	def __init__(self, service: VCSService, reviewer: ReviewGenerator, webhook_secret: str, tag_classifier: Optional[TagClassifier] = None, label_candidates: Optional[List[str]] = None) -> None:
		self.service = service
		self.reviewer = reviewer
		self.webhook_secret = webhook_secret
		self.tag_classifier = tag_classifier
		self.label_candidates = label_candidates or []

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

		# Only validate input and action; heavy work is scheduled by the server
		return {"status": "ok", "validated": True}

	def process_merge_request(self, project_id: int, mr_iid: int, title: str, description: str) -> None:
		"""Heavy processing of MR in background."""
		try:
			project = self.service.get_project(project_id)
		except Exception as e:
			_LOGGER.exception("Failed to fetch project for processing", extra={"project_id": project_id})
			return
		# Fetch MR-derived data concurrently
		with ThreadPoolExecutor(max_workers=3) as pool:
			diff_f = pool.submit(self.service.collect_mr_diff_text, project, mr_iid)
			files_f = pool.submit(self.service.get_changed_files_with_content, project, mr_iid)
			commits_f = pool.submit(self.service.get_mr_commits, project, mr_iid)
			diff_text = ""
			changed_files: List[Any] = []
			commit_messages: List[str] = []
			try:
				diff_text = diff_f.result()
			except Exception:
				_LOGGER.exception("Failed to fetch MR diff", extra={"mr_iid": mr_iid, "project_id": project_id})
			try:
				changed_files = files_f.result()
			except Exception:
				_LOGGER.exception("Failed to fetch changed files", extra={"mr_iid": mr_iid, "project_id": project_id})
			try:
				commit_objs = commits_f.result()
				commit_messages = [c.get("message", "") for c in commit_objs if isinstance(c, dict) and c.get("message")]
			except Exception:
				_LOGGER.exception("Failed to fetch MR commits", extra={"mr_iid": mr_iid, "project_id": project_id})

		# Generate review and optional label concurrently
		review_comments: List[str] = []
		label_choice: Optional[List[str]] = None
		with ThreadPoolExecutor(max_workers=2) as pool:
			review_f = pool.submit(
				self.reviewer.generate_review,
				title,
				description,
				diff_text,
				changed_files,
				commit_messages,
			)
			if self.tag_classifier and self.label_candidates:
				_LOGGER.info(
					"Tagging enabled; classifying MR",
					extra={"candidates_count": len(self.label_candidates), "mr_iid": mr_iid, "project_id": project_id},
				)
				label_f = pool.submit(
					self.tag_classifier.classify,
					title,
					description,
					diff_text,
					changed_files,
					commit_messages,
					self.label_candidates,
				)
			else:
				label_f = None
			try:
				review_res = review_f.result()
				if isinstance(review_res, list):
					review_comments = [c.to_markdown() if hasattr(c, "to_markdown") else str(c) for c in review_res if c]
				elif review_res:
					review_comments = [str(review_res)]
			except Exception:
				_LOGGER.exception("Failed to generate review", extra={"mr_iid": mr_iid, "project_id": project_id})
			if label_f is not None:
				try:
					label_choice = label_f.result()
				except Exception:
					_LOGGER.exception("Classifier failed", extra={"mr_iid": mr_iid, "project_id": project_id})

		# Post results
		if review_comments:
			for body in review_comments:
				if not body:
					continue
				try:
					self.service.post_mr_note(project, mr_iid, body)
				except Exception:
					_LOGGER.exception("Failed to post MR note", extra={"mr_iid": mr_iid, "project_id": project_id})
					break
		if label_choice:
			try:
				self.service.update_mr_labels(project, mr_iid, label_choice)
				_LOGGER.info("Applied MR labels", extra={"labels": label_choice, "mr_iid": mr_iid, "project_id": project_id})
			except Exception:
				_LOGGER.exception("Failed to apply MR label", extra={"mr_iid": mr_iid, "project_id": project_id})


