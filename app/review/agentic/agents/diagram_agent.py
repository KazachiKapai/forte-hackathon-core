from ..models import AgentPayload
from .base import BaseAgent


class DiagramAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(key="architecture_diagram", title="Architecture Diagram")

    def build_prompt(self, payload: AgentPayload) -> str:
        files_blob = payload.files_blob(max_files=12, max_chars_per_file=800)
        arch_notes = "\n".join(payload.project_context.architecture) if payload.project_context.architecture else ""
        desc_notes = payload.project_context.description or ""
        return (
            "You are a system designer. Return a SINGLE valid Mermaid code block only.\n"
            "STRICT:\n"
            "- Start with ```mermaid and end with ```\n"
            "- Use either 'graph TD' (preferred) or 'sequenceDiagram'.\n"
            "- No extra text, no markdown outside the code block.\n"
            "- Keep nodes concise, show data/flow, highlight changed components.\n"
            "- Do NOT invent components not implied by files/context.\n"
            "- If unsure, produce a minimal valid graph TD with 2-4 nodes.\n\n"
            f"Project Description (fallback context):\n{desc_notes}\n\n"
            f"Project Architecture Notes:\n{arch_notes}\n\n"
            f"Changed Files (snippets):\n{files_blob}\n"
        )

    def postprocess(self, output: str) -> str:
        text = super().postprocess(output).strip()
        lower = text.lower()
        if "```mermaid" in lower:
            start = text.lower().find("```mermaid")
            trimmed = text[start:]
            # Ensure closing fence
            if "```" not in trimmed[len("```mermaid"):]:
                trimmed = f"{trimmed}\n```"
            return trimmed

        body = text.strip()
        if not body or ("graph" not in body and "sequenceDiagram" not in body):
            body = "graph TD\n  A[Change] --> B[Effect]\n  B --> C[Consumer]"
        return f"```mermaid\n{body}\n```"



