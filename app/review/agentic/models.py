from dataclasses import dataclass, field


@dataclass
class ProjectContext:
	name: str = "Default Project"
	description: str = ""
	tech_stack: list[str] = field(default_factory=list)
	architecture: list[str] = field(default_factory=list)
	testing_standards: str = ""
	coding_guidelines: str = ""


@dataclass
class AgentPayload:
	title: str
	description: str
	diff_text: str
	changed_files: list[tuple[str, str]]
	commit_messages: list[str]
	project_context: ProjectContext

	def files_blob(self, max_files: int = 8, max_chars_per_file: int = 1500) -> str:
		if not self.changed_files:
			return ""
		lines: list[str] = []
		for path, content in self.changed_files[:max_files]:
			snippet = content[:max_chars_per_file]
			lines.append(f"File: {path}\n{snippet}")
		return "\n\n".join(lines)

	def commits_blob(self, max_commits: int = 10) -> str:
		if not self.commit_messages:
			return ""
		selected = self.commit_messages[:max_commits]
		return "\n".join(f"- {msg}" for msg in selected)


	def files_with_line_numbers(self, max_files: int = 6, max_lines: int = 400) -> str:
		if not self.changed_files:
			return ""
		blocks: list[str] = []
		for path, content in self.changed_files[:max_files]:
			lines: list[str] = []
			for idx, line in enumerate(content.splitlines(), start=1):
				lines.append(f"{idx:04d}: {line}")
				if idx >= max_lines:
					break
			blocks.append(f"File: {path}\n" + "\n".join(lines))
		return "\n\n".join(blocks)


@dataclass
class AgentFinding:
	path: str
	line: int
	body: str
	source: str = ""


@dataclass
class AgentResult:
	key: str
	content: str = ""
	success: bool = True
	error: str | None = None
	findings: list[AgentFinding] = field(default_factory=list)



