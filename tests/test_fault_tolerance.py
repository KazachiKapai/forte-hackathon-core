from typing import List


def _mr_payload(iid: int = 1, action: str = "open", updated_at: str = "2025-01-01T00:00:00Z") -> dict:
	return {
		"object_kind": "merge_request",
		"object_attributes": {
			"iid": iid,
			"action": action,
			"updated_at": updated_at,
			"title": "T",
			"description": "D",
		},
		"project": {"id": 123},
	}


def test_rate_limit_429_on_burst(app_client, monkeypatch):
	# Configure very low rate limit and trust proxy for deterministic client IP
	# TODO: Update this test when infra package is removed and rate limiting is inlined
	from app.infra import ratelimit as rl
	monkeypatch.setenv("TRUST_PROXY", "true")
	monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1")
	monkeypatch.setenv("RATE_LIMIT_BURST", "1")
	# Reset singleton so env takes effect; auto-restored after test
	monkeypatch.setattr(rl, "_singleton", None, raising=False)

	client, _ = app_client
	headers = {
		"X-Gitlab-Event": "Merge Request Hook",
		"X-Gitlab-Token": "secret",
		"X-Forwarded-For": "9.9.9.9",
	}
	# First request passes
	r1 = client.post("/gitlab/webhook", headers=headers, json=_mr_payload(10))
	assert r1.status_code == 202
	# Second immediate request should be rate limited
	r2 = client.post("/gitlab/webhook", headers=headers, json=_mr_payload(11))
	assert r2.status_code == 429


def test_ip_allowlist_forbidden(app_client, monkeypatch):
	# Only allow 10.0.0.0/8 while client advertises 1.2.3.4 → should be 403
	monkeypatch.setenv("TRUST_PROXY", "true")
	monkeypatch.setenv("IP_ALLOWLIST", "10.0.0.0/8")
	client, _ = app_client
	r = client.post(
		"/gitlab/webhook",
		headers={"X-Gitlab-Event": "Merge Request Hook", "X-Gitlab-Token": "secret", "X-Forwarded-For": "1.2.3.4"},
		json=_mr_payload(20),
	)
	assert r.status_code == 403


def test_webhook_cooldown_skips_back_to_back(app_client):
	client, _ = app_client
	headers = {"X-Gitlab-Event": "Merge Request Hook", "X-Gitlab-Token": "secret"}
	pay = _mr_payload(30)
	# First queues
	r1 = client.post("/gitlab/webhook", headers=headers, json=pay)
	assert r1.status_code == 202 and r1.json()["status"] in ("queued", "duplicate_skipped", "cooldown_skipped")
	# Immediate repeat should be skipped by cooldown
	r2 = client.post("/gitlab/webhook", headers=headers, json=pay)
	assert r2.status_code == 202 and r2.json()["status"] == "cooldown_skipped"


def test_webhook_duplicate_skipped_with_uuid(app_client, monkeypatch):
	# Bypass cooldown so dedupe logic is exercised deterministically
	# TODO: Update this test when infra package is removed and cooldown is inlined
	from app.server import http as httpmod

	class AlwaysAllowCooldown:
		def acquire(self, key: str) -> bool:
			return True

	monkeypatch.setattr(httpmod, "get_cooldown_store", lambda: AlwaysAllowCooldown())

	client, _ = app_client
	headers = {
		"X-Gitlab-Event": "Merge Request Hook",
		"X-Gitlab-Token": "secret",
		"X-Gitlab-Event-UUID": "uuid-123",
	}
	pay = _mr_payload(40)
	r1 = client.post("/gitlab/webhook", headers=headers, json=pay)
	assert r1.status_code == 202 and r1.json()["status"] in ("queued", "duplicate_skipped")
	r2 = client.post("/gitlab/webhook", headers=headers, json=pay)
	assert r2.status_code == 202 and r2.json()["status"] == "duplicate_skipped"


def test_processor_handles_service_failure_gracefully():
	# get_project throws → processor should catch and return without raising
	from app.review.base import ReviewGenerator
	from app.webhook.processor import WebhookProcessor

	class FailingService:
		def get_project(self, project_id: int):
			raise RuntimeError("boom")

	class DummyReviewer(ReviewGenerator):
		def generate_review(self, title, description, diff_text, changed_files, commit_messages):
			return []

	processor = WebhookProcessor(service=FailingService(), reviewer=DummyReviewer(), webhook_secret="secret")
	# Should not raise
	processor.process_merge_request(project_id=1, mr_iid=1, title="t", description="d")


