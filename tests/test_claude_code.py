"""Claude Code hook behaviour, driven with the JSON payloads Claude Code sends."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from greenwash.integrations.claude_code import ALLOW, BLOCK, guard, is_protected, stop

from .helpers import init_repo

TEST_FILE = "def test_total():\n    assert total(2) == 4\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return init_repo(
        tmp_path / "repo",
        {"tests/test_calc.py": TEST_FILE, "calc.py": "def total(x):\n    return x * 2\n"},
    )


def _stop_payload(repo: Path, *, session: str = "s1", retry: bool = False) -> str:
    return json.dumps(
        {
            "session_id": session,
            "cwd": str(repo),
            "stop_hook_active": retry,
            "hook_event_name": "Stop",
        }
    )


def _weaken(repo: Path) -> None:
    (repo / "tests" / "test_calc.py").write_text("def test_total():\n    pass\n", encoding="utf-8")


def test_clean_work_lets_the_agent_stop(repo: Path):
    result = stop(_stop_payload(repo))
    assert result.exit_code == ALLOW and result.message == ""


def test_weakened_test_blocks_with_the_offending_line(repo: Path):
    _weaken(repo)
    result = stop(_stop_payload(repo))
    assert result.exit_code == BLOCK
    assert "tests/test_calc.py:2" in result.message
    assert "assert total(2) == 4" in result.message


def test_same_problem_never_blocks_twice(repo: Path):
    _weaken(repo)
    assert stop(_stop_payload(repo)).exit_code == BLOCK
    assert stop(_stop_payload(repo)).exit_code == ALLOW


def test_a_new_session_is_told_again(repo: Path):
    _weaken(repo)
    assert stop(_stop_payload(repo, session="a")).exit_code == BLOCK
    assert stop(_stop_payload(repo, session="b")).exit_code == BLOCK


def test_retry_stop_is_never_blocked(repo: Path):
    """`stop_hook_active` means the agent is already continuing because of a hook."""
    _weaken(repo)
    assert stop(_stop_payload(repo, retry=True)).exit_code == ALLOW


def test_session_state_stays_out_of_the_working_tree(repo: Path):
    _weaken(repo)
    stop(_stop_payload(repo, session="../../escape"))
    assert list((repo / ".git" / "greenwash").iterdir())
    assert not (repo.parent / "escape").exists()


def test_outside_a_repo_fails_open(tmp_path: Path):
    assert stop(_stop_payload(tmp_path)).exit_code == ALLOW


@pytest.mark.parametrize("raw", ["", "not json", "[1, 2]"])
def test_malformed_payload_fails_open(raw: str):
    assert stop(raw).exit_code == ALLOW


def _edit_payload(path: str, cwd: str = "/project") -> str:
    return json.dumps({"cwd": cwd, "tool_name": "Edit", "tool_input": {"file_path": path}})


def test_guard_blocks_protected_edits():
    result = guard(_edit_payload("tests/test_calc.py"), ["tests/**"])
    assert result.exit_code == BLOCK
    assert "tests/test_calc.py" in result.message


def test_guard_allows_other_edits():
    assert guard(_edit_payload("src/calc.py"), ["tests/**"]).exit_code == ALLOW


def test_guard_resolves_absolute_paths(tmp_path: Path):
    target = tmp_path / "tests" / "test_x.py"
    assert guard(_edit_payload(str(target), str(tmp_path)), ["tests/**"]).exit_code == BLOCK


def test_guard_without_protected_paths_allows_everything():
    assert guard(_edit_payload("tests/test_calc.py"), []).exit_code == ALLOW


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("test_root.py", True),
        ("pkg/sub/test_deep.py", True),
        ("pkg/testing.py", False),
    ],
)
def test_double_star_prefix_also_matches_the_root(path: str, expected: bool):
    assert is_protected(path, ["**/test_*.py"]) is expected
