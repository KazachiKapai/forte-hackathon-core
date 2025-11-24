from typing import List, Optional, Tuple
import json
import re
from ..logging_config import configure_logging
from .base import TagClassifier

_LOGGER = configure_logging()

try:
	import google.generativeai as genai  # type: ignore
	_HAS_GEMINI = True
except Exception:
	_HAS_GEMINI = False


class GeminiTagClassifier(TagClassifier):
	def __init__(self, api_key: Optional[str], model: str, max_labels: int = 2) -> None:
		self.api_key = api_key
		self.model = model
		self.max_labels = max_labels

	def classify(
		self,
		title: str,
		description: str,
		diff_text: str,
		changed_files: List[Tuple[str, str]],
		commit_messages: List[str],
		candidates: List[str],
	) -> List[str]:
		if not _HAS_GEMINI or not self.api_key:
			return []
		if not candidates:
			return []
		try:
			genai.configure(api_key=self.api_key)
			model = genai.GenerativeModel(self.model)
			files_blob = ""
			if changed_files:
				parts: List[str] = []
				for path, content in changed_files[:10]:
					parts.append(f"File: {path}\nContent:\n{content}\n")
				files_blob = "\n".join(parts)
			commits_blob = ""
			if commit_messages:
				commits_blob = "\n".join(f"- {m}" for m in commit_messages[:20])
			choices = ", ".join(candidates)
			maxn = max(1, int(self.max_labels or 1))
			prompt = (
				"You are labeling a merge request with up to N labels from the provided set.\n"
				"- Return ONLY a JSON array of strings (no prose), e.g.: [\"bug\", \"docs\"]\n"
				"- Choose at most N labels, all from the allowed set, no extras.\n"
				"- If none apply, return []\n\n"
				f"N = {maxn}\n"
				f"Allowed labels: {choices}\n\n"
				f"Merge Request Title: {title}\n\n"
				f"Description:\n{description}\n\n"
				f"Unified Diff:\n{diff_text}\n\n"
				f"Changed Files:\n{files_blob}\n\n"
				f"Commit Messages:\n{commits_blob}\n"
			)
			resp = model.generate_content(prompt)
			raw = (getattr(resp, "text", None) or "").strip()
			if not raw:
				return []
			# Strip code fences if present
			if raw.startswith("```"):
				raw = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", raw)
				raw = re.sub(r"\s*```$", "", raw)
			selected: List[str] = []
			try:
				data = json.loads(raw)
				if isinstance(data, list):
					for item in data:
						if isinstance(item, str):
							selected.append(item.strip())
			except Exception:
				# Fallback: split by commas/newlines
				for part in re.split(r"[,;\n]+", raw):
					part = part.strip("`'\" \t\r")
					if part:
						selected.append(part)
			# Normalize, filter to candidates, dedupe, and cap to maxn
			cand_lc = {c.lower(): c for c in candidates}
			final: List[str] = []
			seen = set()
			for s in selected:
				key = s.lower()
				if key in cand_lc and key not in seen:
					final.append(cand_lc[key])
					seen.add(key)
				if len(final) >= maxn:
					break
			return final
		except Exception:
			return []


