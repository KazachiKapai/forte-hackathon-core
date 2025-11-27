import json

from app.review.agentic.context_loader import load_project_context


def test_load_context_missing_file_returns_default(tmp_path):
	ctx = load_project_context(str(tmp_path / "nope.json"))
	assert ctx.name == "Default Project"
	assert ctx.tech_stack == []


def test_load_context_invalid_json_returns_default(tmp_path):
	p = tmp_path / "bad.json"
	p.write_text("{not json", encoding="utf-8")
	ctx = load_project_context(str(p))
	assert ctx.name == "Default Project"


def test_load_context_valid_json(tmp_path):
	p = tmp_path / "ok.json"
	p.write_text(json.dumps({"name": "Demo", "tech_stack": ["py"], "architecture": ["svc"], "testing_standards": "x"}), encoding="utf-8")
	ctx = load_project_context(str(p))
	assert ctx.name == "Demo"
	assert ctx.tech_stack == ["py"]
	assert ctx.architecture == ["svc"]
	assert ctx.testing_standards == "x"


