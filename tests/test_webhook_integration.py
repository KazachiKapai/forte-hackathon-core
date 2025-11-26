import json
from typing import List


def test_webhook_ignored_when_wrong_event(app_client):
	client, _ = app_client
	r = client.post(
		"/gitlab/webhook",
		headers={"X-Gitlab-Event": "Push Hook", "X-Gitlab-Token": "secret"},
		json={"object_kind": "push"},
	)
	assert r.status_code == 202
	assert r.json()["status"] == "ignored"


def test_webhook_auth_and_queue(app_client):
	client, fp = app_client
	payload = {
		"object_kind": "merge_request",
		"object_attributes": {"iid": 10, "action": "open", "updated_at": "2025-01-01T00:00:00Z"},
		"project": {"id": 123},
	}
	r = client.post(
		"/gitlab/webhook",
		headers={"X-Gitlab-Event": "Merge Request Hook", "X-Gitlab-Token": "secret"},
		json=payload,
	)
	assert r.status_code == 202
	assert r.json()["status"] in ("queued", "duplicate_skipped", "cooldown_skipped")


def test_webhook_invalid_token_401(app_client):
	client, _ = app_client
	r = client.post(
		"/gitlab/webhook",
		headers={"X-Gitlab-Event": "Merge Request Hook", "X-Gitlab-Token": "wrong"},
		json={"object_kind": "merge_request", "object_attributes": {"iid": 1, "action": "open", "updated_at": ""}, "project": {"id": 1}},
	)
	assert r.status_code == 401


def test_webhook_handle_error_bubbles_status(app_client):
	client, fp = app_client
	# Make handler return error
	fp.handle_result = {"status": "error", "code": 400, "message": "bad"}
	r = client.post(
		"/gitlab/webhook",
		headers={"X-Gitlab-Event": "Merge Request Hook", "X-Gitlab-Token": "secret"},
		json={"object_kind": "merge_request", "object_attributes": {"iid": 1, "action": "open", "updated_at": ""}, "project": {"id": 1}},
	)
	assert r.status_code == 400


def test_webhook_processor_posts_inline_findings():
	from app.review.base import InlineFinding, ReviewComment, ReviewGenerator, ReviewOutput
	from app.webhook.processor import WebhookProcessor

	class StubNotes:
		def list(self, per_page: int):
			return []

	class StubMR:
		def __init__(self) -> None:
			self.notes = StubNotes()
			self.labels = []
			self.created_at = "2025-01-01T00:00:00Z"
			self.web_url = "https://example/mr/1"

		def versions(self):
			return []

	class StubProject:
		def __init__(self) -> None:
			self.mergerequests = self

		def get(self, mr_iid: int):
			return StubMR()

	class StubService:
		def __init__(self) -> None:
			self.notes = []
			self.inline_notes = []
			self.labels = []

		def get_project(self, project_id: int):
			return StubProject()

		def collect_mr_diff_text(self, project, mr_iid: int, max_chars: int = 50_000) -> str:
			return "diff --git a/foo b/foo"

		def get_changed_files_with_content(self, project, mr_iid: int, max_chars_per_file: int = 100_000):
			return []

		def get_mr_commits(self, project, mr_iid: int, limit: int = 50):
			return []

		def post_mr_note(self, project, mr_iid: int, body: str) -> None:
			self.notes.append(body)

		def review_line(self, project, mr_iid: int, body: str, file_path: str, new_line: int) -> None:
			self.inline_notes.append((file_path, new_line, body))

		def get_latest_mr_version_id(self, project, mr_iid: int) -> str:
			return "1"

		def update_mr_labels(self, project, mr_iid: int, add_labels: List[str]) -> None:
			self.labels.extend(add_labels)

		def ensure_webhook_for_project(self, project, webhook_url: str, secret_token: str):
			return (False, None)

		def list_membership_projects(self):
			return []

		def create_test_mr(self, *args, **kwargs):
			return {}

		def create_test_mr_v2(self, *args, **kwargs):
			return {}

		def get_mr_branches(self, project, mr_iid: int):
			return ("main", "main")

	class DummyReviewer(ReviewGenerator):
		def generate_review(self, title, description, diff_text, changed_files, commit_messages):
			return ReviewOutput(
				comments=[ReviewComment(title="Task and Diff Summary", body="- bullet")],
				inline_findings=[InlineFinding(path="src/foo.py", line=5, body="Rename tmp var")],
			)

	service = StubService()
	processor = WebhookProcessor(service=service, reviewer=DummyReviewer(), webhook_secret="secret")
	processor.process_merge_request(project_id=1, mr_iid=2, title="Demo", description="Desc")

	assert any("Task and Diff Summary" in note for note in service.notes)
	assert service.inline_notes == [("src/foo.py", 5, "Rename tmp var")]


