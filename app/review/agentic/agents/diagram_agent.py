from .base import BaseAgent
from ..models import AgentPayload


class DiagramAgent(BaseAgent):
	def __init__(self) -> None:
		super().__init__(key="architecture_diagram", title="Architecture Diagram")

	def build_prompt(self, payload: AgentPayload) -> str:
		files_blob = payload.files_blob(max_files=12, max_chars_per_file=800)
		return (
			"You are a system designer who explains merge request changes with a Mermaid diagram.\n"
			"Produce a flowchart or sequence diagram that shows key components, services, and data flows touched by this diff.\n"
			"Use concise node names and indicate directions of data.\n"
			"Return ONLY a Mermaid code block, nothing else.\n\n"
			f"Project Architecture Notes:\n{payload.project_context.architecture}\n\n"
			f"Changed Files:\n{files_blob}\n"
		)

	def postprocess(self, output: str) -> str:
		text = super().postprocess(output)
		if "```mermaid" in text.lower():
			return text
		return f"```mermaid\n{text}\n```"



