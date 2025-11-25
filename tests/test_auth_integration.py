from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, List
import importlib


def test_health_ok(app_client):
	client, _ = app_client
	r = client.get("/health")
	assert r.status_code == 200
	assert r.json() == {"status": "ok"}


def test_auth_login_redirects(app_client, monkeypatch):
	client, _ = app_client
	# Stub authorize URL to deterministic
	from app.auth import service as auth_service
	def fake_build_authorize_url(state: str) -> str:
		return f"https://gitlab.example/oauth?state={state}"
	monkeypatch.setattr(auth_service, "build_authorize_url", fake_build_authorize_url)
	r = client.get("/auth/login")
	assert r.status_code in (302, 307)
	loc = r.headers["Location"]
	assert "https://gitlab.example/oauth" in loc
	# State should have been recorded
	state = parse_qs(urlparse(loc).query)["state"][0]
	from app.storage import json_store as js
	states: Dict[str, Any] = js.load_json("oauth_state.json", {})
	assert state in states


def test_auth_callback_sets_session_and_redirects(app_client, monkeypatch):
	client, _ = app_client
	# Generate a state via login
	from app.auth import service as auth_service
	monkeypatch.setattr(auth_service, "build_authorize_url", lambda s: f"https://gitlab.example/oauth?state={s}")
	r_login = client.get("/auth/login")
	state = parse_qs(urlparse(r_login.headers["Location"]).query)["state"][0]
	# Stub exchange and user fetch
	monkeypatch.setattr(auth_service, "exchange_code", lambda code: {"access_token": "tok"})
	monkeypatch.setattr(auth_service, "api_get_user", lambda at: {"id": 123, "username": "jdoe", "email": "j@e", "name": "John", "avatar_url": "http://a"})
	r = client.get(f"/auth/callback?code=abc&state={state}")
	assert r.status_code in (302, 307)
	assert r.headers["Location"].endswith("/onboarding")
	# Cookie should be set
	assert any(c.startswith("sid=") for c in r.headers.get("set-cookie", "").split(";"))
	# /auth/me should work with returned cookie
	cookies = r.cookies
	r_me = client.get("/auth/me", cookies=cookies)
	assert r_me.status_code == 200
	body = r_me.json()
	assert body["username"] == "jdoe"


def test_auth_logout_clears_session(app_client, monkeypatch):
	client, _ = app_client
	# Create session
	from app.auth import service as auth_service
	monkeypatch.setattr(auth_service, "build_authorize_url", lambda s: f"https://gitlab.example/oauth?state={s}")
	state = parse_qs(urlparse(client.get("/auth/login").headers["Location"]).query)["state"][0]
	monkeypatch.setattr(auth_service, "exchange_code", lambda code: {"access_token": "tok"})
	monkeypatch.setattr(auth_service, "api_get_user", lambda at: {"id": 7, "username": "u", "email": "u@e", "name": "U", "avatar_url": ""})
	r_cb = client.get(f"/auth/callback?code=abc&state={state}")
	cookies = r_cb.cookies
	# Logout
	r_out = client.post("/auth/logout", cookies=cookies)
	assert r_out.status_code == 200
	# Subsequent me is unauthorized
	r_me = client.get("/auth/me", cookies=cookies)
	assert r_me.status_code == 401


