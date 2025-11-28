from concurrent.futures import ThreadPoolExecutor, as_completed

from ...config.logging_config import configure_logging
from ..base import InlineFinding, ReviewComment, ReviewGenerator, ReviewOutput
from .agents import (
    CodeSummaryAgent,
    DiagramAgent,
    NamingQualityAgent,
    TaskContextAgent,
    TestCoverageAgent,
)
from .context_loader import load_project_context
from .llm import build_llm_client
from .models import AgentFinding, AgentPayload, AgentResult

_LOGGER = configure_logging()


class AgenticReviewGenerator(ReviewGenerator):
	def __init__(
		self,
		provider: str,
		model: str,
		openai_api_key: str,
		google_api_key: str,
		project_context_path: str,
		timeout: float = 60.0,
		max_retries: int = 2,
		max_concurrency: int = 4,
	) -> None:
		self.project_context_path = project_context_path
		self.max_retries = max(0, max_retries)
		self.client = build_llm_client(provider, model, openai_api_key, google_api_key, timeout)
		self.max_concurrency = max(1, int(max_concurrency))
		self.agents = [
			TaskContextAgent(),
			CodeSummaryAgent(),
			DiagramAgent(),
			NamingQualityAgent(),
			TestCoverageAgent(),
		]

	def generate_review(
		self,
		title: str,
		description: str,
		diff_text: str,
		changed_files: list[tuple[str, str]],
		commit_messages: list[str],
	) -> ReviewOutput:
		context = load_project_context(self.project_context_path)
		payload = AgentPayload(
			title=title,
			description=description,
			diff_text=diff_text,
			changed_files=changed_files,
			commit_messages=commit_messages,
			project_context=context,
		)
		results: dict[str, AgentResult] = {}
		inline_findings: list[AgentFinding] = []
		if not self.agents:
			return ReviewOutput(comments=[], inline_findings=[])

		max_workers = min(self.max_concurrency, len(self.agents))
		with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-worker") as pool:
			future_to_key = {pool.submit(self._run_agent, agent, payload): agent.key for agent in self.agents}
			for fut in as_completed(future_to_key):
				key = future_to_key[fut]
				try:
					res = fut.result()
				except Exception as exc:
					_LOGGER.warning("Agent future failed", extra={"agent": key, "error": str(exc)})
					res = AgentResult(key=key, success=False, error=str(exc))
				results[key] = res
				if getattr(res, "findings", None):
					inline_findings.extend(res.findings)

		if inline_findings:
			inline_findings.sort(key=lambda f: (getattr(f, "path", "") or "", getattr(f, "line", 0)))
		comments = self._compose_comments(payload, results)
		return ReviewOutput(
			comments=comments,
			inline_findings=[
				InlineFinding(path=f.path, line=f.line, body=f.body, source=f.source or "")
				for f in inline_findings
			],
		)

	def _run_agent(self, agent, payload: AgentPayload) -> AgentResult:
		if not self.client.available:
			return AgentResult(key=agent.key, success=False, error=self.client.unavailable_reason or "LLM unavailable")
		last_error = None
		for _ in range(self.max_retries + 1):
			try:
				return agent.execute(self.client, payload)
			except Exception as exc:
				last_error = str(exc)
				_LOGGER.warning("Agent execution failed", extra={"agent": agent.key, "error": last_error})
		return AgentResult(key=agent.key, success=False, error=last_error or "Agent failed without error")

	def _compose_comments(self, payload: AgentPayload, results: dict[str, AgentResult]) -> list[ReviewComment]:
		if not results:
			return []
		if not any(r.success for r in results.values()):
			return [ReviewComment(title="Agentic Reviewer", body=self._fallback_body(payload, results))]
		comments: list[ReviewComment] = []
		summary = self._build_summary_comment(results)
		if summary:
			comments.append(summary)
		diagram = self._build_diagram_comment(results)
		if diagram:
			comments.append(diagram)
		naming = self._build_naming_comment(results)
		if naming:
			comments.append(naming)
		tests = self._build_test_comment(results)
		if tests:
			comments.append(tests)
		return comments or [ReviewComment(title="Agentic Reviewer", body=self._fallback_body(payload, results))]

	def _build_summary_comment(self, results: dict[str, AgentResult]) -> ReviewComment | None:
		task = results.get("task_context")
		code = results.get("code_summary")
		bullets = self._collect_bullets(task, code)
		if not bullets:
			return None
		body = "\n".join(f"- {item}" for item in bullets[:5])
		if not body.strip():
			return None
		return ReviewComment(title="Task and Diff Summary", body=body)

	def _collect_bullets(self, *results: AgentResult | None) -> list[str]:
		bullets: list[str] = []
		for result in results:
			if not result or not result.content:
				continue
			for line in result.content.splitlines():
				strip = line.strip()
				if not strip:
					continue
				if strip.startswith("-"):
					strip = strip[1:].strip()
				bullets.append(strip)
		return [b for b in bullets if b]

	def _build_diagram_comment(self, results: dict[str, AgentResult]) -> ReviewComment | None:
		item = results.get("architecture_diagram")
		if not item:
			return None
		body = self._render_section("Mermaid", item)
		if not body:
			return None
		return ReviewComment(title="Architecture Diagram", body=body)

	def _build_naming_comment(self, results: dict[str, AgentResult]) -> ReviewComment | None:
		item = results.get("naming_quality")
		if not item:
			return None
		body = self._render_section("Findings", item)
		if not body:
			return None
		return ReviewComment(title="Naming and Documentation", body=body)

	def _build_test_comment(self, results: dict[str, AgentResult]) -> ReviewComment | None:
		item = results.get("test_coverage")
		if not item:
			return None
		body = self._render_section("Analysis", item)
		if not body:
			return None
		return ReviewComment(title="Test Coverage Review", body=body)

	def _render_section(self, label: str, result: AgentResult | None) -> str:
		if not result:
			return ""
		if result.success and result.content:
			return f"**{label}**\n{result.content.strip()}"
		error = result.error or "No output produced."
		return f"**{label}**\nAgent error: {error}"

	def _fallback_body(self, payload: AgentPayload, results: dict[str, AgentResult]) -> str:
		reason = next((r.error for r in results.values() if r.error), "agent pipeline unavailable")
		diff_preview = (payload.diff_text or "")[:2000]
		return (
			f"Agentic pipeline unavailable: {reason}\n\n"
			"Diff preview:\n"
			f"```\n{diff_preview}\n```"
		)



