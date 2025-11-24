import argparse
import os
import sys
from typing import List, Optional

import uvicorn

try:
	from dotenv import load_dotenv  # type: ignore
	load_dotenv()
except Exception:
	pass

from app.config import AppConfig, read_env
from app.logging_config import configure_logging
from app.vcs.gitlab_service import GitLabService
from app.review.gemini_review import GeminiReviewGenerator
from app.webhook_processor import WebhookProcessor
from app.server import create_app

_LOGGER = configure_logging()


def build_services(cfg: AppConfig) -> WebhookProcessor:
	gl_service = GitLabService(cfg.gitlab_url, cfg.gitlab_token)
	reviewer = GeminiReviewGenerator(api_key=cfg.gemini_api_key, model=cfg.gemini_model)
	return WebhookProcessor(service=gl_service, reviewer=reviewer, webhook_secret=cfg.webhook_secret)


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
	uvicorn.run(app, host=cfg.host, port=cfg.port)


def cmd_list_projects(args: argparse.Namespace) -> None:
	cfg = AppConfig()
	service = GitLabService(cfg.gitlab_url, cfg.gitlab_token)
	for p in service.list_membership_projects():
		default_branch = getattr(p, "default_branch", None)
		print(f"{p.id}\t{p.path_with_namespace}\tdefault={default_branch}")


def cmd_test_mr(args: argparse.Namespace) -> None:
	cfg = AppConfig()
	service = GitLabService(cfg.gitlab_url, cfg.gitlab_token)
	project_id = int(args.project_id)
	res = service.create_test_mr(
		project_id=project_id,
		target_branch=args.target_branch,
		branch=args.branch,
		file_path=args.file_path,
		title=args.title,
	)
	print(f"Created MR !{res['iid']} in project {res['project_path']}")
	if res.get("web_url"):
		print(res["web_url"])


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
	parser = build_arg_parser()
	args = parser.parse_args()
	try:
		args.func(args)
	except AttributeError:
		parser.print_help(sys.stderr)
		sys.exit(2)


if __name__ == "__main__":
	main()