import json


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


