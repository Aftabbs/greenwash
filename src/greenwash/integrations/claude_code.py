"""Claude Code hooks.

`stop` runs when the agent finishes a turn. If the uncommitted work weakens the
test suite, it exits 2; Claude Code then keeps the agent going and shows it the
report, so the agent can fix the problem before a person ever looks.

`guard` runs before an edit and refuses writes to protected paths such as the
test directory, which prevents the problem instead of reporting it afterwards.

Everything here fails open: bad input, a missing repo or a git error means
"say nothing", never a blocked agent.
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..core.detectors import run_all
from ..core.model import Finding
from ..core.sources import GitError, from_worktree, git_dir
from ..report.text import render

ALLOW = 0
BLOCK = 2

_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]")

STOP_PREAMBLE = (
    "greenwash: the uncommitted changes weaken the test suite. Restore the checks "
    "below, or tell the user plainly why each change is intentional."
)


@dataclass(frozen=True, slots=True)
class HookResult:
    exit_code: int
    message: str = ""


def _load(raw: str) -> dict:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _state_file(repo: Path, session_id: str) -> Path:
    safe = _SAFE_ID.sub("", session_id)[:64] or "default"
    return git_dir(repo) / "greenwash" / f"session-{safe}.json"


def _already_reported(state: Path) -> set[str]:
    try:
        return set(json.loads(state.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def _remember(state: Path, fingerprints: set[str]) -> None:
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(sorted(fingerprints)), encoding="utf-8")


def stop(raw_payload: str) -> HookResult:
    """Handle a Stop event.

    Blocks at most once per problem: a finding already shown in this session is
    never used to block again, and a stop that is itself a retry is never blocked.
    That is what keeps the hook from trapping the agent in a loop.
    """
    payload = _load(raw_payload)
    if not payload.get("cwd"):
        return HookResult(ALLOW)  # never guess which repository to audit
    repo = Path(payload["cwd"])
    try:
        findings = [f for f in run_all(from_worktree(repo)) if f.severity.actionable]
        state = _state_file(repo, str(payload.get("session_id", "")))
    except (GitError, OSError):
        return HookResult(ALLOW)
    if not findings:
        return HookResult(ALLOW)

    reported = _already_reported(state)
    fresh = {f.fingerprint for f in findings} - reported
    if not fresh or payload.get("stop_hook_active"):
        return HookResult(ALLOW)

    _remember(state, reported | fresh)
    return HookResult(BLOCK, f"{STOP_PREAMBLE}\n\n{render(_ordered(findings))}")


def _ordered(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (f.path, f.line))


def _relative(path: str, cwd: Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(cwd.resolve())
        except ValueError:
            return candidate.as_posix()
    return PurePosixPath(candidate.as_posix()).as_posix()


def is_protected(path: str, patterns: list[str]) -> bool:
    """Glob match where `**/` may also match nothing, so `**/test_*.py` covers
    a `test_x.py` at the repository root."""
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]):
            return True
    return False


def guard(raw_payload: str, protected: list[str]) -> HookResult:
    """Handle a PreToolUse event for file-editing tools."""
    payload = _load(raw_payload)
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target or not protected:
        return HookResult(ALLOW)
    path = _relative(str(target), Path(payload.get("cwd") or "."))
    if not is_protected(path, protected):
        return HookResult(ALLOW)
    return HookResult(
        BLOCK,
        f"greenwash: {path} is a protected test file in this project. Do not edit it "
        "to make a check pass. If the test itself is wrong, stop and ask the user.",
    )
