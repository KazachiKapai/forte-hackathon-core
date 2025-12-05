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
from ..vcs.gitlab_service import GitLabService

_ALLOWED_ACTIONS = {"open"}
storage = get_kv_store()


@dataclass(frozen=True)
class _ReviewOutcome:
    comments: list[str]
    labels: list[str] | None
    inline_findings: list[InlineFinding]

class WebhookProcessor:
    def __init__(self, reviewer: ReviewGenerator, webhook_secret: str, discussion_agent: DiscussionAgent | None = None, tag_classifier: TagClassifier | None = None, label_candidates: list[str] | None = None, jira_service: JiraService | None = None, service: VCSService | None = None) -> None:
        self.reviewer = reviewer
        self.webhook_secret = webhook_secret
        self.discussion_agent = discussion_agent
        self.tag_classifier = tag_classifier
        self.label_candidates = label_candidates or []
        self.jira_service = jira_service
        self._service = service

    def validate_secret(self, provided: str | None) -> bool:
        return provided and provided == self.webhook_secret

    def handle_merge_request_event(self, payload: dict[str, Any]) -> bool:
        if payload["object_kind"] != "merge_request":
            return False

        attrs = payload["object_attributes"]
        action = attrs["action"]
        return action == "open"

    def process_merge_request(self, project_id: int, mr_iid: int, title: str, description: str, commit_sha: str | None = None) -> None:
        service = self._make_gitlab_service(project_id)
        project = service.get_project(project_id)
        diff_text, changed_files, commit_messages = self._gather_mr_data(service, project, project_id, mr_iid)
        description_aug = self._augment_with_tickets(project, mr_iid, title, description)
        description_aug = self._augment_with_repo_context(service, project, mr_iid, description_aug)
        outcome = self._generate_review_outcome(title, description_aug, diff_text, changed_files, commit_messages)
        self._handle_review_outcome(project_id, mr_iid, project, service, outcome, commit_sha)

    def process_note_comment(self, project_id: int, mr_iid: int, payload: dict[str, Any]) -> None:
        service = self._make_gitlab_service(project_id)

        user = payload["user"]
        if service.get_current_user_id() == int(user["id"]):
            print("original bot")
            return

        obj = payload["object_attributes"]
        discussion_id = obj["discussion_id"]
        note_body = obj["note"]
        project = service.get_project(project_id)
        first_body = service.get_discussion_first_note_body(project, mr_iid, discussion_id)
        context = self._build_discussion_context(service, project, mr_iid)
        reply = self._generate_discussion_reply(first_body or "", note_body or "", context)
        service.reply_to_discussion(project, mr_iid, discussion_id, reply)


    def _generate_discussion_reply(self, original: str, comment: str, context: str = "") -> str:
        return self.discussion_agent.generate_reply(original, comment, context)

    def _build_discussion_context(self, service: VCSService, project: Any, mr_iid: int) -> str:
        repo_ctx = self._augment_with_repo_context(service, project, mr_iid, "")
        try:
            diff_text = service.collect_mr_diff_text(project, mr_iid, max_chars=2000)
        except Exception:
            diff_text = ""
        parts: list[str] = []
        if repo_ctx:
            parts.append(repo_ctx)
        if diff_text:
            parts.append("Diff preview:\n" + diff_text[:2000])
        return "\n\n".join(p for p in parts if p).strip()

    def _gather_mr_data(self, service: VCSService, project: Any, project_id: int, mr_iid: int) -> tuple[str, list[Any], list[str]]:
        """
        Fetch diff text, changed files, and commit messages concurrently.
        Returns empty values when individual fetches fail.
        """
        with ThreadPoolExecutor(max_workers=3) as pool:
            diff_f = pool.submit(service.collect_mr_diff_text, project, mr_iid)
            files_f = pool.submit(service.get_changed_files_with_content, project, mr_iid)
            commits_f = pool.submit(service.get_mr_commits, project, mr_iid)
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

    def _augment_with_repo_context(self, service: VCSService, project: Any, mr_iid: int, description: str) -> str:
        try:
            _, ref = service.get_mr_branches(project, mr_iid)
        except Exception:
            ref = getattr(project, "default_branch", None) or "main"
        doc_text, doc_name = self._read_project_doc(service, project, ref)
        tree_listing = self._collect_repo_tree_listing(service, project, ref)
        parts: list[str] = [description or ""]
        if doc_text:
            parts.append(f"{doc_name} contents:\n{doc_text}")
        if tree_listing:
            parts.append(f"Repository tree ({ref}):\n{tree_listing}")
        return "\n\n".join(p for p in parts if p).strip()

    def _read_project_doc(self, service: VCSService, project: Any, ref: str) -> tuple[str, str]:
        for filename in ("ABOUT.md", "README.md"):
            content = service.read_file(project, filename, ref)
            if content is None:
                continue
            text = content.strip()
            if len(text) > 4000:
                text = text[:4000] + "\n... (truncated)"
            return text, filename
        return "", ""

    def _collect_repo_tree_listing(self, service: VCSService, project: Any, ref: str) -> str:
        nodes = service.list_repository_tree(project, ref, recursive=True)
        if not nodes:
            return ""
        lines: list[str] = []
        limit = 120
        for node in nodes[:limit]:
            path = (node.get("path") or node.get("name") or "").strip()
            if not path:
                continue
            node_type = node.get("type") or node.get("mode")
            suffix = f" ({node_type})" if node_type else ""
            lines.append(f"{path}{suffix}")
        remaining = len(nodes) - limit
        if remaining > 0:
            lines.append(f"... (+{remaining} more entries)")
        return "\n".join(lines)

    def _handle_review_outcome(
        self,
        project_id: int,
        mr_iid: int,
        project: Any,
        service: VCSService,
        outcome: _ReviewOutcome,
        commit_sha: str | None,
    ) -> None:
        if outcome.comments:
            version_id = self._safe_get_latest_version_id(service, project, mr_iid)
            marker = self._build_version_marker(version_id)
            if not (commit_sha and self._has_local_commit_marker(project_id, mr_iid, commit_sha)) and not (version_id and self._has_local_version_marker(project_id, mr_iid, version_id)):
                if version_id:
                    self._mark_local_version_processed(project_id, mr_iid, version_id)
                if commit_sha:
                    self._mark_local_commit_processed(project_id, mr_iid, commit_sha)

                self._post_review_comments(service, mr_iid, project, outcome.comments, marker)
                if outcome.inline_findings:
                    self._post_inline_findings(service, mr_iid, project, outcome.inline_findings)
                if outcome.labels:
                    self._apply_labels(service, mr_iid, project, outcome.labels)

    def _safe_get_latest_version_id(self, service: VCSService, project: Any, mr_iid: int) -> str | None:
        try:
            return service.get_latest_mr_version_id(project, mr_iid)  # type: ignore[attr-defined]
        except Exception:
            return None

    def _build_version_marker(self, version_id: str | None) -> str:
        return f"[ai-review v:{version_id or 'unknown'}]"

    def _post_review_comments(
        self,
        service: VCSService,
        mr_iid: int,
        project: Any,
        comments: list[str],
        marker: str,
    ) -> None:
        to_post = comments[:]
        to_post[0] = f"{marker}\n{to_post[0]}" if to_post and to_post[0] else marker
        for body in to_post:
            if body:
                service.post_mr_note(project, mr_iid, body)

    def _post_inline_findings(self, service: VCSService, mr_iid: int, project: Any, findings: list[InlineFinding]) -> None:
        for finding in findings:
            service.review_line(project, mr_iid, finding.body, finding.path, finding.line)

    def _apply_labels(self, service: VCSService, mr_iid: int, project: Any, labels: list[str]) -> None:
        service.update_mr_labels(project, mr_iid, labels)

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

    def _make_gitlab_service(self, project_id: int) -> VCSService:
        if self._service is not None:
            return self._service
        private_token = storage.get_first_token_by_project(project_id)
        return GitLabService("", private_token)


