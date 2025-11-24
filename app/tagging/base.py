from abc import ABC, abstractmethod
from typing import List, Tuple


class TagClassifier(ABC):
	@abstractmethod
	def classify(
		self,
		title: str,
		description: str,
		diff_text: str,
		changed_files: List[Tuple[str, str]],
		commit_messages: List[str],
		candidates: List[str],
	) -> List[str]:
		...


