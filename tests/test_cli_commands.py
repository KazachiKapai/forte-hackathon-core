import argparse
from typing import Dict

import main


def test_cmd_test_mr_2_invokes_service(monkeypatch, capsys):
	monkeypatch.setenv("GITLAB_TOKEN", "tok")
	monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "secret")

	class DummyService:
		def __init__(self, url, token):
			self.url = url
			self.token = token
			self.calls = []

		def create_test_mr_v2(self, **kwargs):
			self.calls.append(kwargs)
			return {"iid": 7, "project_path": "demo/path", "web_url": "https://example/mr/7", "branch": "feature/demo", "files": ["a.py"]}

	dummy_container: Dict[str, DummyService] = {}

	def fake_gitlab_service(url, token):
		svc = DummyService(url, token)
		dummy_container["svc"] = svc
		return svc

	monkeypatch.setattr(main, "GitLabService", fake_gitlab_service)

	args = argparse.Namespace(
		project_id="123",
		branch=None,
		target_branch=None,
		title=None,
		jira_project=None,
	)

	main.cmd_test_mr2(args)
	out = capsys.readouterr().out
	assert "Created MR !7" in out
	assert dummy_container["svc"].calls  # ensure create_test_mr_v2 was invoked


