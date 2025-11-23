from abc import ABC, abstractmethod


class ReviewGenerator(ABC):
	@abstractmethod
	def generate_review(self, diff_text: str, title: str, description: str) -> str:
		...


