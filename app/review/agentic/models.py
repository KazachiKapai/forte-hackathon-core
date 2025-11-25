from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class ProjectContext:
	name: str = "Default Project"
	description: str = ""
	tech_stack: List[str] = field(default_factory=list)
	architecture: List[str] = field(default_factory=list)
	testing_standards: str = ""
	coding_guidelines: str = ""


@dataclass
class AgentPayload:
	title: str
	description: str
	diff_text: str
	changed_files: List[Tuple[str, str]]
	commit_messages: List[str]
	project_context: ProjectContext

	def files_blob(self, max_files: int = 8, max_chars_per_file: int = 1500) -> str:
		if not self.changed_files:
			return ""
		lines: List[str] = []
		for path, content in self.changed_files[:max_files]:
			snippet = content[:max_chars_per_file]
			lines.append(f"File: {path}\n{snippet}")
		return "\n\n".join(lines)

	def commits_blob(self, max_commits: int = 10) -> str:
		if not self.commit_messages:
			return ""
		selected = self.commit_messages[:max_commits]
		return "\n".join(f"- {msg}" for msg in selected)


@dataclass
class AgentResult:
	key: str
	content: str = ""
	success: bool = True
	error: Optional[str] = None



