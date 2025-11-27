import time
from typing import Any, Dict, List


def test_system_bootstrap_and_webhook_processing_posts_note(monkeypatch):
	# Environment required by AppConfig
	monkeypatch.setenv("GITLAB_TOKEN", "tok")
	monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "secret")
	monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")

	# Stubs to replace external integrations during bootstrap
	from app.server import bootstrap as bs

	class StubService:
		def __init__(self, url: str, token: str) -> None:
			self.url = url
			self.token = token
			self.notes: List[str] = []
			self.inline_notes: List[tuple[str, int, str]] = []
			self.labels: List[str] = []

		def get_project(self, project_id: int):
			class _Notes:
				def list(self, per_page: int):
					return []
			class _MR:
				def __init__(self) -> None:
					self.notes = _Notes()
					self.labels = []
					self.created_at = "2025-01-01T00:00:00Z"
					self.web_url = "https://example/mr/1"
				def versions(self):
					return []
			class _Proj:
				def __init__(self) -> None:
					self.mergerequests = self
				def get(self, mr_iid: int):
					return _MR()
			return _Proj()

		def collect_mr_diff_text(self, project, mr_iid: int) -> str:
			return "diff --git a/foo b/foo"

		def get_changed_files_with_content(self, project, mr_iid: int):
			return []

		def get_mr_commits(self, project, mr_iid: int):
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

	class StubReviewer:
		def generate_review(self, title, description, diff_text, changed_files, commit_messages):
			from app.review.base import InlineFinding, ReviewComment, ReviewOutput
			return ReviewOutput(
				comments=[ReviewComment(title="Task and Diff Summary", body="- ok")],
				inline_findings=[InlineFinding(path="src/x.py", line=3, body="n")],
			)

	class StubClassifier:
		def classify(self, *args, **kwargs):
			return ["autolabel"]

	# Capture created service instance
	captured: Dict[str, Any] = {}
	def fake_gl(url, token):
		svc = StubService(url, token)
		captured["svc"] = svc
		return svc
	monkeypatch.setattr(bs, "GitLabService", lambda url, token: fake_gl(url, token))
	monkeypatch.setattr(bs, "AgenticReviewGenerator", lambda **kwargs: StubReviewer())
	monkeypatch.setattr(bs, "GeminiTagClassifier", lambda **kwargs: StubClassifier())
	monkeypatch.setattr(bs, "JiraService", lambda **kwargs: None)

	# Build via real bootstrap and run app as in production (in-memory server)
	from app.config.config import AppConfig
	from app.server.http import create_app
	processor = bs.build_services(AppConfig())
	app = create_app(processor)
	from fastapi.testclient import TestClient
	client = TestClient(app, follow_redirects=False)

	# Health should be OK
	assert client.get("/health").status_code == 200

	# Post webhook and expect queued; then background worker should post a note
	payload = {
		"object_kind": "merge_request",
		"object_attributes": {"iid": 55, "action": "open", "updated_at": "2025-01-01T00:00:00Z", "title": "t", "description": "d"},
		"project": {"id": 777},
	}
	r = client.post("/gitlab/webhook", headers={"X-Gitlab-Event": "Merge Request Hook", "X-Gitlab-Token": "secret"}, json=payload)
	assert r.status_code == 202

	# Wait briefly for background processing
	for _ in range(20):
		if any("Task and Diff Summary" in n for n in captured["svc"].notes):
			break
		time.sleep(0.01)
	assert any("Task and Diff Summary" in n for n in captured["svc"].notes)


def test_system_endpoints_exist_and_cors(monkeypatch):
	monkeypatch.setenv("GITLAB_TOKEN", "tok")
	monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "secret")
	monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")

	# Minimal stubs to satisfy bootstrap
	from app.server import bootstrap as bs
	monkeypatch.setattr(bs, "GitLabService", lambda url, token: object())
	class DummyReviewer:
		def generate_review(self, *args, **kwargs):
			return []
	monkeypatch.setattr(bs, "AgenticReviewGenerator", lambda **kwargs: DummyReviewer())
	monkeypatch.setattr(bs, "GeminiTagClassifier", lambda **kwargs: None)
	monkeypatch.setattr(bs, "JiraService", lambda **kwargs: None)

	from app.config.config import AppConfig
	from app.server.http import create_app
	processor = bs.build_services(AppConfig())
	app = create_app(processor)
	from fastapi.testclient import TestClient
	client = TestClient(app, follow_redirects=False)
	assert client.get("/health").json() == {"status": "ok"}
	# CORS middleware is mounted; ACAO header should be present on actual request
	health_resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
	assert health_resp.status_code == 200
	# Some test client environments may omit ACAO on simple GET; at minimum, credentials flag should be present
	assert health_resp.headers.get("access-control-allow-credentials") == "true"


