from __future__ import annotations

from .base import BaseAgent
import google.generativeai as genai


class DiscussionAgent(BaseAgent):
    def __init__(self, model: str, api_key: str, mention_token: str = "@ai-review") -> None:
        super().__init__(key="discussion", title="Discussion Agent")
        self.mention_token = mention_token
        self.model = model
        self.api_key = api_key

    def build_prompt(self, payload: str) -> str:
        """
        Build a concise discussion prompt. We expect the payload.description
        to include both original note and developer reply, preformatted.
        """
        lines: list[str] = ["You are an AI code review assistant collaborating in a GitLab MR thread. ",
                            "Respond concisely and constructively. If you were wrong, acknowledge and correct. ",
                            "If a code change is needed, propose the minimal fix with a short snippet. ",
                            payload or "", "", "Your response (aim for <= 8 lines):"]
        return "\n".join(lines)

    def generate_reply(self, original_note: str, developer_reply: str) -> str:
        orig = (original_note or "").strip()
        dev = (developer_reply or "").strip()
        description_parts: list[str] = []
        if orig:
            description_parts.append("Original review note:\n" + orig[:4000])
        if dev:
            description_parts.append("Developer reply:\n" + dev[:4000])

        prompt = self.build_prompt("\n".join(description_parts))
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)
        resp = model.generate_content(prompt)
        return (getattr(resp, "text", None) or "").strip()
