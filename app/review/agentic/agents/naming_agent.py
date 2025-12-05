import json
import re

from ..models import AgentFinding, AgentPayload, AgentResult
from .base import BaseAgent


class NamingQualityAgent(BaseAgent):
	def __init__(self) -> None:
		super().__init__(key="naming_quality", title="Naming and Documentation Review")

	def build_prompt(self, payload: AgentPayload) -> str:
		files_blob = payload.files_with_line_numbers(max_files=8, max_lines=300)
		guidelines = payload.project_context.coding_guidelines or payload.project_context.description or ""
		return (
			"You review naming, function signatures, and inline documentation.\n"
			"Follow STRICT rules and output exactly the specified JSON schema.\n"
			"Return STRICT JSON: {\"summary\": [<up to 3 short bullets, <=14 words>], "
			"\"findings\": [{\"path\": \"file.py\", \"line\": 12, \"comment\": \"one sentence\"}, ...] }.\n"
			"- Use only information visible in snippets. Do not speculate.\n"
			"- 'summary' supports the overall comment body; be specific and non-repetitive.\n"
			"- 'findings' pinpoints actionable issues; omit if nothing precise. Lines are 1-indexed.\n"
			"- If everything is fine, use summary [\"Naming and docs look fine\"] and findings [].\n"
			"- No prose outside JSON.\n\n"
			f"Coding Guidelines / Project Description:\n{guidelines}\n\n"
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
		# Suppress comment when nothing actionable
		if not findings and (not summary_items or any("look fine" in s.lower() for s in summary_items)):
			content = ""
		return AgentResult(key=self.key, content=content, success=True, findings=findings)

	def _strip_code_fence(self, text: str) -> str:
		strip = text.strip()
		if strip.startswith("```"):
			strip = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", strip)
			strip = re.sub(r"\s*```$", "", strip)
		return strip



