from app.review.agentic.agents.code_agent import CodeSummaryAgent
from app.review.agentic.agents.diagram_agent import DiagramAgent
from app.review.agentic.agents.naming_agent import NamingQualityAgent
from app.review.agentic.agents.task_agent import TaskContextAgent
from app.review.agentic.agents.test_agent import TestCoverageAgent
from app.review.agentic.models import AgentPayload, ProjectContext


def _payload() -> AgentPayload:
	ctx = ProjectContext(
		name="Demo",
		description="Demo project",
		tech_stack=["python", "fastapi"],
		architecture=["service", "queue"],
		testing_standards="pytest, coverage>80%",
		coding_guidelines="pep8",
	)
	return AgentPayload(
		title="Add feature",
		description="Implements X",
		diff_text="diff --git a b",
		changed_files=[("a.py", "print('a')"), ("b.py", "print('b')")],
		commit_messages=["feat: add a", "chore: tweak"],
		project_context=ctx,
	)


def test_code_summary_prompt_contains_sections():
	agent = CodeSummaryAgent()
	p = _payload()
	out = agent.build_prompt(p)
	assert "Produce at most FIVE" in out
	assert "Diff Snippet:" in out
	assert "Changed Files:" in out
	assert "Commit Messages:" in out


def test_task_context_prompt_contains_context_details():
	agent = TaskContextAgent()
	p = _payload()
	out = agent.build_prompt(p)
	assert "Return at most FIVE bullet points" in out
	assert "Project Name: Demo" in out
	assert "Tech Stack: python, fastapi" in out
	assert "Architecture Focus: service, queue" in out
	assert "Testing Standards:" in out


def test_naming_quality_prompt_mentions_guidelines():
	agent = NamingQualityAgent()
	p = _payload()
	out = agent.build_prompt(p)
	assert "Coding Guidelines:" in out
	assert "Return STRICT JSON" in out


def test_test_coverage_prompt_requests_json_with_findings():
	agent = TestCoverageAgent()
	p = _payload()
	out = agent.build_prompt(p)
	assert "\"findings\"" in out
	assert "Return STRICT JSON" in out
	assert "Testing Standards:" in out


def test_naming_agent_parses_code_fence_json():
	agent = NamingQualityAgent()
	payload = _payload()
	response = """```json
{
  "summary": ["bad doc"],
  "findings": [{"path": "a.py", "line": 10, "comment": "doc missing"}]
}
```"""
	result = agent.parse_output(response)
	assert "- bad doc" in result.content
	assert result.findings and result.findings[0].path == "a.py"


def test_test_agent_parses_code_fence_json():
	agent = TestCoverageAgent()
	response = """```json
{
  "summary": ["ok"],
  "gaps": [],
  "recommended_tests": ["test_x"],
  "findings": [{"path": "b.py", "line": 5, "comment": "missing test"}]
}
```"""
	result = agent.parse_output(response)
	assert "- ok" in result.content
	assert any(f.path == "b.py" for f in result.findings)


def test_diagram_agent_wraps_mermaid_block():
	agent = DiagramAgent()
	p = _payload()
	prompt = agent.build_prompt(p)
	assert "Mermaid" in prompt or "diagram" in prompt.lower()
	# Postprocess should wrap non-mermaid output
	wrapped = agent.postprocess("graph TD; A-->B")
	assert wrapped.strip().startswith("```mermaid")
	assert wrapped.strip().endswith("```")


