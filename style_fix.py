#!/usr/bin/env python3
"""
Auto-fix Python code style for this repository.

Tools:
- pyupgrade (modernize syntax for the target Python version)
- ruff (linting with autofix for common rule sets)
- isort (import sorting)
- codespell (common typos)

This script:
1) Ensures required tools are installed (unless --no-install is set)
2) Selects files tracked by git (falls back to scanning the tree)
3) Applies safe auto-fixes in a sensible order
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from shutil import which
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent


def run(
	cmd: list[str],
	cwd: Path | None = None,
	check: bool = True,
	capture_output: bool = False,
) -> subprocess.CompletedProcess:
	return subprocess.run(
		cmd,
		cwd=str(cwd or REPO_ROOT),
		check=check,
		capture_output=capture_output,
	)


def ensure_tool(name: str, install_name: str | None = None, no_install: bool = False) -> None:
	if which(name):
		return
	if no_install:
		print(f"[skip] {name} not found and --no-install set")
		return
	pkg = install_name or name
	print(f"[install] {pkg}")
	run([sys.executable, "-m", "pip", "install", "--upgrade", pkg], check=True)


def list_python_files() -> list[str]:
	try:
		cp = run(["git", "ls-files", "*.py"], check=True, capture_output=True)
		out = cp.stdout.decode("utf-8") if cp.stdout else ""
		if not out:
			# git may buffer to stderr depending on env; fall through to scan
			raise RuntimeError("empty git output")
		return [line.strip() for line in out.splitlines() if line.strip()]
	except Exception:
		files: list[str] = []
		for p in REPO_ROOT.rglob("*.py"):
			# respect common exclusions
			if any(seg in {".venv", "venv", ".git", "__pycache__"} for seg in p.parts):
				continue
			files.append(str(p.relative_to(REPO_ROOT)))
		return files


def batched(seq: list[str], size: int = 200) -> Iterable[list[str]]:
	for i in range(0, len(seq), size):
		yield seq[i : i + size]


def main() -> int:
	parser = argparse.ArgumentParser(description="Auto-fix code style (pyupgrade, ruff, isort, codespell).")
	parser.add_argument("--no-install", action="store_true", help="Do not auto-install missing tools")
	parser.add_argument("--target-py", default="py312-plus", help="pyupgrade target (default: py312-plus)")
	args = parser.parse_args()

	# 1) Ensure tools
	ensure_tool("pyupgrade", no_install=args.no_install)
	ensure_tool("ruff", no_install=args.no_install)
	ensure_tool("isort", no_install=args.no_install)
	ensure_tool("codespell", no_install=args.no_install)

	# 2) Select files
	py_files = list_python_files()
	if not py_files:
		print("No Python files found.")
		return 0

	# 3) Apply fixes in order
	print("[step] pyupgrade")
	# Run per-file to isolate failures; pyupgrade exits non-zero on parse errors
	failed: list[str] = []
	for path in py_files:
		try:
			run(["pyupgrade", f"--{args.target_py}", "--keep-percent-format", path], check=True)
		except subprocess.CalledProcessError:
			failed.append(path)
	if failed:
		print(f"[warn] pyupgrade failed on {len(failed)} file(s). Continuing. Examples: {failed[:3]}")

	print("[step] ruff (autofix)")
	# Safe subset of rules; do not enforce line length to avoid churn
	run(["ruff", "check", ".", "--select", "E,F,I,UP", "--ignore", "E501", "--fix", "--exit-zero"])

	print("[step] isort")
	run(["isort", "--profile", "black", "--filter-files", "."])

	print("[step] codespell (write)")
	run(["codespell", "-w", "-L", "nd"], check=False)

	print("Done.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())


