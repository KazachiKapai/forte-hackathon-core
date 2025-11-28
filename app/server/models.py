from typing import Literal, Optional

from pydantic import BaseModel


StatusValue = Literal["ok", "ignored", "queued", "cooldown_skipped", "duplicate_skipped", "error"]


class StatusResponse(BaseModel):
	status: StatusValue
	reason: Optional[str] = None
	validated: Optional[bool] = None
	code: Optional[int] = None
	message: Optional[str] = None


class OnboardingStatus(BaseModel):
	completed: bool
	has_tokens: bool
	token_count: int


class AddTokenResponse(BaseModel):
	success: bool
	message: str
	token_id: str


class TokenItem(BaseModel):
	id: str | int | None
	name: str | None = None
	project_id: int | None = None
	scopes: list[str] = []
	created_at: str | None = None
	last_used_at: str | None = None


class TokensListResponse(BaseModel):
	data: list[TokenItem]

class UserInfo(BaseModel):
	id: str
	username: str
	email: str | None = None
	name: str | None = None
	avatar_url: str | None = None


class Pagination(BaseModel):
	page: int
	per_page: int
	total: int


class RepoItem(BaseModel):
	id: str | int | None = None
	gitlab_repo_id: int | None = None
	name: str | None = None
	full_path: str | None = None
	visibility: str | None = None
	description: str | None = None
	last_review_at: str | None = None


class ReposListResponse(BaseModel):
	data: list[RepoItem]
	pagination: Pagination


class SyncRepositoriesResponse(BaseModel):
	synced: int


