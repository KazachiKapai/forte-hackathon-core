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
			"You are a delivery lead who prepares a concise brief for reviewers.\n"
			"Describe the business goal of the change, highlight the most important requirements, "
			"and list any risks that reviewers should keep in mind.\n"
			"Respond in Markdown with sections: Task Objective, Key Requirements, Risks.\n\n"
			f"Project Name: {ctx.name}\n"
			f"Project Summary: {ctx.description}\n"
			f"Tech Stack: {tech_stack}\n"
			f"Architecture Focus: {architecture}\n"
			f"Testing Standards: {ctx.testing_standards}\n"
			f"Coding Guidelines: {ctx.coding_guidelines}\n\n"
			f"Merge Request Title: {payload.title}\n"
			f"Merge Request Description:\n{desc}\n"
		)



