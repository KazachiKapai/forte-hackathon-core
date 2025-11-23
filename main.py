import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import gitlab
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn
import logging

try:
	# Gemini client
	import google.generativeai as genai  # type: ignore
	_HAS_GEMINI = True
except Exception:
	_HAS_GEMINI = False

try:
	# Load .env if present
	from dotenv import load_dotenv  # type: ignore
	load_dotenv()
except Exception:
	pass

# Configure logging level from env (after .env is loaded)
_LOG_LEVEL_NAME = os.environ.get("LOG_LEVEL", "INFO").upper()
try:
	logging.basicConfig(
		level=getattr(logging, _LOG_LEVEL_NAME, logging.INFO),
		format="%(asctime)s %(levelname)s %(name)s: %(message)s",
	)
except Exception:
	# Fallback in case of invalid level
	logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger("mr_reviewer")

# ----------------------------
# Configuration and Utilities
# ----------------------------

def read_env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
	value = os.environ.get(name, default)
	if required and (value is None or value == ""):
		raise RuntimeError(f"Missing required environment variable: {name}")
	return value


def get_gitlab_client() -> gitlab.Gitlab:
	base_url = read_env("GITLAB_URL", "https://gitlab.com")
	private_token = read_env("GITLAB_TOKEN", required=True)
	gl = gitlab.Gitlab(base_url, private_token=private_token)
	return gl


def ensure_webhook_for_project(
	gl: gitlab.Gitlab,
	project: Any,
	webhook_url: str,
	secret_token: str,
) -> Tuple[bool, Optional[int]]:
	"""
	Ensure a project has a webhook for MR events pointing to webhook_url.
	Returns (created_or_existing, hook_id).
	"""
	existing_hooks = project.hooks.list(all=True)
	for hook in existing_hooks:
		if hook.url == webhook_url and getattr(hook, "merge_requests_events", False):
			# Update secret if changed
			if getattr(hook, "token", None) != secret_token:
				hook.token = secret_token
				hook.save()
			return (False, hook.id)

	new_hook = project.hooks.create(
		{
			"url": webhook_url,
			"enable_ssl_verification": True,
			"token": secret_token,
			"push_events": False,
			"tag_push_events": False,
			"merge_requests_events": True,
			"note_events": False,
			"job_events": False,
			"pipeline_events": False,
			"wiki_page_events": False,
		}
	)
	return (True, new_hook.id)


def collect_mr_diff_text(project: Any, mr_iid: int, max_chars: int = 50_000) -> str:
	"""
	Collects and concatenates MR diffs into a single text blob (capped by max_chars).
	"""
	mr = project.mergerequests.get(mr_iid)
	diffs_page = mr.diffs.list()
	if not diffs_page:
		return "No diffs found for this merge request."
	diff_obj = mr.diffs.get(diffs_page[0].get_id())
	collected: List[str] = []
	total_len = 0
	for d in diff_obj.diffs:
		one = f"File: {d.get('new_path') or d.get('old_path')}\n{d.get('diff', '')}\n"
		if total_len + len(one) > max_chars:
			collected.append(one[: max(0, max_chars - total_len)])
			break
		collected.append(one)
		total_len += len(one)
	return "\n".join(collected)


def generate_gpt_review(diff_text: str, title: str, description: str) -> str:
	"""
	Generate an MR review using Gemini.
	Returns a placeholder if not configured.
	"""
	gemini_key = os.environ.get("GEMINI_API_KEY")
	if not _HAS_GEMINI:
		_LOGGER.warning("Gemini is not available: google-generativeai package not installed")
	if not gemini_key:
		_LOGGER.info("GEMINI_API_KEY not set; skipping AI review")
	if _HAS_GEMINI and gemini_key:
		try:
			genai.configure(api_key=gemini_key)
			model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
			_LOGGER.debug(
				"Generating Gemini review",
				extra={
					"model": model_name,
					"title_len": len(title or ""),
					"description_len": len(description or ""),
					"diff_len": len(diff_text or ""),
				},
			)
			model = genai.GenerativeModel(model_name)
			system_instructions = (
				"You are an expert software reviewer. Provide a concise, actionable code review.\n"
				"- Identify bugs, security issues, and regressions.\n"
				"- Flag unclear naming or unreadable logic.\n"
				"- Suggest concrete improvements and tests.\n"
				"- If diff is large, focus on highest-risk areas first.\n"
			)
			prompt = (
				f"{system_instructions}\n\n"
				f"Merge Request Title: {title}\n\n"
				f"Description:\n{description}\n\n"
				f"Unified Diff:\n{diff_text}\n"
			)
			resp = model.generate_content(prompt)
			text = getattr(resp, "text", None) or ""
			header = "Automated GPT Review (Gemini)\n\n"
			_LOGGER.info("Gemini review generated successfully")
			return header + text.strip()
		except Exception as e:
			_LOGGER.exception("Gemini review failed")
			# fall through to placeholder
	# Placeholder if not configured or failed
	return (
		"GPT review is not configured. Set GEMINI_API_KEY to enable automated reviews.\n"
		"Preview of analyzed content (truncated):\n\n"
		f"{diff_text[:2000]}"
	)


