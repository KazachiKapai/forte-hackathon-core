import argparse
import sys
from typing import Any

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from app.config.config import AppConfig
from app.config.logging_config import configure_logging
from app.integrations.jira_service import JiraService
from app.server import create_app
from app.server.bootstrap import build_services as _bootstrap_build_services
from app.vcs.gitlab_service import GitLabService

_LOGGER = configure_logging()


# Backward-compatible shim; delegate to server bootstrap
def build_services(cfg: AppConfig):
	return _bootstrap_build_services(cfg)


def _print_test_mr_result(res: dict[str, Any]) -> None:
	print(f"Created MR !{res['iid']} in project {res['project_path']}")
	if res.get("web_url"):
		print(res["web_url"])


def _maybe_create_jira_issue(cfg: AppConfig, service: GitLabService, args: argparse.Namespace, res: dict[str, Any]) -> None:
	if not (cfg.jira_url and cfg.jira_email and cfg.jira_api_token and cfg.jira_project_keys):
		return
	try:
		_ = service.get_project(int(args.project_id))
		jira = JiraService(
			base_url=cfg.jira_url,
			email=cfg.jira_email,
			api_token=cfg.jira_api_token,
			project_keys=cfg.jira_project_keys,
			max_issues=cfg.jira_max_issues,
			search_window=cfg.jira_search_window,
		)
		project_key = args.jira_project or (cfg.jira_project_keys[0] if cfg.jira_project_keys else None)
		if not project_key:
			print("No Jira project key set. Configure JIRA_PROJECT_KEYS or pass --jira-project KEY")
			return
		default_summary = "Add simple interest calculator, docs, and tests"
		summary = args.title or f"{default_summary} (!{res['iid']})"
		desc_lines = [
			f"Auto-created for MR !{res['iid']} in {res['project_path']}",
			f"URL: {res.get('web_url','')}",
			"Labels: autotest, webhook",
		]
		files = res.get("files") or []
		if files:
			desc_lines.append("Affected files:")
			for p in files:
				desc_lines.append(f"- {p}")
		if res.get("branch"):
			desc_lines.append(f"Branch: {res.get('branch')}")
		created = jira.create_issue(
			project_key=project_key,
			summary=summary,
			description="\n".join(desc_lines),
			labels=["autotest", "webhook"],
		)
		if created:
			print(f"Created Jira issue {created['key']} {created['url']}")
			try:
				mr_url = res.get("web_url", "")
				if mr_url:
					jira.add_remote_link(created["key"], mr_url, title=f"GitLab MR !{res['iid']}")
			except Exception as e2:
				print(f"Failed to link Jira issue to MR: {e2}")
	except Exception as e:
		print(f"Failed to create Jira issue: {e}")


def cmd_register_hooks(args: argparse.Namespace) -> None:
	cfg = AppConfig()
	processor = build_services(cfg)
	service = processor.service
	if args.project_id:
		target_ids = [int(x) for x in args.project_id]
		projects = [service.get_project(pid) for pid in target_ids]
	else:
		projects = service.list_membership_projects()
	created = 0
	existing = 0
	if not cfg.webhook_url:
		raise RuntimeError("WEBHOOK_URL is required to register hooks")
	for p in projects:
		was_created, hook_id = service.ensure_webhook_for_project(p, cfg.webhook_url, cfg.webhook_secret)
		if was_created:
			created += 1
			print(f"[hook] created for {p.path_with_namespace} (id={p.id}) hook_id={hook_id}")
		else:
			existing += 1
			print(f"[hook] exists for {p.path_with_namespace} (id={p.id}) hook_id={hook_id}")
	print(f"Done. created={created} existing={existing}")


def cmd_serve(args: argparse.Namespace) -> None:
	cfg = AppConfig()
	processor = build_services(cfg)
	app = create_app(processor)
	uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="debug")


def cmd_list_projects(args: argparse.Namespace) -> None:
	cfg = AppConfig()
	service = GitLabService(cfg.gitlab_url, cfg.gitlab_token)
	for p in service.list_membership_projects():
		default_branch = getattr(p, "default_branch", None)
		print(f"{p.id}\t{p.path_with_namespace}\tdefault={default_branch}")


def cmd_test_mr(args: argparse.Namespace) -> None:
	cfg = AppConfig()
	service = GitLabService(cfg.gitlab_url, cfg.gitlab_token)
	res = service.create_test_mr(
		project_id=int(args.project_id),
		target_branch=args.target_branch,
		branch=args.branch,
		file_path=args.file_path,
		title=args.title,
	)
	_print_test_mr_result(res)
	_maybe_create_jira_issue(cfg, service, args, res)


def cmd_test_mr2(args: argparse.Namespace) -> None:
	cfg = AppConfig()
	service = GitLabService(cfg.gitlab_url, cfg.gitlab_token)
	res = service.create_test_mr_v2(
		project_id=int(args.project_id),
		target_branch=args.target_branch,
		branch=args.branch,
		title=args.title,
	)
	_print_test_mr_result(res)
	_maybe_create_jira_issue(cfg, service, args, res)


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

	def cmd_list_jira_projects(_: argparse.Namespace) -> None:
		cfg = AppConfig()
		if not (cfg.jira_url and cfg.jira_email and cfg.jira_api_token):
			print("Jira is not configured. Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN.")
			return
		jira = JiraService(
			base_url=cfg.jira_url,
			email=cfg.jira_email,
			api_token=cfg.jira_api_token,
		)
		projs = jira.list_projects()
		if not projs:
			print("No projects found or insufficient permissions.")
			return
		for pr in projs:
			print(f"{pr.get('key','')}\t{pr.get('name','')}")

	p_test = sub.add_parser("test-mr", help="Create a test branch/commit/MR in a project")
	p_test.add_argument("--project-id", required=True, help="Target project ID")
	p_test.add_argument("--branch", help="Branch name to create/use (default: test-webhook-<timestamp>)")
	p_test.add_argument("--file-path", help="File path to create in the commit (default: webhook_test.txt)")
	p_test.add_argument("--target-branch", help="Target branch (default: project default)")
	p_test.add_argument("--title", help="Merge Request title")
	p_test.add_argument("--jira-project", help="Jira project key to create test issue (overrides JIRA_PROJECT_KEYS[0])")
	p_test.set_defaults(func=cmd_test_mr)
	p_test2 = sub.add_parser("test-mr-2", help="Create an intentionally imperfect MR to showcase reviews")
	p_test2.add_argument("--project-id", required=True, help="Target project ID")
	p_test2.add_argument("--branch", help="Branch name to create/use (default: test-webhook-<timestamp>)")
	p_test2.add_argument("--target-branch", help="Target branch (default: project default)")
	p_test2.add_argument("--title", help="Merge Request title")
	p_test2.add_argument("--jira-project", help="Jira project key to create test issue (overrides JIRA_PROJECT_KEYS[0])")
	p_test2.set_defaults(func=cmd_test_mr2)
	p_jls = sub.add_parser("list-jira-projects", help="List Jira projects (keys and names)")
	p_jls.set_defaults(func=cmd_list_jira_projects)
	return parser


def main() -> None:
	parser = build_arg_parser()
	args = parser.parse_args()
	try:
		args.func(args)
	except AttributeError:
		parser.print_help(sys.stderr)
		sys.exit(2)


if __name__ == "__main__":
	main()