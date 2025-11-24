import os
from typing import List, Optional, Tuple
import os
import json

from .base import ReviewGenerator
from ..config.logging_config import configure_logging

_LOGGER = configure_logging()

try:
	import google.generativeai as genai  # type: ignore
	_HAS_GEMINI = True
except Exception:
	_HAS_GEMINI = False


class GeminiReviewGenerator(ReviewGenerator):
	def __init__(self, api_key: Optional[str], model: str) -> None:
		self.api_key = api_key
		self.model = model

	def generate_review(
		self,
		title: str,
		description: str,
		diff_text: str,
		changed_files: List[Tuple[str, str]],
		commit_messages: List[str],
	) -> str:
		# Dev mode: return deterministic, structured mock output for validation
		if (os.environ.get("ENV", "prod") or "prod").lower() == "dev":
			num_files = len(changed_files or [])
			approx_diff_len = len(diff_text or "")
			issues: List[str] = []
			recs: List[str] = []
			text_lower = f"{title}\n{description}\n{diff_text}".lower()
			if "fix" in text_lower or "bug" in text_lower:
				issues.append("Potential bug fix detected")
				recs.append("Add regression test covering the reported bug scenario")
			if "readme" in text_lower or "doc" in text_lower:
				recs.append("Ensure documentation is updated and accurate")
			if "test" in text_lower:
				recs.append("Verify tests are stable and deterministic")
			mock = {
				"type": "mock_review",
				"title": title,
				"issues": issues,
				"recommendations": recs,
				"summary": {"filesChanged": num_files, "diffChars": approx_diff_len, "commitCount": len(commit_messages or [])},
			}
			header = "Automated GPT Review (Mock)\n\n"
			return header + "```json\n" + json.dumps(mock, ensure_ascii=False, indent=2) + "\n```"
		if not _HAS_GEMINI:
			_LOGGER.warning("Gemini package not installed")
			return self._placeholder(diff_text)
		if not self.api_key:
			_LOGGER.info("GEMINI_API_KEY not set; skipping AI review")
			return self._placeholder(diff_text)
		try:
			genai.configure(api_key=self.api_key)
			candidates = self._candidate_models(self.model)
			candidates = self._intersect_available_models(candidates)
			system_instructions = (
				"You are an expert software reviewer. Provide a concise, actionable code review.\n"
				"- Identify bugs, security issues, and regressions.\n"
				"- Flag unclear naming or unreadable logic.\n"
				"- Suggest concrete improvements and tests.\n"
				"- If diff is large, focus on highest-risk areas first.\n"
			)
			files_blob = ""
			if changed_files:
				parts: List[str] = []
				for path, content in changed_files:
					parts.append(f"File: {path}\nContent:\n{content}\n")
				files_blob = "\n".join(parts)
			commits_blob = ""
			if commit_messages:
				commits_blob = "\n".join(f"- {m}" for m in commit_messages)
			prompt = (
				f"{system_instructions}\n\n"
				f"Merge Request Title: {title}\n\n"
				f"Description:\n{description}\n\n"
				f"Unified Diff:\n{diff_text}\n\n"
				f"Changed Files (new contents):\n{files_blob}\n\n"
				f"Commit Messages:\n{commits_blob}\n"
			)
			last_err: Optional[Exception] = None
			for model_name in candidates:
				try:
					_LOGGER.info("Attempting Gemini generation", extra={"model": model_name})
					model = genai.GenerativeModel(model_name)
					resp = model.generate_content(prompt)
					text = getattr(resp, "text", None) or ""
					_LOGGER.info("Gemini review generated", extra={"model": model_name})
					return "Automated GPT Review (Gemini)\n\n" + text.strip()
				except Exception as e:
					last_err = e
					_LOGGER.warning("Gemini attempt failed", extra={"model": model_name, "error": str(e)})
					continue
			if last_err:
				_LOGGER.error("All Gemini attempts failed", extra={"error": str(last_err)})
		except Exception as e:
			_LOGGER.exception("Gemini review failed irrecoverably")
		return self._placeholder(diff_text)

	def _candidate_models(self, env_model: Optional[str]) -> List[str]:
		base = [
			"gemini-2.5-pro",
			"gemini-2.0-pro",
			"gemini-1.5-flash",
			"gemini-1.5-flash-8b",
			"gemini-1.5-pro",
			"gemini-1.0-pro",
			"gemini-pro",
		]
		candidates: List[str] = []
		if env_model:
			candidates.append(env_model)
		for m in base:
			if m not in candidates:
				candidates.append(m)
		return candidates

	def _intersect_available_models(self, candidates: List[str]) -> List[str]:
		try:
			available_models = genai.list_models()
			available_names = set()
			for m in available_models:
				if "generateContent" in getattr(m, "supported_generation_methods", []) and getattr(m, "name", ""):
					name = m.name
					if name.startswith("models/"):
						name = name[len("models/") :]
					available_names.add(name)
			if available_names:
				filtered = [m for m in candidates if m in available_names]
				if filtered:
					return filtered
		except Exception:
			_LOGGER.debug("Could not list Gemini models; using static candidates")
		return candidates

	def _placeholder(self, diff_text: str) -> str:
		return (
			"GPT review is not configured. Set GEMINI_API_KEY to enable automated reviews.\n"
			"Preview of analyzed content (truncated):\n\n"
			f"{diff_text[:2000]}"
		)


