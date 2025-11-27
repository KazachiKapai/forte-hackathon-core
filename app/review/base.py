from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ReviewComment:
	title: str
	body: str

	def to_markdown(self) -> str:
		if self.title:
			return f"### {self.title}\n\n{self.body}".strip()
		return self.body.strip()


@dataclass
class InlineFinding:
	path: str
	line: int
	body: str
	source: str = ""


@dataclass
class ReviewOutput:
	comments: list[ReviewComment] = field(default_factory=list)
	inline_findings: list[InlineFinding] = field(default_factory=list)


class ReviewGenerator(ABC):
	@abstractmethod
	def generate_review(
		self,
		title: str,
		description: str,
		diff_text: str,
		changed_files: list[tuple[str, str]],
		commit_messages: list[str],
	) -> ReviewOutput:
		...


