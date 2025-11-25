from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, List


def _login_and_get_cookies(client, monkeypatch):
	from app.auth import service as auth_service
	monkeypatch.setattr(auth_service, "build_authorize_url", lambda s: f"https://gitlab.example/oauth?state={s}")
	state = parse_qs(urlparse(client.get("/auth/login").headers["Location"]).query)["state"][0]
	monkeypatch.setattr(auth_service, "exchange_code", lambda code: {"access_token": "tok"})
	monkeypatch.setattr(auth_service, "api_get_user", lambda at: {"id": 321, "username": "r", "email": "r@e", "name": "R", "avatar_url": ""})
	r_cb = client.get(f"/auth/callback?code=abc&state={state}")
	return r_cb.cookies


def test_repos_list_empty_then_sync(app_client, monkeypatch):
	client, _ = app_client
	cookies = _login_and_get_cookies(client, monkeypatch)
	# Initially empty
	r0 = client.get("/api/repositories", cookies=cookies)
	assert r0.status_code == 200
	assert r0.json()["pagination"]["total"] == 0
	# Monkeypatch sync to populate repos
	from app.repos import service as repos_service
	def fake_sync(user_id: str) -> int:
		repos_service.save_repos(user_id, [
			{"id": "repo_1", "gitlab_repo_id": 1, "name": "a", "full_path": "g/a", "visibility": "private", "description": "", "last_review_at": None},
			{"id": "repo_2", "gitlab_repo_id": 2, "name": "b", "full_path": "g/b", "visibility": "private", "description": "", "last_review_at": None},
		])
		return 2
	monkeypatch.setattr(repos_service, "sync_repositories", lambda user_id: fake_sync(user_id))
	r_sync = client.post("/api/repositories/sync", cookies=cookies)
	assert r_sync.status_code == 200
	assert r_sync.json()["synced"] == 2
	# Now list returns two
	r1 = client.get("/api/repositories", cookies=cookies)
	assert r1.status_code == 200
	assert r1.json()["pagination"]["total"] == 2
	# Search filter
	r2 = client.get("/api/repositories?search=b", cookies=cookies)
	assert r2.json()["pagination"]["total"] == 1


