from typing import Any, Dict, List, Optional, Tuple
import time
import gitlab
import base64
from .base import VCSService


class GitLabService(VCSService):
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

	def get_mr_branches(self, project: Any, mr_iid: int) -> Tuple[str, str]:
		mr = project.mergerequests.get(mr_iid)
		return mr.source_branch, mr.target_branch

	def get_mr_commits(self, project: Any, mr_iid: int, limit: int = 50) -> List[Dict[str, Any]]:
		mr = project.mergerequests.get(mr_iid)
		try:
			commits = mr.commits()
		except Exception:
			# Fallback: use source branch commits if MR API missing
			source = mr.source_branch
			commits = project.commits.list(ref_name=source, per_page=limit)
		# Normalize to dicts; RESTObjectList may not be sliceable
		result: List[Dict[str, Any]] = []
		count = 0
		for c in commits:
			if isinstance(c, dict):
				msg = c.get("message") or c.get("title") or ""
				sha = c.get("id") or c.get("short_id")
			else:
				msg = getattr(c, "message", None) or getattr(c, "title", "") or ""
				sha = getattr(c, "id", None) or getattr(c, "short_id", None)
			result.append({"id": sha, "message": msg})
			count += 1
			if count >= limit:
				break
		return result

	def get_changed_files_with_content(self, project: Any, mr_iid: int, max_chars_per_file: int = 100_000) -> List[Tuple[str, str]]:
		"""
		Returns list of (path, content) for changed files using the MR's source branch.
		Skips deleted files. Content is truncated per file for safety.
		"""
		mr = project.mergerequests.get(mr_iid)
		source_branch = mr.source_branch
		diffs_page = mr.diffs.list()
		if not diffs_page:
			return []
		diff_obj = mr.diffs.get(diffs_page[0].get_id())
		paths: List[str] = []
		for d in diff_obj.diffs:
			if d.get("deleted_file"):
				continue
			path = d.get("new_path") or d.get("old_path")
			if path and path not in paths:
				paths.append(path)
		results: List[Tuple[str, str]] = []
		for path in paths:
			try:
				f = project.files.get(file_path=path, ref=source_branch)
				content_b64 = getattr(f, "content", "")
				if content_b64:
					raw = base64.b64decode(content_b64.encode("utf-8"), validate=False)
					text = raw.decode("utf-8", errors="replace")
				else:
					text = ""
				if len(text) > max_chars_per_file:
					text = text[:max_chars_per_file]
				results.append((path, text))
			except Exception:
				# Ignore files we cannot fetch (binary or too large)
				continue
		return results

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


