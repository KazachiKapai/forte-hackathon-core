import json
import re

from ..models import AgentFinding, AgentPayload, AgentResult
from .base import BaseAgent


class TestCoverageAgent(BaseAgent):
	__test__ = False
	def __init__(self) -> None:
		super().__init__(key="test_coverage", title="Test Coverage Review")

	def build_prompt(self, payload: AgentPayload) -> str:
		files_blob = payload.files_with_line_numbers(max_files=8, max_lines=200)
		commits_blob = payload.commits_blob()
		testing = payload.project_context.testing_standards or payload.project_context.description or ""
		return (
			"You are a QA ENGINEER who has been burned by 'it works on my machine' too many times.\n"
			"Your mission: find untested code paths that WILL break in production at 3 AM.\n\n"
			"PERSONALITY:\n"
			"- You've been paged at 3 AM because someone didn't write tests. Never again.\n"
			"- 'I tested it manually' makes your eye twitch\n"
			"- You believe untested code is broken code that hasn't failed YET\n"
			"- Happy path tests only? That's cute. What about edge cases?\n"
			"- No error handling tests? Hope you enjoy debugging production.\n\n"
			"BUT: You're pragmatic. Not everything needs 100% coverage.\n"
			"- Simple getters/setters? Skip.\n"
			"- Generated code? Skip.\n"
			"- Critical business logic without tests? UNACCEPTABLE.\n\n"
			"OUTPUT: STRICT JSON only:\n"
			"{\n"
			'  "summary": ["<max 2 bullets about test status>"],\n'
			'  "gaps": ["<max 3 bullets about CRITICAL missing tests>"],\n'
			'  "recommended_tests": ["test scenario description"],\n'
			'  "findings": [{"path": "file.py", "line": 42, "severity": "critical|warning|info", "comment": "why this needs tests"}],\n'
			'  "proposed_tests": [{"path": "tests/test_x.py", "framework": "pytest", "rationale": "why", "code": "```python\\n# test\\n```"}]\n'
			"}\n\n"
			"SEVERITY GUIDE:\n"
			"- critical: Business logic, money handling, auth, data mutation - MUST have tests\n"
			"- warning: Public API, error handling, edge cases - SHOULD have tests\n"
			"- info: Nice-to-have tests, already low-risk code\n\n"
			"ROAST EXAMPLES:\n"
			'- No tests for payment logic → "Oh cool, we\'re testing payment processing in production. WCGW?"\n'
			'- Try/except with pass → "Silently swallowing exceptions. The \'pretend it didn\'t happen\' strategy."\n'
			'- Async without error handling → "async def yolo(): hope nothing fails here ever"\n\n'
			"If tests look adequate: {\"summary\": [\"Test coverage looks solid\"], \"gaps\": [], ...}\n\n"
			f"Testing Standards:\n{testing}\n\n"
			f"Changed Files (find the untested sins):\n{files_blob}\n\n"
			f"Commits:\n{commits_blob}\n"
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
		for item in data.get("recommended_tests", []) or []:
			if isinstance(item, str) and item.strip():
				reco_items.append(item.strip())
		if reco_items:
			parts.append("Recommended tests:")
			for test_name in reco_items:
				parts.append(f"- [add] {test_name}")
		# Proposed test code blocks (optional)
		proposed_blocks = []
		for t in data.get("proposed_tests", []) or []:
			if not isinstance(t, dict):
				continue
			path = t.get("path")
			code = t.get("code")
			rationale = t.get("rationale")
			if isinstance(path, str) and isinstance(code, str) and path.strip() and code.strip():
				header = f"\n\nProposed test: {path}"
				if isinstance(rationale, str) and rationale.strip():
					header += f"\nReason: {rationale.strip()}"
				proposed_blocks.append(header + f"\n{code.strip()}")
		if proposed_blocks:
			parts.append("\n".join(proposed_blocks))
		body = "\n".join(parts).strip()
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
		# Suppress comment when nothing actionable
		return AgentResult(key=self.key, content=body, success=True, findings=findings)

	def _strip_code_fence(self, text: str) -> str:
		strip = text.strip()
		if strip.startswith("```"):
			strip = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", strip)
			strip = re.sub(r"\s*```$", "", strip)
		return strip



