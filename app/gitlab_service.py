from typing import Any, Dict, List, Optional, Tuple
import time
import gitlab


class GitLabService:
	def __init__(self, base_url: str, private_token: str) -> None:
		self.client = gitlab.Gitlab(base_url, private_token=private_token)

	def get_project(self, project_id: int) -> Any:
		return self.client.projects.get(project_id)

	def list_membership_projects(self) -> List[Any]:
		return self.client.projects.list(membership=True, all=True)

	def ensure_webhook_for_project(self, project: Any, webhook_url: str, secret_token: str) -> Tuple[bool, Optional[int]]:
		existing_hooks = project.hooks.list(all=True)
		for hook in existing_hooks:
			if hook.url == webhook_url and getattr(hook, "merge_requests_events", False):
				if getattr(hook, "token", None) != secret_token:
					hook.token = secret_token
					hook.save()
				return (False, hook.id)
		new_hook = project.hooks.create(
			{
				"url": webhook_url,
				"enable_ssl_verification": True,
				"token": secret_token,
				"push_events": False,
				"tag_push_events": False,
				"merge_requests_events": True,
				"note_events": False,
				"job_events": False,
				"pipeline_events": False,
				"wiki_page_events": False,
			}
		)
		return (True, new_hook.id)

	def collect_mr_diff_text(self, project: Any, mr_iid: int, max_chars: int = 50_000) -> str:
		mr = project.mergerequests.get(mr_iid)
		diffs_page = mr.diffs.list()
		if not diffs_page:
			return "No diffs found for this merge request."
		diff_obj = mr.diffs.get(diffs_page[0].get_id())
		collected: List[str] = []
		total_len = 0
		for d in diff_obj.diffs:
			one = f"File: {d.get('new_path') or d.get('old_path')}\n{d.get('diff', '')}\n"
			if total_len + len(one) > max_chars:
				collected.append(one[: max(0, max_chars - total_len)])
				break
			collected.append(one)
			total_len += len(one)
		return "\n".join(collected)

	def post_mr_note(self, project: Any, mr_iid: int, body: str) -> None:
		mr = project.mergerequests.get(mr_iid)
		mr.notes.create({"body": body})

	def create_test_mr(self, project_id: int, target_branch: Optional[str] = None, branch: Optional[str] = None, file_path: Optional[str] = None, title: Optional[str] = None) -> Dict[str, Any]:
		project = self.client.projects.get(project_id)
		t_branch = target_branch or getattr(project, "default_branch", None) or "main"
		branch_name = branch or f"test-webhook-{int(time.time())}"
		path = file_path or "webhook_test.txt"
		mr_title = title or f"Webhook Test MR {branch_name}"
		try:
			project.branches.create({"branch": branch_name, "ref": t_branch})
		except Exception:
			pass
		project.commits.create(
			{
				"branch": branch_name,
				"commit_message": "test: trigger webhook",
				"actions": [{"action": "create", "file_path": path, "content": f"hello webhook {int(time.time())}\n"}],
			}
		)
		mr = project.mergerequests.create({"source_branch": branch_name, "target_branch": t_branch, "title": mr_title})
		return {"iid": mr.iid, "web_url": getattr(mr, "web_url", None), "project_path": project.path_with_namespace}


