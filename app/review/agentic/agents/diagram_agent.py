from ..models import AgentPayload
from .base import BaseAgent


class DiagramAgent(BaseAgent):
	def __init__(self) -> None:
		super().__init__(key="architecture_diagram", title="Architecture Diagram")

	def build_prompt(self, payload: AgentPayload) -> str:
		files_blob = payload.files_blob(max_files=12, max_chars_per_file=800)
		return (
			"You are a system designer. Explain MR changes with a valid Mermaid diagram.\n"
			"STRICT rules:\n"
			"- Return ONLY a Mermaid code block, nothing else.\n"
			"- Prefer 'graph TD' for components or 'sequenceDiagram' for interactions.\n"
			"- Use concise node names, show data flow directions, highlight changed areas.\n"
			"- Do not invent components beyond what files imply.\n\n"
			f"Project Architecture Notes:\n{payload.project_context.architecture}\n\n"
			f"Changed Files:\n{files_blob}\n"
		)

	def postprocess(self, output: str) -> str:
		text = super().postprocess(output)
		if "```mermaid" in text.lower():
			return text
		return f"```mermaid\n{text}\n```"



