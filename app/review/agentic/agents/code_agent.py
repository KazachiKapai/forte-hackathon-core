from .base import BaseAgent
from ..models import AgentPayload


class CodeSummaryAgent(BaseAgent):
	def __init__(self) -> None:
		super().__init__(key="code_summary", title="Code Change Summary")

	def build_prompt(self, payload: AgentPayload) -> str:
		files_blob = payload.files_blob()
		commits_blob = payload.commits_blob()
		diff = payload.diff_text or "Diff not available."
		return (
			"You are a senior reviewer. Produce at most FIVE crisp bullet points (format '- text') "
			"highlighting the most important code or diff facts: scope impact, risky area, key dependency, "
			"and any follow-up work. Do not add headings or prose.\n\n"
			f"Merge Request Title: {payload.title}\n"
			f"Project Context: {payload.project_context.description}\n\n"
			f"Diff Snippet:\n{diff}\n\n"
			f"Changed Files:\n{files_blob}\n\n"
			f"Commit Messages:\n{commits_blob}\n"
		)