# ----------------------------
# FastAPI application
# ----------------------------

def create_app() -> FastAPI:
	app = FastAPI()

	@app.get("/health")
	async def health() -> Dict[str, str]:
		return {"status": "ok"}

	@app.post("/gitlab/webhook")
	async def gitlab_webhook(
		request: Request,
		x_gitlab_event: Optional[str] = Header(default=None, alias="X-Gitlab-Event"),
		x_gitlab_token: Optional[str] = Header(default=None, alias="X-Gitlab-Token"),
	) -> JSONResponse:
		secret = read_env("GITLAB_WEBHOOK_SECRET", required=True)
		if not x_gitlab_token or x_gitlab_token != secret:
			raise HTTPException(status_code=401, detail="Invalid webhook token")
		if x_gitlab_event != "Merge Request Hook":
			# Ignore other event types
			return JSONResponse({"status": "ignored", "reason": "unsupported_event"}, status_code=202)

		payload = await request.json()
		object_kind = payload.get("object_kind")
		if object_kind != "merge_request":
			return JSONResponse({"status": "ignored", "reason": "not_merge_request"}, status_code=202)

		attributes = payload.get("object_attributes", {}) or {}
		action = attributes.get("action")
		project_info = payload.get("project", {}) or {}
		project_id = project_info.get("id")
		mr_iid = attributes.get("iid")
		title = attributes.get("title", "")
		description = attributes.get("description") or ""

		if project_id is None or mr_iid is None:
			raise HTTPException(status_code=400, detail="Missing project_id or mr_iid")
		# Coerce and validate IDs
		try:
			project_id = int(project_id)
			mr_iid = int(mr_iid)
		except Exception:
			raise HTTPException(status_code=400, detail="project_id and mr_iid must be integers")
		if project_id <= 0 or mr_iid <= 0:
			raise HTTPException(status_code=400, detail="project_id and mr_iid must be positive integers")

		# React only to meaningful actions
		if action not in {"open", "reopen", "update"}:
			return JSONResponse({"status": "ignored", "action": action}, status_code=202)

		gl = get_gitlab_client()
		try:
			project = gl.projects.get(project_id)
		except gitlab.exceptions.GitlabGetError as e:
			raise HTTPException(status_code=404, detail=f"GitLab project not found: {e}") from e

		# Validate MR exists
		try:
			_ = project.mergerequests.get(mr_iid)
		except gitlab.exceptions.GitlabGetError as e:
			raise HTTPException(status_code=404, detail=f"GitLab merge request not found: {e}") from e

		diff_text = collect_mr_diff_text(project, int(mr_iid))
		review_body = generate_gpt_review(diff_text, title=title, description=description)

		try:
			mr = project.mergerequests.get(mr_iid)
			mr.notes.create({"body": review_body})
		except Exception as e:
			raise HTTPException(status_code=500, detail=f"Failed to post MR note: {e}")

		return JSONResponse({"status": "ok", "posted": True})

	return app


# ----------------------------
# CLI commands
# ----------------------------

