from typing import Any, Dict, List, Optional, Tuple
from .base import VCSService


class GitHubService(VCSService):
	"""
	Lightweight skeleton for future GitHub support.
	Maps GitHub Pull Requests to the MR-oriented interface.
	Not wired into the app yet.
	"""

	def __init__(self, api_base_url: str, token: str) -> None:
		self.api_base_url = api_base_url
		self.token = token
		# Intentionally not importing PyGithub to avoid new mandatory dependency.
		# Implementations can use requests or PyGithub in the future.

	def get_project(self, project_id: int) -> Any:
		raise NotImplementedError("GitHubService.get_project is not implemented yet")

	def list_membership_projects(self) -> List[Any]:
		raise NotImplementedError("GitHubService.list_membership_projects is not implemented yet")

	def ensure_webhook_for_project(self, project: Any, webhook_url: str, secret_token: str) -> Tuple[bool, Optional[int]]:
		# Would create/update a repo webhook with pull_request events on GitHub
		raise NotImplementedError("GitHubService.ensure_webhook_for_project is not implemented yet")

	def collect_mr_diff_text(self, project: Any, mr_iid: int, max_chars: int = 50_000) -> str:
		# Would fetch PR diff via GitHub API: GET /repos/{owner}/{repo}/pulls/{pull_number}
		raise NotImplementedError("GitHubService.collect_mr_diff_text is not implemented yet")

	def post_mr_note(self, project: Any, mr_iid: int, body: str) -> None:
		# Would post a PR comment: POST /repos/{owner}/{repo}/issues/{issue_number}/comments
		raise NotImplementedError("GitHubService.post_mr_note is not implemented yet")

	def get_mr_branches(self, project: Any, mr_iid: int) -> Tuple[str, str]:
		# Would map to PR head.ref and base.ref
		raise NotImplementedError("GitHubService.get_mr_branches is not implemented yet")

	def get_mr_commits(self, project: Any, mr_iid: int, limit: int = 50) -> List[Dict[str, Any]]:
		# GET /repos/{owner}/{repo}/pulls/{pull_number}/commits
		raise NotImplementedError("GitHubService.get_mr_commits is not implemented yet")

	def get_changed_files_with_content(self, project: Any, mr_iid: int, max_chars_per_file: int = 100_000) -> List[Tuple[str, str]]:
		# GET /repos/{owner}/{repo}/pulls/{pull_number}/files then fetch file blobs from head SHA
		raise NotImplementedError("GitHubService.get_changed_files_with_content is not implemented yet")

	def create_test_mr(self, project_id: int, target_branch: Optional[str] = None, branch: Optional[str] = None, file_path: Optional[str] = None, title: Optional[str] = None) -> Dict[str, Any]:
		# Would create a branch, commit, and open a PR
		raise NotImplementedError("GitHubService.create_test_mr is not implemented yet")


