"""The package imports and the command line is wired up."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "greenwash", *args], capture_output=True, text=True
    )


def test_version():
    result = _run("--version")
    assert result.returncode == 0
    assert result.stdout.startswith("greenwash ")


def test_check_help_lists_options():
    result = _run("check", "--help")
    assert result.returncode == 0
    assert "--fail-on" in result.stdout


def test_bare_arguments_default_to_check(tmp_path: Path):
    """`greenwash --repo X` means `greenwash check --repo X`."""
    result = _run("--repo", str(tmp_path))
    assert result.returncode == 2
    assert "error:" in result.stderr
