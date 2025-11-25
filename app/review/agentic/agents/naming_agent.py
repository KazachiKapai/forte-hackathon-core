from .base import BaseAgent
from ..models import AgentPayload


class NamingQualityAgent(BaseAgent):
	def __init__(self) -> None:
		super().__init__(key="naming_quality", title="Naming and Documentation Review")

	def build_prompt(self, payload: AgentPayload) -> str:
		files_blob = payload.files_blob(max_files=12, max_chars_per_file=1200)
		return (
			"You review naming, function signatures, and inline documentation.\n"
			"List any identifiers that are unclear, misleading, or violate the project's guidelines.\n"
			"Highlight missing docstrings, parameter descriptions, or mismatched behavior.\n"
			"Respond in Markdown with bullet points. If everything looks good, state that explicitly.\n\n"
			f"Coding Guidelines:\n{payload.project_context.coding_guidelines}\n\n"
			f"Changed Files:\n{files_blob}\n"
		)



