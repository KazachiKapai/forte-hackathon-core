import os
import sys
from pathlib import Path
import importlib
import types
import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path so `import app` works under pytest
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
	sys.path.insert(0, str(ROOT_DIR))

class FakeProcessor:
	def __init__(self, secret: str = "secret") -> None:
		self._secret = secret
		self.process_calls = []
		self.handle_result = {"status": "ok", "validated": True}

	def validate_secret(self, provided):
		if not provided or provided != self._secret:
			raise PermissionError("Invalid")

	def handle_merge_request_event(self, payload):
		return self.handle_result

	def process_merge_request(self, project_id: int, mr_iid: int, title: str, description: str, event_uuid: str = None):
		self.process_calls.append((project_id, mr_iid, title, description, event_uuid))


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
	# Force isolated data dir per test
	monkeypatch.setenv("DATA_DIR", str(tmp_path))
	# Reload storage to pick up new DATA_DIR
	from app.storage import json_store as js
	importlib.reload(js)
	return tmp_path


@pytest.fixture
def app_client(tmp_data_dir, monkeypatch):
	# Set default frontend URL to allow CORS and redirects
	monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")
	# Provide dummy OAuth env so /auth/login works
	monkeypatch.setenv("GITLAB_OAUTH_CLIENT_ID", "cid")
	monkeypatch.setenv("GITLAB_OAUTH_CLIENT_SECRET", "csecret")
	monkeypatch.setenv("GITLAB_OAUTH_REDIRECT_URI", "http://localhost:8080/auth/callback")
	# Reload auth service (reads env)
	from app.auth import service as auth_service
	importlib.reload(auth_service)
	# Build app with fake webhook processor
	from app.server.http import create_app
	fp = FakeProcessor()
	app = create_app(fp)
	client = TestClient(app, follow_redirects=False)
	return client, fp


