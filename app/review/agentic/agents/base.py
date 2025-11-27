from abc import ABC, abstractmethod

from ..llm import LLMClient
from ..models import AgentPayload, AgentResult


class BaseAgent(ABC):
	def __init__(self, key: str, title: str) -> None:
		self.key = key
		self.title = title

	@abstractmethod
	def build_prompt(self, payload: AgentPayload) -> str: ...

	def postprocess(self, output: str) -> str:
		return output.strip()

	def parse_output(self, output: str) -> AgentResult:
		content = self.postprocess(output)
		return AgentResult(key=self.key, content=content, success=True)

	def execute(self, client: LLMClient, payload: AgentPayload) -> AgentResult:
		prompt = self.build_prompt(payload)
		raw = client.generate(prompt)
		return self.parse_output(raw)

	def failure(self, error: Exception) -> AgentResult:
		return AgentResult(key=self.key, success=False, error=str(error))



