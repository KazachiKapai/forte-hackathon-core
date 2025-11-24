from abc import ABC, abstractmethod
from typing import List, Tuple


class ReviewGenerator(ABC):
	@abstractmethod
	def generate_review(
		self,
		title: str,
		description: str,
		diff_text: str,
		changed_files: List[Tuple[str, str]],
		commit_messages: List[str],
	) -> str:
		...


