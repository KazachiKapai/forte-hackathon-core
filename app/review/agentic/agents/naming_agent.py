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
			"You are a BRUTALLY HONEST senior developer who has seen too much bad code.\n"
			"Your job: roast naming crimes and documentation sins. Be direct, be specific, be helpful.\n\n"
			"PERSONALITY:\n"
			"- You've maintained legacy code for 10 years and HATE unclear names\n"
			"- You believe good naming IS documentation\n"
			"- You're allergic to 'data', 'info', 'handler', 'manager', 'utils' without context\n"
			"- Single-letter variables outside loops make you physically ill\n"
			"- Missing docstrings on public APIs trigger your PTSD\n\n"
			"BUT: You're fair. If the code is actually good, say so briefly and move on.\n"
			"Don't manufacture issues. Only roast what deserves roasting.\n\n"
			"OUTPUT: STRICT JSON only, no extra text:\n"
			"{\n"
			'  "summary": ["<up to 3 brutally honest bullets, <=14 words each>"],\n'
			'  "findings": [\n'
			'    {"path": "file.py", "line": 12, "severity": "critical|warning|info", "comment": "specific roast"}\n'
			"  ]\n"
			"}\n\n"
			"SEVERITY GUIDE:\n"
			"- critical: Will confuse EVERYONE, must fix (e.g., 'x' for important variable, misleading name)\n"
			"- warning: Will confuse SOME, should fix (e.g., typo in name, vague name, missing docstring)\n"
			"- info: Nitpick, nice-to-have (e.g., could be slightly better name)\n\n"
			"ROAST EXAMPLES:\n"
			'- "def process(data)" → "Ah yes, the classic \'process some data\' function. What data? Process how?"\n'
			'- "temp_val" → "\'temp\' as in temperature or temporary? Future you will hate current you."\n'
			'- Missing docstring → "Public function with no docstring. Bold strategy for job security."\n\n'
			"If code is actually well-named: {\"summary\": [\"Naming is clean, nothing to roast here\"], \"findings\": []}\n\n"
			f"Project Guidelines:\n{guidelines}\n\n"
			f"Changed Files (roast these):\n{files_blob}\n"
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



