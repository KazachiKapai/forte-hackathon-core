from app.review.agentic.agents.code_agent import CodeSummaryAgent
from app.review.agentic.agents.diagram_agent import DiagramAgent
from app.review.agentic.agents.naming_agent import NamingQualityAgent
from app.review.agentic.agents.task_agent import TaskContextAgent
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
	assert "Code Change Summary" not in out  # title is not part of prompt
	assert "You are a senior engineer" in out
	assert "Diff Snippet:" in out
	assert "Changed Files:" in out
	assert "Commit Messages:" in out


def test_task_context_prompt_contains_context_details():
	agent = TaskContextAgent()
	p = _payload()
	out = agent.build_prompt(p)
	assert "Project Name: Demo" in out
	assert "Tech Stack: python, fastapi" in out
	assert "Architecture Focus: service, queue" in out
	assert "Testing Standards:" in out


def test_naming_quality_prompt_mentions_guidelines():
	agent = NamingQualityAgent()
	p = _payload()
	out = agent.build_prompt(p)
	assert "Coding Guidelines:" in out
	assert "Respond in Markdown" in out


def test_diagram_agent_wraps_mermaid_block():
	agent = DiagramAgent()
	p = _payload()
	prompt = agent.build_prompt(p)
	assert "Mermaid" in prompt or "diagram" in prompt.lower()
	# Postprocess should wrap non-mermaid output
	wrapped = agent.postprocess("graph TD; A-->B")
	assert wrapped.strip().startswith("```mermaid")
	assert wrapped.strip().endswith("```")


