from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from ..integrations.jira_service import JiraService
from ..review.base import InlineFinding, ReviewGenerator, ReviewOutput
from ..storage.provider import get_kv_store
from ..tagging.base import TagClassifier
from ..vcs.base import VCSService
from ..storage.json_store import load_json, save_json
from ..review.agentic.agents.discussion_agent import DiscussionAgent

_ALLOWED_ACTIONS = {"open"}


@dataclass(frozen=True)
class _ReviewOutcome:
    comments: list[str]
    labels: list[str] | None
    inline_findings: list[InlineFinding]


class WebhookProcessor:
    def __init__(self, service: VCSService, reviewer: ReviewGenerator, webhook_secret: str, discussion_agent: DiscussionAgent | None = None, tag_classifier: TagClassifier | None = None, label_candidates: list[str] | None = None, jira_service: JiraService | None = None) -> None:
        self.service = service
        self.reviewer = reviewer
        self.webhook_secret = webhook_secret
        self.discussion_agent = discussion_agent
        self.tag_classifier = tag_classifier
        self.label_candidates = label_candidates or []
        self.jira_service = jira_service

    def validate_secret(self, provided: str | None) -> bool:
        return provided and provided == self.webhook_secret

    def handle_merge_request_event(self, payload: dict[str, Any]) -> bool:
        if payload["object_kind"] != "merge_request":
            return False

        attrs = payload["object_attributes"]
        action = attrs["action"]
        return action == "open"

    def process_merge_request(self, project_id: int, mr_iid: int, title: str, description: str, commit_sha: str | None = None) -> None:
        project = self.service.get_project(project_id)
        diff_text, changed_files, commit_messages = self._gather_mr_data(project, project_id, mr_iid)
        description_aug = self._augment_with_tickets(project, mr_iid, title, description)
        outcome = self._generate_review_outcome(title, description_aug, diff_text, changed_files, commit_messages)
        self._handle_review_outcome(project_id, mr_iid, project, outcome, commit_sha)

    def process_note_comment(self, project_id: int, mr_iid: int, payload: dict[str, Any]) -> None:
        obj = payload["object_attributes"]
        discussion_id = obj["discussion_id"]
        note_body = obj["note"]
        project = self.service.get_project(project_id)
        first_body = self.service.get_discussion_first_note_body(project, mr_iid, discussion_id)
        reply = self._generate_discussion_reply(first_body or "", note_body or "")
        self.service.reply_to_discussion(project, mr_iid, discussion_id, reply)


    def _generate_discussion_reply(self, original: str, comment: str) -> str:
        return self.discussion_agent.generate_reply(original, comment)

    def _gather_mr_data(self, project: Any, project_id: int, mr_iid: int) -> tuple[str, list[Any], list[str]]:
        """
        Fetch diff text, changed files, and commit messages concurrently.
        Returns empty values when individual fetches fail.
        """
        with ThreadPoolExecutor(max_workers=3) as pool:
            diff_f = pool.submit(self.service.collect_mr_diff_text, project, mr_iid)
            files_f = pool.submit(self.service.get_changed_files_with_content, project, mr_iid)
            commits_f = pool.submit(self.service.get_mr_commits, project, mr_iid)
            diff_text = diff_f.result()
            changed_files = files_f.result()
            commit_objs = commits_f.result()
            commit_messages = [c.get("message", "") for c in commit_objs if isinstance(c, dict) and c.get("message")]
        return diff_text, changed_files, commit_messages

    def _review_and_classify(
        self,
        title: str,
        description: str,
        diff_text: str,
        changed_files: list[Any],
        commit_messages: list[str],
    ) -> tuple[list[str], list[str] | None, list[InlineFinding]]:
        review_comments: list[str] = []
        label_choice: list[str] | None = None
        inline_findings: list[InlineFinding] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            review_f = pool.submit(self.reviewer.generate_review, title, description, diff_text, changed_files, commit_messages)
            if self.tag_classifier and self.label_candidates:
                label_f = pool.submit(self.tag_classifier.classify, title, description, diff_text, changed_files, commit_messages, self.label_candidates)
            else:
                label_f = None
            review_res = review_f.result()
            if isinstance(review_res, ReviewOutput):
                comments = review_res.comments or []
                review_comments = [c.to_markdown() for c in comments if c]
                inline_findings = list(review_res.inline_findings or [])
            elif isinstance(review_res, list):
                review_comments = [c.to_markdown() if hasattr(c, "to_markdown") else str(c) for c in review_res if c]
            elif review_res:
                review_comments = [str(review_res)]
            if label_f is not None:
                label_choice = label_f.result()

        return review_comments, label_choice, inline_findings

    def _augment_with_tickets(self, project: Any, mr_iid: int, title: str, description: str) -> str:
        """
        Append related Jira tickets to the MR description when Jira is configured.
        Returns the original description on any error or when Jira is disabled.
        """
        if not self.jira_service:
            return description
        mr = project.mergerequests.get(mr_iid)
        labels = list(getattr(mr, "labels", []) or [])
        created_at = getattr(mr, "created_at", None)
        web_url = getattr(mr, "web_url", None)
        issues = self.jira_service.search_related_issues(
            title=title,
            description=description or "",
            labels=labels,
            created_at_iso=created_at,
            mr_url=web_url,
        )
        if not issues:
            return description
        lines: list[str] = ["Related Tickets:"]
        for it in issues:
            lines.append(f"- {it.get('key')} [{it.get('status')}]: {it.get('summary')} ({it.get('url')})")
        return (description or "") + "\n\n" + "\n".join(lines)

    def _generate_review_outcome(
        self,
        title: str,
        description: str,
        diff_text: str,
        changed_files: list[Any],
        commit_messages: list[str],
    ) -> _ReviewOutcome:
        comments, labels, findings = self._review_and_classify(
            title, description, diff_text, changed_files, commit_messages,
        )
        return _ReviewOutcome(comments=comments, labels=labels, inline_findings=findings)

    def _handle_review_outcome(
        self,
        project_id: int,
        mr_iid: int,
        project: Any,
        outcome: _ReviewOutcome,
        commit_sha: str | None,
    ) -> None:
        if outcome.comments:
            version_id = self._safe_get_latest_version_id(project, mr_iid)
            marker = self._build_version_marker(version_id)
            if not (commit_sha and self._has_local_commit_marker(project_id, mr_iid, commit_sha)) and not (version_id and self._has_local_version_marker(project_id, mr_iid, version_id)):
                if version_id:
                    self._mark_local_version_processed(project_id, mr_iid, version_id)
                if commit_sha:
                    self._mark_local_commit_processed(project_id, mr_iid, commit_sha)

                self._post_review_comments(mr_iid, project, outcome.comments, marker)
                if outcome.inline_findings:
                    self._post_inline_findings(mr_iid, project, outcome.inline_findings)
                if outcome.labels:
                    self._apply_labels(mr_iid, project, outcome.labels)

    def _safe_get_latest_version_id(self, project: Any, mr_iid: int) -> str | None:
        try:
            return self.service.get_latest_mr_version_id(project, mr_iid)  # type: ignore[attr-defined]
        except Exception:
            return None

    def _build_version_marker(self, version_id: str | None) -> str:
        return f"[ai-review v:{version_id or 'unknown'}]"

    def _post_review_comments(
        self,
        mr_iid: int,
        project: Any,
        comments: list[str],
        marker: str,
    ) -> None:
        to_post = comments[:]
        to_post[0] = f"{marker}\n{to_post[0]}" if to_post and to_post[0] else marker
        for body in to_post:
            if body:
                self.service.post_mr_note(project, mr_iid, body)

    def _post_inline_findings(self, mr_iid: int, project: Any, findings: list[InlineFinding]) -> None:
        for finding in findings:
            self.service.review_line(project, mr_iid, finding.body, finding.path, finding.line)

    def _apply_labels(self, mr_iid: int, project: Any, labels: list[str]) -> None:
        self.service.update_mr_labels(project, mr_iid, labels)

    def _version_store(self) -> dict[str, list[str]]:
        return load_json("mr_versions.json", {})

    def _has_local_version_marker(self, project_id: int, mr_iid: int, version_id: str) -> bool:
        store = self._version_store()
        key = f"{project_id}:{mr_iid}"
        seen: list[str] = store.get(key, [])
        return version_id in set(seen)

    def _mark_local_version_processed(self, project_id: int, mr_iid: int, version_id: str) -> None:
        if not version_id:
            return
        store = self._version_store()
        key = f"{project_id}:{mr_iid}"
        seen: list[str] = store.get(key, [])
        if version_id not in seen:
            seen.append(version_id)
            store[key] = seen
            save_json("mr_versions.json", store)

    def _commit_store(self) -> dict[str, list[str]]:
        return load_json("mr_commits.json", {})

    def _has_local_commit_marker(self, project_id: int, mr_iid: int, commit_sha: str) -> bool:
        if not commit_sha:
            return False
        store = self._commit_store()
        key = f"{project_id}:{mr_iid}"
        seen: list[str] = store.get(key, [])
        return commit_sha in set(seen)

    def _mark_local_commit_processed(self, project_id: int, mr_iid: int, commit_sha: str) -> None:
        if not commit_sha:
            return
        store = self._commit_store()
        key = f"{project_id}:{mr_iid}"
        seen: list[str] = store.get(key, [])
        if commit_sha not in seen:
            seen.append(commit_sha)
            store[key] = seen
            save_json("mr_commits.json", store)


