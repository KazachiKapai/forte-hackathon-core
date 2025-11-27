import json
import re
from .base import BaseAgent
from ..models import AgentPayload, AgentFinding, AgentResult


class NamingQualityAgent(BaseAgent):
	def __init__(self) -> None:
		super().__init__(key="naming_quality", title="Naming and Documentation Review")

	def build_prompt(self, payload: AgentPayload) -> str:
		files_blob = payload.files_with_line_numbers(max_files=8, max_lines=300)
		return (
			"You review naming, function signatures, and inline documentation.\n"
			"Return STRICT JSON: {\"summary\": [<up to 3 short bullets>], "
			"\"findings\": [{\"path\": \"file.py\", \"line\": 12, \"comment\": \"one sentence\"}, ...] }.\n"
			"- summary bullets must be concise statements for the overall comment body.\n"
			"- findings array pinpoints specific issues; omit if nothing actionable. Lines are 1-indexed.\n"
			"If everything is good, summary must be [\"Naming and docs look fine\"] and findings must be []. "
			"No prose outside JSON.\n\n"
			f"Coding Guidelines:\n{payload.project_context.coding_guidelines}\n\n"
			f"Changed Files:\n{files_blob}\n"
		)

	def parse_output(self, output: str) -> AgentResult:
		text = self.postprocess(output)
		try:
			data = json.loads(self._strip_code_fence(text))
		except Exception:
			return AgentResult(key=self.key, content=text, success=True)
		summary_items = [item.strip() for item in data.get("summary", []) if isinstance(item, str) and item.strip()]
		content = "\n".join(f"- {item}" for item in summary_items) if summary_items else ""
		findings: list[AgentFinding] = []
		for item in data.get("findings", []):
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
		return AgentResult(
			key=self.key,
			content=content or "No naming/doc issues detected.",
			success=True,
			findings=findings,
		)

	def _strip_code_fence(self, text: str) -> str:
		strip = text.strip()
		if strip.startswith("```"):
			strip = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", strip)
			strip = re.sub(r"\s*```$", "", strip)
		return strip



