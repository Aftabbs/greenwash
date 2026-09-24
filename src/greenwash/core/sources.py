"""Where a set of changes comes from: a commit range, or the working tree."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .claim import NO_CLAIM, Claim
from .classify import detect_language, detect_role
from .diff import parse_diff
from .model import FileChange, Hunk, Line

# Untracked files larger than this are skipped rather than read into memory.
MAX_UNTRACKED_BYTES = 512 * 1024

# `-M` reports renames as renames, so a moved test file is one change, not a
# deletion plus an addition. `core.quotepath=false` keeps non-ASCII paths readable.
_GIT = ["git", "-c", "core.quotepath=false"]
_DIFF = ["diff", "--unified=0", "-M", "--no-color", "--no-ext-diff"]


class GitError(RuntimeError):
    """git refused to answer; callers turn this into an exit code."""


def run_git(args: list[str], repo: Path) -> str:
    result = subprocess.run(
        [*_GIT, *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


@dataclass(slots=True)
class Changes:
    """A parsed change set, plus whatever was claimed about it."""

    files: list[FileChange] = field(default_factory=list)
    claim: Claim = NO_CLAIM

    @property
    def test_files(self) -> list[FileChange]:
        return [f for f in self.files if f.role == "test"]

    @property
    def source_files(self) -> list[FileChange]:
        return [f for f in self.files if f.role == "source"]

    def relocated(self) -> set[str]:
        """Every non-blank added line in the change.

        Code moved between files is removed in one place and added in another.
        Without this, reorganising files reads as mass deletion.
        """
        return {ln.stripped for f in self.files for ln in f.added if ln.stripped}


def _annotate(files: list[FileChange]) -> list[FileChange]:
    for change in files:
        change.language = detect_language(change.path)
        change.role = detect_role(change.path)
    return files


def _has_head(repo: Path) -> bool:
    try:
        run_git(["rev-parse", "--verify", "--quiet", "HEAD"], repo)
    except GitError:
        return False
    return True


def _as_new_file(repo: Path, path: str) -> FileChange | None:
    """Represent an untracked file as an addition of every line in it."""
    target = repo / path
    try:
        if target.stat().st_size > MAX_UNTRACKED_BYTES:
            return None
        data = target.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return FileChange(path=path, is_new=True, is_binary=True)
    lines = data.decode("utf-8", errors="replace").splitlines()
    hunk = Hunk(
        0, 0, 1, len(lines), [Line(text, "+", None, number) for number, text in enumerate(lines, 1)]
    )
    return FileChange(path=path, is_new=True, hunks=[hunk] if lines else [])


def _untracked(repo: Path, *, include_index: bool = False) -> list[FileChange]:
    args = ["ls-files", "--others", "--exclude-standard", "-z"]
    if include_index:
        args.insert(1, "--cached")
    paths = [p for p in run_git(args, repo).split("\0") if p]
    return [c for c in (_as_new_file(repo, p) for p in paths) if c is not None]


def from_range(repo: Path, rev_range: str, claim: Claim = NO_CLAIM) -> Changes:
    """Changes introduced by a commit range, such as `HEAD~1..HEAD`."""
    diff = run_git([*_DIFF, rev_range], repo)
    return Changes(files=_annotate(parse_diff(diff)), claim=claim)


def from_worktree(repo: Path) -> Changes:
    """Everything not yet committed: staged, unstaged, and untracked files.

    This is what an agent has just done, before anyone has committed it. A repo
    with no commits yet is treated as one big addition.
    """
    if not _has_head(repo):
        return Changes(files=_annotate(_untracked(repo, include_index=True)))
    tracked = parse_diff(run_git([*_DIFF, "HEAD"], repo))
    return Changes(files=_annotate(tracked + _untracked(repo)))


def commit_message(repo: Path, rev_range: str) -> Claim:
    target = rev_range.split("..")[-1] or "HEAD"
    return Claim(text=run_git(["log", "-1", "--format=%B", target], repo), source="commit-message")


def git_dir(repo: Path) -> Path:
    """The repository's `.git` directory, for state that must not touch the tree."""
    return (repo / run_git(["rev-parse", "--git-dir"], repo).strip()).resolve()
