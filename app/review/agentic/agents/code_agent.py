from ..models import AgentPayload
from .base import BaseAgent


class CodeSummaryAgent(BaseAgent):
	def __init__(self) -> None:
		super().__init__(key="code_summary", title="Code Change Summary")

	def build_prompt(self, payload: AgentPayload) -> str:
		files_blob = payload.files_blob()
		commits_blob = payload.commits_blob()
		diff = payload.diff_text or "Diff not available."
		return (
			"You are a senior reviewer. Follow STRICT rules:\n"
			"- Produce at most FIVE bullets, each max 14 words, format exactly '- <text>'.\n"
			"- Use only evidence in the diff/files/commits. If uncertain, omit.\n"
			"- Focus on: scope impact, risky area, key dependency, notable follow-up.\n"
			"- No headings, no prose outside bullets.\n\n"
			f"Merge Request Title: {payload.title}\n"
			f"Project Context: {payload.project_context.description}\n\n"
			f"Diff Snippet:\n{diff}\n\n"
			f"Changed Files:\n{files_blob}\n\n"
			f"Commit Messages:\n{commits_blob}\n"
		)



