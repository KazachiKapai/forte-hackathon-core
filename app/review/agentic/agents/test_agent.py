import json
import re
from .base import BaseAgent
from ..models import AgentFinding, AgentPayload, AgentResult


class TestCoverageAgent(BaseAgent):
	def __init__(self) -> None:
		super().__init__(key="test_coverage", title="Test Coverage Review")

	def build_prompt(self, payload: AgentPayload) -> str:
		files_blob = payload.files_with_line_numbers(max_files=8, max_lines=200)
		commits_blob = payload.commits_blob()
		return (
			"You evaluate whether the code changes are covered by automated tests.\n"
			"Return STRICT JSON: {"
			"\"summary\": [<bullets>], "
			"\"gaps\": [<bullets>], "
			"\"recommended_tests\": [\"test name or scenario\", ...], "
			"\"findings\": [{\"path\": \"file.py\", \"line\": 42, \"comment\": \"one sentence\"}, ...]"
			"}.\n"
			"- summary: what tests exist / pass (short bullets, max 2).\n"
			"- gaps: what is missing or wrong (short bullets, max 3). If a test is wrong, mention it explicitly.\n"
			"- recommended_tests: plain list of tests to add (max 4). If nothing missing, use [].\n"
			"- findings: tie any bug/gap to a specific file+line (1-indexed). Use [] if nothing precise.\n"
			"No prose outside JSON. Keep bullets brutally concise.\n\n"
			f"Testing Standards: {payload.project_context.testing_standards}\n\n"
			f"Changed Files:\n{files_blob}\n\n"
			f"Commit Messages:\n{commits_blob}\n"
		)

	def parse_output(self, output: str) -> AgentResult:
		text = self.postprocess(output)
		try:
			data = json.loads(self._strip_code_fence(text))
		except Exception:
			return AgentResult(key=self.key, content=text, success=True)
		parts = []
		for label in ("summary", "gaps"):
			items = data.get(label) or []
			if not isinstance(items, list):
				continue
			for item in items:
				if isinstance(item, str) and item.strip():
					parts.append(f"- {item.strip()}")
		reco_items = []
		reco_items = []
		for item in data.get("recommended_tests", []) or []:
			if isinstance(item, str) and item.strip():
				reco_items.append(item.strip())
		if reco_items:
			parts.append("Recommended tests:")
			for test_name in reco_items:
				parts.append(f"- [add] {test_name}")
		body = "\n".join(parts) if parts else "No test concerns."
		findings: list[AgentFinding] = []
		for item in data.get("findings", []) or []:
			if not isinstance(item, dict):
				continue
			path = item.get("path")
			line = item.get("line")
			comment = item.get("comment")
			try:
				line_num = int(line)
			except Exception:
				continue
			if path and isinstance(path, str) and line_num > 0 and isinstance(comment, str) and comment.strip():
				findings.append(AgentFinding(path=path, line=line_num, body=comment.strip(), source=self.key))
		return AgentResult(key=self.key, content=body, success=True, findings=findings)

	def _strip_code_fence(self, text: str) -> str:
		strip = text.strip()
		if strip.startswith("```"):
			strip = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", strip)
			strip = re.sub(r"\s*```$", "", strip)
		return strip



