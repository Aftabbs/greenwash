"""Command line interface.

greenwash [check] [RANGE]      audit the working tree, or a commit range
greenwash install [--protect]  register the Claude Code hooks in this project
greenwash hook stop|guard      entry points Claude Code calls; not for humans
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .__about__ import __version__
from .core.claim import NO_CLAIM, Claim
from .core.detectors import run_all
from .core.model import Severity
from .core.sources import GitError, commit_message, from_range, from_worktree
from .integrations import claude_code
from .integrations.install import SettingsError, install, uninstall
from .report.text import DEFAULT_MAX_FINDINGS, render

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

SUBCOMMANDS = {"check", "install", "hook"}
DEFAULT_PROTECT = ["tests/**", "**/test_*.py", "**/*_test.py", "**/*.test.*", "**/*.spec.*"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="greenwash",
        description="Catch coding agents that weaken your tests and report success.",
    )
    parser.add_argument("--version", action="version", version=f"greenwash {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="audit changes (default command)")
    check.add_argument(
        "range", nargs="?", help="commit range such as HEAD~1..HEAD (default: uncommitted work)"
    )
    check.add_argument("--repo", type=Path, default=Path("."))
    check.add_argument("--claim", help="what the change claims to do, if not the commit message")
    check.add_argument(
        "--fail-on",
        choices=["high", "medium", "never"],
        default="never",
        help="exit 1 at this severity or above (default: never)",
    )
    check.add_argument("--max-findings", type=int, default=DEFAULT_MAX_FINDINGS)
    check.add_argument(
        "--verbose", action="store_true", help="also show informational notes, with rule ids"
    )

    setup = commands.add_parser("install", help="add the Claude Code hooks to a project")
    setup.add_argument("--repo", type=Path, default=Path("."))
    setup.add_argument(
        "--protect",
        nargs="*",
        metavar="GLOB",
        help=f"also block agent edits to these paths (no value: {' '.join(DEFAULT_PROTECT)})",
    )
    setup.add_argument(
        "--shared",
        action="store_true",
        help="write .claude/settings.json instead of settings.local.json",
    )
    setup.add_argument("--uninstall", action="store_true", help="remove the hooks")

    hook = commands.add_parser("hook", help="entry point for Claude Code hooks")
    hook.add_argument("event", choices=["stop", "guard"])
    hook.add_argument("--protect", nargs="*", default=[], metavar="GLOB")
    return parser


def _run_check(args: argparse.Namespace) -> int:
    try:
        if args.range is None:
            changes = from_worktree(args.repo)
        else:
            claim = Claim(args.claim, "cli") if args.claim else _commit_claim(args)
            changes = from_range(args.repo, args.range, claim)
    except GitError as err:
        print(f"error: {err}", file=sys.stderr)
        return EXIT_ERROR

    findings = [f for f in run_all(changes) if args.verbose or f.severity.actionable]
    if findings:
        print(render(findings, max_findings=args.max_findings, verbose=args.verbose))
    if args.fail_on == "never":
        return EXIT_OK
    threshold = Severity.parse(args.fail_on)
    return EXIT_FINDINGS if any(f.severity >= threshold for f in findings) else EXIT_OK


def _commit_claim(args: argparse.Namespace) -> Claim:
    try:
        return commit_message(args.repo, args.range)
    except GitError:
        return NO_CLAIM


def _run_install(args: argparse.Namespace) -> int:
    try:
        if args.uninstall:
            path = uninstall(args.repo, shared=args.shared)
            print(f"removed greenwash hooks from {path}" if path else "nothing to remove")
            return EXIT_OK
        protected = DEFAULT_PROTECT if args.protect == [] else (args.protect or [])
        path = install(args.repo, protected=protected, shared=args.shared)
    except SettingsError as err:
        print(f"error: {err}", file=sys.stderr)
        return EXIT_ERROR
    print(f"greenwash hooks written to {path}")
    if protected:
        print(f"agent edits blocked for: {' '.join(protected)}")
    return EXIT_OK


def _run_hook(args: argparse.Namespace) -> int:
    raw = sys.stdin.read()
    handlers = {
        "stop": lambda: claude_code.stop(raw),
        "guard": lambda: claude_code.guard(raw, args.protect),
    }
    result = handlers[args.event]()
    if result.message:
        print(result.message, file=sys.stderr)
    return result.exit_code


def _utf8(stream) -> None:
    if stream.encoding and stream.encoding.lower() not in ("utf-8", "utf8"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] not in SUBCOMMANDS and argv[0] not in ("-h", "--help", "--version")):
        argv.insert(0, "check")
    _utf8(sys.stdout)
    _utf8(sys.stderr)

    args = _parser().parse_args(argv)
    handlers = {"check": _run_check, "install": _run_install, "hook": _run_hook}
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
