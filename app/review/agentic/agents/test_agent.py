from .base import BaseAgent
from ..models import AgentPayload


class TestCoverageAgent(BaseAgent):
	def __init__(self) -> None:
		super().__init__(key="test_coverage", title="Test Coverage Review")

	def build_prompt(self, payload: AgentPayload) -> str:
		files_blob = payload.files_blob(max_files=10, max_chars_per_file=1000)
		commits_blob = payload.commits_blob()
		return (
			"You evaluate whether the code changes are covered by automated tests.\n"
			"Identify unit, integration, or contract tests that were added or need to be added.\n"
			"Call out risk areas that lack coverage and suggest specific test ideas.\n"
			"Respond in Markdown with sections: Existing Coverage, Gaps, Recommended Tests.\n\n"
			f"Testing Standards: {payload.project_context.testing_standards}\n\n"
			f"Changed Files:\n{files_blob}\n\n"
			f"Commit Messages:\n{commits_blob}\n"
		)



