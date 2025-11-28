from abc import ABC, abstractmethod
from typing import Any


class VCSService(ABC):
	"""
	Abstract interface for a Version Control Service adapter.
	Concrete implementations should adapt their native concepts (e.g., PR vs MR)
	to these generic methods.
	"""

	# Session / identity
	def get_current_user_id(self) -> int | None: ...

	@abstractmethod
	def get_project(self, project_id: int) -> Any: ...

	@abstractmethod
	def list_membership_projects(self) -> list[Any]: ...

	@abstractmethod
	def ensure_webhook_for_project(self, project: Any, webhook_url: str, secret_token: str) -> tuple[bool, int | None]: ...

	@abstractmethod
	def collect_mr_diff_text(self, project: Any, mr_iid: int, max_chars: int = 50_000) -> str: ...

	@abstractmethod
	def post_mr_note(self, project: Any, mr_iid: int, body: str) -> None: ...

	@abstractmethod
	def review_line(self, project: Any, mr_iid: int, body: str, file_path: str, new_line: int) -> None: ...

	def get_discussion_first_note_body(self, project: Any, mr_iid: int, discussion_id: str) -> str | None: ...

	def reply_to_discussion(self, project: Any, mr_iid: int, discussion_id: str, body: str) -> None: ...

	@abstractmethod
	def get_mr_branches(self, project: Any, mr_iid: int) -> tuple[str, str]: ...

	@abstractmethod
	def get_mr_commits(self, project: Any, mr_iid: int, limit: int = 50) -> list[dict[str, Any]]: ...

	@abstractmethod
	def get_changed_files_with_content(self, project: Any, mr_iid: int, max_chars_per_file: int = 100_000) -> list[tuple[str, str]]: ...

	@abstractmethod
	def create_test_mr(self, project_id: int, target_branch: str | None = None, branch: str | None = None, file_path: str | None = None, title: str | None = None) -> dict[str, Any]: ...

	@abstractmethod
	def update_mr_labels(self, project: Any, mr_iid: int, add_labels: list[str]) -> None: ...


