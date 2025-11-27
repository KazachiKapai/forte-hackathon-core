from urllib.parse import parse_qs, urlparse

import pytest


def _login_and_get_cookies(client, monkeypatch):
	from app.auth import service as auth_service
	monkeypatch.setattr(auth_service, "build_authorize_url", lambda s: f"https://gitlab.example/oauth?state={s}")
	state = parse_qs(urlparse(client.get("/auth/login").headers["Location"]).query)["state"][0]
	monkeypatch.setattr(auth_service, "exchange_code", lambda code: {"access_token": "tok"})
	monkeypatch.setattr(auth_service, "api_get_user", lambda at: {"id": 999, "username": "test", "email": "t@e", "name": "T", "avatar_url": ""})
	r_cb = client.get(f"/auth/callback?code=abc&state={state}")
	return r_cb.cookies


def test_onboarding_status_initial(client_and_cookies):
	client, cookies = client_and_cookies
	client.cookies.update(cookies)
	r = client.get("/api/onboarding/status")
	assert r.status_code == 200
	body = r.json()
	assert body["completed"] is True
	assert body["has_tokens"] is False
	assert body["token_count"] == 0


def test_add_list_delete_token(app_client, monkeypatch):
	client, _ = app_client
	cookies = _login_and_get_cookies(client, monkeypatch)
	client.cookies.update(cookies)
	# Mock token validation to succeed
	from app.tokens import service as token_service
	monkeypatch.setattr(token_service, "validate_token_with_gitlab", lambda tok: (True, 12345))
	r_add = client.post("/api/onboarding/token", json={"token": "glpat-xyz", "name": "My Token"})
	assert r_add.status_code == 200
	tok_id = r_add.json()["token_id"]
	# List
	r_ls = client.get("/api/tokens")
	assert r_ls.status_code == 200
	data = r_ls.json()["data"]
	assert len(data) == 1 and data[0]["id"] == tok_id
	# Status now has tokens
	r_st = client.get("/api/onboarding/status")
	assert r_st.json()["has_tokens"] is True
	# Delete
	r_del = client.delete(f"/api/tokens/{tok_id}")
	assert r_del.status_code == 204
	# Status again
	r_st2 = client.get("/api/onboarding/status")
	assert r_st2.json()["has_tokens"] is False


# Helper fixture combining client and cookies
@pytest.fixture
def client_and_cookies(app_client, monkeypatch):
	client, _ = app_client
	cookies = _login_and_get_cookies(client, monkeypatch)
	return client, cookies


