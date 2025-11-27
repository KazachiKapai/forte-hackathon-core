from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from ..config.logging_config import configure_logging
from ..integrations.jira_service import JiraService
from ..review.base import InlineFinding, ReviewGenerator
from ..tagging.base import TagClassifier
from ..vcs.base import VCSService

_LOGGER = configure_logging()

_ALLOWED_ACTIONS = {"open", "reopen", "update"}
_NON_MEANINGFUL_UPDATE_FIELDS = {"labels", "updated_at", "last_edited_at", "assignee_id", "assignee_ids", "updated_by_id"}


@dataclass(frozen=True)
class _ReviewOutcome:
	comments: list[str]
	labels: list[str] | None
	inline_findings: list[InlineFinding]


class WebhookProcessor:
	def __init__(self, service: VCSService, reviewer: ReviewGenerator, webhook_secret: str, tag_classifier: TagClassifier | None = None, label_candidates: list[str] | None = None, jira_service: JiraService | None = None) -> None:
		self.service = service
		self.reviewer = reviewer
		self.webhook_secret = webhook_secret
		self.tag_classifier = tag_classifier
		self.label_candidates = label_candidates or []
		self.jira_service = jira_service

	def validate_secret(self, provided: str | None) -> None:
		"""
		Validate that a provided webhook token matches the configured secret.
		Raises PermissionError on mismatch.
		"""
		if not provided or provided != self.webhook_secret:
			raise PermissionError("Invalid webhook token")

	def handle_merge_request_event(self, payload: dict[str, Any]) -> dict[str, Any]:
		"""
		Perform lightweight validation and event filtering for a webhook payload.
		Returns a dict with either status=ok or a terminal status (ignored/error).
		"""
		if payload.get("object_kind") != "merge_request":
			return {"status": "ignored", "reason": "not_merge_request"}

		ok, result = self._parse_event(payload)
		if not ok:
			return result

		return {"status": "ok", "validated": True}

	def process_merge_request(self, project_id: int, mr_iid: int, title: str, description: str, event_uuid: str | None = None) -> None:
		"""
		Fully process a validated MR event: fetch MR data, optionally augment
		with Jira, generate review, and post comments/labels/inline findings.
		All side-effecting operations are protected with error logging to
		ensure the pipeline is resilient to partial failures.
		"""
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
		outcome = self._generate_review_outcome(title, description_aug, diff_text, changed_files, commit_messages, project_id, mr_iid)
		self._handle_review_outcome(project_id, mr_iid, project, outcome, event_uuid)
		_LOGGER.info(
			"Processing MR done",
			extra={"event_uuid": event_uuid, "project_id": project_id, "mr_iid": mr_iid},
		)

	def _parse_event(self, payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
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
		if action not in _ALLOWED_ACTIONS:
			return False, {"status": "ignored", "action": action}
		if action == "update":
			changed = set(changes.keys())
			if changed and changed.issubset(_NON_MEANINGFUL_UPDATE_FIELDS):
				_LOGGER.info("Skipping non-meaningful update", extra={"project_id": project_id, "mr_iid": mr_iid, "changed": list(changed)})
				return False, {"status": "ignored", "reason": "non_meaningful_update"}
		return True, {}

	def _gather_mr_data(self, project: Any, project_id: int, mr_iid: int) -> tuple[str, list[Any], list[str]]:
		"""
		Fetch diff text, changed files, and commit messages concurrently.
		Returns empty values when individual fetches fail.
		"""
		with ThreadPoolExecutor(max_workers=3) as pool:
			diff_f = pool.submit(self.service.collect_mr_diff_text, project, mr_iid)
			files_f = pool.submit(self.service.get_changed_files_with_content, project, mr_iid)
			commits_f = pool.submit(self.service.get_mr_commits, project, mr_iid)
			diff_text = ""
			changed_files: list[Any] = []
			commit_messages: list[str] = []
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
		changed_files: list[Any],
		commit_messages: list[str],
		project_id: int,
		mr_iid: int,
	) -> tuple[list[str], list[str] | None, list[InlineFinding]]:
		"""
		Run the review generator and optional classifier in parallel and collect results.
		"""
		review_comments: list[str] = []
		label_choice: list[str] | None = None
		inline_findings: list[InlineFinding] = []
		with ThreadPoolExecutor(max_workers=2) as pool:
			review_f = pool.submit(self.reviewer.generate_review, title, description, diff_text, changed_files, commit_messages)
			if self.tag_classifier and self.label_candidates:
				_LOGGER.info("Tagging enabled; classifying MR", extra={"candidates_count": len(self.label_candidates), "mr_iid": mr_iid, "project_id": project_id})
				label_f = pool.submit(self.tag_classifier.classify, title, description, diff_text, changed_files, commit_messages, self.label_candidates)
			else:
				label_f = None
			try:
				review_res = review_f.result()
				if hasattr(review_res, "comments"):
					comments = getattr(review_res, "comments", []) or []
					review_comments = [
						c.to_markdown() if hasattr(c, "to_markdown") else str(c) for c in comments if c
					]
					inline_findings = list(getattr(review_res, "inline_findings", []) or [])
				elif isinstance(review_res, list):
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

		return review_comments, label_choice, inline_findings

	def _augment_with_tickets(self, project: Any, mr_iid: int, title: str, description: str) -> str:
		"""
		Append related Jira tickets to the MR description when Jira is configured.
		Returns the original description on any error or when Jira is disabled.
		"""
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
			lines: list[str] = ["Related Tickets:"]
			for it in issues:
				lines.append(f"- {it.get('key')} [{it.get('status')}]: {it.get('summary')} ({it.get('url')})")
			_LOGGER.info("Appending related Jira tickets", extra={"mr_iid": mr_iid, "count": len(issues)})
			return (description or "") + "\n\n" + "\n".join(lines)
		except Exception:
			_LOGGER.exception("Jira augmentation failed", extra={"mr_iid": mr_iid})
			return description

	def _generate_review_outcome(
		self,
		title: str,
		description: str,
		diff_text: str,
		changed_files: list[Any],
		commit_messages: list[str],
		project_id: int,
		mr_iid: int,
	) -> _ReviewOutcome:
		comments, labels, findings = self._review_and_classify(
			title, description, diff_text, changed_files, commit_messages, project_id, mr_iid
		)
		return _ReviewOutcome(comments=comments, labels=labels, inline_findings=findings)

	def _handle_review_outcome(
		self,
		project_id: int,
		mr_iid: int,
		project: Any,
		outcome: _ReviewOutcome,
		event_uuid: str | None,
	) -> None:
		"""
		Apply the generated outcome: notes, inline findings, and labels,
		with idempotency checks and robust error handling.
		"""
		if outcome.comments:
			version_id = self._safe_get_latest_version_id(project, mr_iid)
			marker = self._build_version_marker(version_id)
			if self._has_existing_marker(project, mr_iid, marker):
				_LOGGER.info("Duplicate review detected for version, skipping post", extra={"mr_iid": mr_iid, "version": version_id})
			else:
				self._post_review_comments(project_id, mr_iid, project, outcome.comments, marker, event_uuid, version_id)
		if outcome.inline_findings:
			self._post_inline_findings(project_id, mr_iid, project, outcome.inline_findings)
		if outcome.labels:
			self._apply_labels(project_id, mr_iid, project, outcome.labels, event_uuid)

	def _safe_get_latest_version_id(self, project: Any, mr_iid: int) -> str | None:
		try:
			return self.service.get_latest_mr_version_id(project, mr_iid)  # type: ignore[attr-defined]
		except Exception:
			return None

	def _build_version_marker(self, version_id: str | None) -> str:
		return f"[ai-review v:{version_id or 'unknown'}]"

	def _has_existing_marker(self, project: Any, mr_iid: int, marker: str) -> bool:
		try:
			notes = project.mergerequests.get(mr_iid).notes.list(per_page=20)
		except Exception:
			return False
		for n in notes:
			if marker in (getattr(n, "body", "") or ""):
				return True
		return False

	def _post_review_comments(
		self,
		project_id: int,
		mr_iid: int,
		project: Any,
		comments: list[str],
		marker: str,
		event_uuid: str | None,
		version_id: str | None,
	) -> None:
		to_post = comments[:]
		to_post[0] = f"{marker}\n{to_post[0]}" if to_post and to_post[0] else marker
		for body in to_post:
			if not body:
				continue
			try:
				self.service.post_mr_note(project, mr_iid, body)
			except Exception:
				_LOGGER.exception("Failed to post MR note", extra={"mr_iid": mr_iid, "project_id": project_id})
				break
		else:
			_LOGGER.info("Posted MR review", extra={"event_uuid": event_uuid, "project_id": project_id, "mr_iid": mr_iid, "version": version_id})

	def _post_inline_findings(self, project_id: int, mr_iid: int, project: Any, findings: list[InlineFinding]) -> None:
		for finding in findings[:10]:
			try:
				self.service.review_line(project, mr_iid, finding.body, finding.path, finding.line)
			except Exception:
				_LOGGER.exception(
					"Failed to post inline finding",
					extra={"mr_iid": mr_iid, "project_id": project_id, "path": finding.path, "line": finding.line},
				)

	def _apply_labels(self, project_id: int, mr_iid: int, project: Any, labels: list[str], event_uuid: str | None) -> None:
		try:
			self.service.update_mr_labels(project, mr_iid, labels)
			_LOGGER.info("Applied MR labels", extra={"event_uuid": event_uuid, "labels": labels, "mr_iid": mr_iid, "project_id": project_id})
		except Exception:
			_LOGGER.exception("Failed to apply MR label", extra={"mr_iid": mr_iid, "project_id": project_id})


