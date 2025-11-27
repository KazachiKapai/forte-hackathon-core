from abc import ABC, abstractmethod


class TagClassifier(ABC):
	@abstractmethod
	def classify(
		self,
		title: str,
		description: str,
		diff_text: str,
		changed_files: list[tuple[str, str]],
		commit_messages: list[str],
		candidates: list[str],
	) -> list[str]:
		...


