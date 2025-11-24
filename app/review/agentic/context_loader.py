import json
from pathlib import Path
from typing import Any, Dict

from .models import ProjectContext


def load_project_context(path: str) -> ProjectContext:
	context_path = Path(path)
	if not context_path.exists():
		return ProjectContext()
	try:
		raw = context_path.read_text(encoding="utf-8")
		data: Dict[str, Any] = json.loads(raw)
	except Exception:
		return ProjectContext()
	return ProjectContext(
		name=data.get("name", "Default Project"),
		description=data.get("description", ""),
		tech_stack=list(data.get("tech_stack", [])),
		architecture=list(data.get("architecture", [])),
		testing_standards=data.get("testing_standards", ""),
		coding_guidelines=data.get("coding_guidelines", ""),
	)



