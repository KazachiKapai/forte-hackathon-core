from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ReviewComment:
	title: str
	body: str

	def to_markdown(self) -> str:
		if self.title:
			return f"### {self.title}\n\n{self.body}".strip()
		return self.body.strip()


class ReviewGenerator(ABC):
	@abstractmethod
	def generate_review(
		self,
		title: str,
		description: str,
		diff_text: str,
		changed_files: List[Tuple[str, str]],
		commit_messages: List[str],
	) -> List[ReviewComment]:
		...


