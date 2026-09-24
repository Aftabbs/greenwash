"""Sweep a repository's history and report how often greenwash speaks up.

Most of a mature project's history is honest human work, so anything flagged here
is either a genuine signal or noise we need to fix.

Usage:  python scripts/replay.py <repo-path> [n-commits]   (after `pip install -e .`)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

from greenwash.core.claim import Claim
from greenwash.core.detectors import run_all
from greenwash.core.sources import GitError, from_range

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("limit", nargs="?", type=int, default=50)
    parser.add_argument("--show", type=int, default=10, help="flagged commits to print")
    args = parser.parse_args()

    revs = git(args.repo, "log", f"-{args.limit}", "--no-merges", "--format=%H").split()

    by_rule: Counter[str] = Counter()
    audited = flagged = 0
    details = []

    for rev in revs:
        try:
            message = git(args.repo, "log", "-1", "--format=%B", rev)
            changes = from_range(args.repo, f"{rev}~1..{rev}", Claim(message, "commit-message"))
        except (GitError, subprocess.CalledProcessError):
            continue  # shallow-clone boundary or root commit
        audited += 1
        findings = run_all(changes)
        actionable = [f for f in findings if f.severity.actionable]
        for f in findings:
            by_rule[f.rule_id] += 1
        if actionable:
            flagged += 1
            subject = git(args.repo, "log", "-1", "--format=%s", rev).strip()
            details.append((rev[:8], subject, actionable))

    rate = (flagged / audited * 100) if audited else 0.0
    print("=" * 68)
    print(f"replay: {args.repo.name}")
    print("=" * 68)
    print(f"commits audited      : {audited}")
    print(f"commits with a flag  : {flagged}")
    print(f"actionable flag rate : {rate:.1f}%")
    print(f"by rule              : {dict(by_rule)}")

    for sha, subject, findings in details[: args.show]:
        print(f"\n  {sha}  {subject[:60]}")
        for f in findings:
            print(f"     [{f.severity.name.lower()}] {f.rule_id}  {f.path}:{f.line}")
            print(f"       {f.line_text.strip()[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
