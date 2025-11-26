from .base import BaseAgent
from ..models import AgentPayload


class TaskContextAgent(BaseAgent):
	def __init__(self) -> None:
		super().__init__(key="task_context", title="Task Context Summary")

	def build_prompt(self, payload: AgentPayload) -> str:
		ctx = payload.project_context
		tech_stack = ", ".join(ctx.tech_stack) if ctx.tech_stack else "unspecified"
		architecture = ", ".join(ctx.architecture) if ctx.architecture else "unspecified"
		desc = payload.description or "No description provided."
		return (
			"You are a delivery lead who prepares a concise brief for senior reviewers.\n"
			"Return at most FIVE bullet points (format exactly '- <text>') covering:\n"
			"- business goal / scope\n"
			"- most important code change\n"
			"- critical risk or regression to watch\n"
			"- test/doc expectation if relevant\n"
			"- optional follow-up.\n"
			"No headings, no paragraphs, no fluff.\n\n"
			f"Project Name: {ctx.name}\n"
			f"Project Summary: {ctx.description}\n"
			f"Tech Stack: {tech_stack}\n"
			f"Architecture Focus: {architecture}\n"
			f"Testing Standards: {ctx.testing_standards}\n"
			f"Coding Guidelines: {ctx.coding_guidelines}\n\n"
			f"Merge Request Title: {payload.title}\n"
			f"Merge Request Description:\n{desc}\n"
		)



