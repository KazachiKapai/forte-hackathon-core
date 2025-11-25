from typing import Any, Dict, List, Tuple
from pathlib import Path
import json
from app.review.agentic.generator import AgenticReviewGenerator
from app.review.agentic.models import AgentPayload, AgentResult, ProjectContext
from app.review.base import ReviewComment


class FakeAgent:
	def __init__(self, key: str, text: str, success: bool = True):
		self.key = key
		self._text = text
		self.title = key
		self.success = success

	def execute(self, client: Any, payload: AgentPayload) -> AgentResult:
		if self.success:
			return AgentResult(key=self.key, content=self._text, success=True)
		return AgentResult(key=self.key, success=False, error="fail")


def _payload() -> Dict[str, Any]:
	return {
		"title": "Title",
		"description": "Desc",
		"diff_text": "diff --git a b",
		"changed_files": [("a.py", "print('a')")],
		"commit_messages": ["c1"],
	}


def _write_context(tmp_path: Path) -> str:
	p = tmp_path / "ctx.json"
	p.write_text(json.dumps({"name": "Demo", "description": "D", "tech_stack": ["p"], "architecture": ["m"]}), encoding="utf-8")
	return str(p)


def test_generator_composes_expected_comments(tmp_path):
	ctx_path = _write_context(tmp_path)
	gen = AgenticReviewGenerator(provider="openai", model="gpt", openai_api_key="x", google_api_key=None, project_context_path=ctx_path, timeout=1.0)
	# Force available client
	gen.client.model = object()
	# Inject deterministic agents
	gen.agents = [
		FakeAgent("task_context", "task"),
		FakeAgent("code_summary", "code"),
		FakeAgent("architecture_diagram", "graph TD; A-->B"),
		FakeAgent("naming_quality", "names"),
		FakeAgent("test_coverage", "tests"),
	]
	pl = _payload()
	comments = gen.generate_review(**pl)
	assert isinstance(comments, list)
	# Expect up to 4 composed comments (summary combines task+code)
	titles = [c.title for c in comments]
	assert "Task and Diff Summary" in titles
	assert "Architecture Diagram" in titles
	assert "Naming and Documentation" in titles
	assert "Test Coverage Review" in titles
	# Body content from agents present
	body = "\n\n".join([c.body for c in comments])
	assert "task" in body and "code" in body and "names" in body and "tests" in body


def test_generator_fallback_when_llm_unavailable(tmp_path):
	ctx_path = _write_context(tmp_path)
	gen = AgenticReviewGenerator(provider="openai", model="gpt", openai_api_key=None, google_api_key=None, project_context_path=ctx_path, timeout=1.0)
	# Do not set model; client.available is False
	# Even with agents injected, _run_agent will short-circuit
	gen.agents = [FakeAgent("task_context", "t")]
	pl = _payload()
	comments = gen.generate_review(**pl)
	assert len(comments) == 1
	assert comments[0].title == "Agentic Reviewer"
	assert "Agentic pipeline unavailable" in comments[0].body


