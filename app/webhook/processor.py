from typing import Any, Dict, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor
import gitlab

from ..vcs.base import VCSService
from ..review.base import ReviewGenerator
from ..tagging.base import TagClassifier
from ..integrations.jira_service import JiraService
from ..config.logging_config import configure_logging

_LOGGER = configure_logging()


class WebhookProcessor:
	def __init__(self, service: VCSService, reviewer: ReviewGenerator, webhook_secret: str, tag_classifier: Optional[TagClassifier] = None, label_candidates: Optional[List[str]] = None, jira_service: Optional[JiraService] = None) -> None:
		self.service = service
		self.reviewer = reviewer
		self.webhook_secret = webhook_secret
		self.tag_classifier = tag_classifier
		self.label_candidates = label_candidates or []
		self.jira_service = jira_service

	def validate_secret(self, provided: Optional[str]) -> None:
		if not provided or provided != self.webhook_secret:
			raise PermissionError("Invalid webhook token")

	def handle_merge_request_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
		if payload.get("object_kind") != "merge_request":
			return {"status": "ignored", "reason": "not_merge_request"}

		ok, result = self._parse_event(payload)
		if not ok:
			return result

		return {"status": "ok", "validated": True}

	def process_merge_request(self, project_id: int, mr_iid: int, title: str, description: str, event_uuid: Optional[str] = None) -> None:
		_LOGGER.info(
			"Processing MR start",
			extra={"event_uuid": event_uuid, "project_id": project_id, "mr_iid": mr_iid, "title_len": len(title or "")},
		)
		try:
			project = self.service.get_project(project_id)
		except Exception:
			_LOGGER.exception("Failed to fetch project for processing", extra={"project_id": project_id})
			return
		diff_text, changed_files, commit_messages = self._gather_mr_data(project, project_id, mr_iid)
		description_aug = self._augment_with_tickets(project, mr_iid, title, description)
		review_comments, label_choice = self._review_and_classify(title, description_aug, diff_text, changed_files, commit_messages, project_id, mr_iid)
		if review_comments:
			# Idempotency by MR version: embed and check a version marker
			version_id = None
			try:
				version_id = self.service.get_latest_mr_version_id(project, mr_iid)  # type: ignore[attr-defined]
			except Exception:
				version_id = None
			marker = f"[ai-review v:{version_id or 'unknown'}]"
			try:
				notes = project.mergerequests.get(mr_iid).notes.list(per_page=20)
				for n in notes:
					if marker in (getattr(n, "body", "") or ""):
						_LOGGER.info("Duplicate review detected for version, skipping post", extra={"mr_iid": mr_iid, "version": version_id})
						review_comments = []
						break
			except Exception:
				pass
			if review_comments:
				review_comments = review_comments[:]
				review_comments[0] = f"{marker}\n{review_comments[0]}"
				for body in review_comments:
					if not body:
						continue
					try:
						self.service.post_mr_note(project, mr_iid, body)
					except Exception:
						_LOGGER.exception("Failed to post MR note", extra={"mr_iid": mr_iid, "project_id": project_id})
						break
				else:
					_LOGGER.info("Posted MR review", extra={"event_uuid": event_uuid, "project_id": project_id, "mr_iid": mr_iid, "version": version_id})
		if label_choice:
			try:
				self.service.update_mr_labels(project, mr_iid, label_choice)
				_LOGGER.info("Applied MR labels", extra={"event_uuid": event_uuid, "labels": label_choice, "mr_iid": mr_iid, "project_id": project_id})
			except Exception:
				_LOGGER.exception("Failed to apply MR label", extra={"mr_iid": mr_iid, "project_id": project_id})
		_LOGGER.info(
			"Processing MR done",
			extra={"event_uuid": event_uuid, "project_id": project_id, "mr_iid": mr_iid},
		)

	def _parse_event(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
		attrs = payload.get("object_attributes", {}) or {}
		changes = payload.get("changes", {}) or {}
		project_info = payload.get("project", {}) or {}
		project_id = project_info.get("id")
		mr_iid = attrs.get("iid")
		action = attrs.get("action")
		if project_id is None or mr_iid is None:
			return False, {"status": "error", "code": 400, "message": "Missing project_id or mr_iid"}
		try:
			project_id = int(project_id)
			mr_iid = int(mr_iid)
		except Exception:
			return False, {"status": "error", "code": 400, "message": "project_id and mr_iid must be integers"}
		if project_id <= 0 or mr_iid <= 0:
			return False, {"status": "error", "code": 400, "message": "project_id and mr_iid must be positive integers"}
		if action not in {"open", "reopen", "update"}:
			return False, {"status": "ignored", "action": action}
		if action == "update":
			changed = set(changes.keys())
			non_meaningful = {"labels", "updated_at", "last_edited_at", "assignee_id", "assignee_ids", "updated_by_id"}
			if changed and changed.issubset(non_meaningful):
				_LOGGER.info("Skipping non-meaningful update", extra={"project_id": project_id, "mr_iid": mr_iid, "changed": list(changed)})
				return False, {"status": "ignored", "reason": "non_meaningful_update"}
		return True, {}

	def _gather_mr_data(self, project: Any, project_id: int, mr_iid: int) -> Tuple[str, List[Any], List[str]]:
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
		return diff_text, changed_files, commit_messages

	def _review_and_classify(
		self,
		title: str,
		description: str,
		diff_text: str,
		changed_files: List[Any],
		commit_messages: List[str],
		project_id: int,
		mr_iid: int,
	) -> Tuple[List[str], Optional[List[str]]]:
		review_comments: List[str] = []
		label_choice: Optional[List[str]] = None
		with ThreadPoolExecutor(max_workers=2) as pool:
			review_f = pool.submit(self.reviewer.generate_review, title, description, diff_text, changed_files, commit_messages)
			if self.tag_classifier and self.label_candidates:
				_LOGGER.info("Tagging enabled; classifying MR", extra={"candidates_count": len(self.label_candidates), "mr_iid": mr_iid, "project_id": project_id})
				label_f = pool.submit(self.tag_classifier.classify, title, description, diff_text, changed_files, commit_messages, self.label_candidates)
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

		return review_comments, label_choice

	def _augment_with_tickets(self, project: Any, mr_iid: int, title: str, description: str) -> str:
		if not self.jira_service:
			return description
		try:
			mr = project.mergerequests.get(mr_iid)
			labels = list(getattr(mr, "labels", []) or [])
			created_at = getattr(mr, "created_at", None)
			web_url = getattr(mr, "web_url", None)
			_LOGGER.info("Searching Jira for related tickets", extra={"mr_iid": mr_iid, "labels": labels})
			issues = self.jira_service.search_related_issues(
				title=title,
				description=description or "",
				labels=labels,
				created_at_iso=created_at,
				mr_url=web_url,
			)
			if not issues:
				_LOGGER.info("No related Jira tickets found", extra={"mr_iid": mr_iid})
				return description
			lines: List[str] = ["Related Tickets:"]
			for it in issues:
				lines.append(f"- {it.get('key')} [{it.get('status')}]: {it.get('summary')} ({it.get('url')})")
			_LOGGER.info("Appending related Jira tickets", extra={"mr_iid": mr_iid, "count": len(issues)})
			return (description or "") + "\n\n" + "\n".join(lines)
		except Exception:
			_LOGGER.exception("Jira augmentation failed", extra={"mr_iid": mr_iid})
			return description


