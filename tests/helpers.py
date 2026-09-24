"""Shared helpers for tests that need a real git repository."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout


def init_repo(path: Path, files: dict[str, str] | None = None, *, commit: bool = True) -> Path:
    """Create a git repo at `path`, optionally with committed files."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    for name, content in (files or {}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if files and commit:
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", "initial")
    return path