def cmd_register_hooks(args: argparse.Namespace) -> None:
	gl = get_gitlab_client()
	webhook_url = read_env("WEBHOOK_URL", required=True)
	secret = read_env("GITLAB_WEBHOOK_SECRET", required=True)

	target_project_ids: Optional[List[int]] = None
	if args.project_id:
		target_project_ids = [int(x) for x in args.project_id]

	if target_project_ids:
		projects: List[Any] = []
		for pid in target_project_ids:
			projects.append(gl.projects.get(pid))
	else:
		projects = gl.projects.list(membership=True, all=True)

	created = 0
	existing = 0
	for p in projects:
		was_created, hook_id = ensure_webhook_for_project(gl, p, webhook_url, secret)
		if was_created:
			created += 1
			print(f"[hook] created for {p.path_with_namespace} (id={p.id}) hook_id={hook_id}")
		else:
			existing += 1
			print(f"[hook] exists for {p.path_with_namespace} (id={p.id}) hook_id={hook_id}")
	print(f"Done. created={created} existing={existing}")


def cmd_serve(args: argparse.Namespace) -> None:
	app = create_app()
	host = read_env("HOST", "0.0.0.0")
	port_str = read_env("PORT", "8080")
	try:
		port = int(port_str or "8080")
	except Exception:
		port = 8080
	uvicorn.run(app, host=host, port=port)


def cmd_list_projects(args: argparse.Namespace) -> None:
	gl = get_gitlab_client()
	projects = gl.projects.list(membership=True, all=True)
	for p in projects:
		default_branch = getattr(p, "default_branch", None)
		print(f"{p.id}\t{p.path_with_namespace}\tdefault={default_branch}")


def cmd_test_mr(args: argparse.Namespace) -> None:
	gl = get_gitlab_client()
	project_id = int(args.project_id)
	project = gl.projects.get(project_id)
	target_branch = args.target_branch or getattr(project, "default_branch", None) or "main"
	branch_name = args.branch or f"test-webhook-{int(time.time())}"
	file_path = args.file_path or "webhook_test.txt"
	title = args.title or f"Webhook Test MR {branch_name}"

	# Create branch (ignore if exists)
	try:
		project.branches.create({"branch": branch_name, "ref": target_branch})
	except Exception:
		pass

	# Commit a change
	project.commits.create(
		{
			"branch": branch_name,
			"commit_message": "test: trigger webhook",
			"actions": [
				{"action": "create", "file_path": file_path, "content": f"hello webhook {int(time.time())}\n"}
			],
		}
	)

	# Create MR
	mr = project.mergerequests.create(
		{"source_branch": branch_name, "target_branch": target_branch, "title": title}
	)
	web_url = getattr(mr, "web_url", None)
	print(f"Created MR !{mr.iid} in project {project.path_with_namespace}")
	if web_url:
		print(web_url)


def build_arg_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="GitLab MR Webhook + GPT Reviewer")
	sub = parser.add_subparsers(dest="command", required=True)

	p_reg = sub.add_parser("register-hooks", help="Register MR webhooks for membership projects or given IDs")
	p_reg.add_argument("--project-id", action="append", help="Project ID to target (repeatable)")
	p_reg.set_defaults(func=cmd_register_hooks)

	p_srv = sub.add_parser("serve", help="Run the webhook HTTP server")
	p_srv.set_defaults(func=cmd_serve)

	p_ls = sub.add_parser("list-projects", help="List projects where you have membership")
	p_ls.set_defaults(func=cmd_list_projects)

	p_test = sub.add_parser("test-mr", help="Create a test branch/commit/MR in a project")
	p_test.add_argument("--project-id", required=True, help="Target project ID")
	p_test.add_argument("--branch", help="Branch name to create/use (default: test-webhook-<timestamp>)")
	p_test.add_argument("--file-path", help="File path to create in the commit (default: webhook_test.txt)")
	p_test.add_argument("--target-branch", help="Target branch (default: project default)")
	p_test.add_argument("--title", help="Merge Request title")
	p_test.set_defaults(func=cmd_test_mr)
	return parser


def main() -> None:
	# Security note: you previously pasted a personal access token in code.
	# For safety, move all secrets to environment variables (see README).
	parser = build_arg_parser()
	args = parser.parse_args()
	try:
		args.func(args)
	except AttributeError:
		parser.print_help(sys.stderr)
		sys.exit(2)


if __name__ == "__main__":
	main()