from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class VCSService(ABC):
	"""
	Abstract interface for a Version Control Service adapter.
	Concrete implementations should adapt their native concepts (e.g., PR vs MR)
	to these generic methods.
	"""

	@abstractmethod
	def get_project(self, project_id: int) -> Any: ...

	@abstractmethod
	def list_membership_projects(self) -> List[Any]: ...

	@abstractmethod
	def ensure_webhook_for_project(self, project: Any, webhook_url: str, secret_token: str) -> Tuple[bool, Optional[int]]: ...

	@abstractmethod
	def collect_mr_diff_text(self, project: Any, mr_iid: int, max_chars: int = 50_000) -> str: ...

	@abstractmethod
	def post_mr_note(self, project: Any, mr_iid: int, body: str) -> None: ...

	@abstractmethod
	def get_mr_branches(self, project: Any, mr_iid: int) -> Tuple[str, str]: ...

	@abstractmethod
	def get_mr_commits(self, project: Any, mr_iid: int, limit: int = 50) -> List[Dict[str, Any]]: ...

	@abstractmethod
	def get_changed_files_with_content(self, project: Any, mr_iid: int, max_chars_per_file: int = 100_000) -> List[Tuple[str, str]]: ...

	@abstractmethod
	def create_test_mr(self, project_id: int, target_branch: Optional[str] = None, branch: Optional[str] = None, file_path: Optional[str] = None, title: Optional[str] = None) -> Dict[str, Any]: ...