def test_processor_idempotency_marker_skips_duplicate_notes():
	from app.review.base import ReviewComment, ReviewGenerator, ReviewOutput
	from app.webhook.processor import WebhookProcessor

	marker_version = "1"

	class Note:
		def __init__(self, body: str) -> None:
			self.body = body

	class NotesList:
		def list(self, per_page: int):
			return [Note(f"[ai-review v:{marker_version}] already reviewed")]

	class MRObj:
		def __init__(self) -> None:
			self.notes = NotesList()
			self.labels = []
			self.created_at = "2025-01-01T00:00:00Z"
			self.web_url = "https://example/mr/1"

		def versions(self):
			return []

	class Proj:
		def __init__(self) -> None:
			self.mergerequests = self

		def get(self, mr_iid: int):
			return MRObj()

	class Service:
		def __init__(self) -> None:
			self.notes: List[str] = []

		def get_project(self, project_id: int):
			return Proj()

		def collect_mr_diff_text(self, project, mr_iid: int) -> str:
			return ""

		def get_changed_files_with_content(self, project, mr_iid: int):
			return []

		def get_mr_commits(self, project, mr_iid: int):
			return []

		def post_mr_note(self, project, mr_iid: int, body: str) -> None:
			self.notes.append(body)

		def get_latest_mr_version_id(self, project, mr_iid: int) -> str:
			return marker_version

	class Reviewer(ReviewGenerator):
		def generate_review(self, title, description, diff_text, changed_files, commit_messages):
			return ReviewOutput(comments=[ReviewComment(title="A", body="B")], inline_findings=[])

	svc = Service()
	processor = WebhookProcessor(service=svc, reviewer=Reviewer(), webhook_secret="secret")
	processor.process_merge_request(project_id=1, mr_iid=2, title="t", description="d")
	# Due to existing marker, no new notes should be posted
	assert svc.notes == []


def test_classifier_failure_does_not_block_posting():
	from app.review.base import ReviewComment, ReviewGenerator, ReviewOutput
	from app.webhook.processor import WebhookProcessor

	class Project:
		def __init__(self) -> None:
			self.mergerequests = self
			self._notes: List[str] = []

		class _Notes:
			def __init__(self, parent: "Project") -> None:
				self._parent = parent

			def list(self, per_page: int):
				return []

		def get(self, mr_iid: int):
			obj = self
			obj.notes = Project._Notes(self)
			obj.labels = []
			obj.created_at = "2025-01-01T00:00:00Z"
			obj.web_url = "https://example/mr/1"
			return obj

	class Service:
		def __init__(self) -> None:
			self.notes: List[str] = []

		def get_project(self, project_id: int):
			return Project()

		def collect_mr_diff_text(self, project, mr_iid: int) -> str:
			return ""

		def get_changed_files_with_content(self, project, mr_iid: int):
			return []

		def get_mr_commits(self, project, mr_iid: int):
			return []

		def post_mr_note(self, project, mr_iid: int, body: str) -> None:
			self.notes.append(body)

		def get_latest_mr_version_id(self, project, mr_iid: int) -> str:
			return "1"

	class Reviewer(ReviewGenerator):
		def generate_review(self, title, description, diff_text, changed_files, commit_messages):
			return ReviewOutput(comments=[ReviewComment(title="C", body="D")], inline_findings=[])

	class Classifier:
		def classify(self, *args, **kwargs):
			raise RuntimeError("classifier boom")

	svc = Service()
	reviewer = Reviewer()
	processor = WebhookProcessor(
		service=svc,
		reviewer=reviewer,
		webhook_secret="secret",
		tag_classifier=Classifier(),
		label_candidates=["bug", "feature"],
	)
	processor.process_merge_request(project_id=1, mr_iid=3, title="t", description="d")
	# Even though classifier fails, the review note should be posted
	assert any("ai-review" in n or "C" in n or "D" in n for n in svc.notes)


