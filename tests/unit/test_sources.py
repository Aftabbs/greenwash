"""Working-tree collection: what an agent changed before anyone committed."""

from __future__ import annotations

from pathlib import Path

from greenwash.core.sources import from_worktree

from ..helpers import git, init_repo


def _paths(repo: Path) -> dict[str, object]:
    return {f.path: f for f in from_worktree(repo).files}


def test_unstaged_edit_is_seen(tmp_path: Path):
    repo = init_repo(tmp_path, {"app.py": "x = 1\n"})
    (repo / "app.py").write_text("x = 2\n", encoding="utf-8")
    change = _paths(repo)["app.py"]
    assert [ln.text for ln in change.added] == ["x = 2"]


def test_staged_edit_is_seen(tmp_path: Path):
    repo = init_repo(tmp_path, {"app.py": "x = 1\n"})
    (repo / "app.py").write_text("x = 3\n", encoding="utf-8")
    git(repo, "add", "app.py")
    assert "app.py" in _paths(repo)


def test_untracked_file_counts_as_new(tmp_path: Path):
    repo = init_repo(tmp_path, {"app.py": "x = 1\n"})
    (repo / "tests").mkdir()
    (repo / "tests" / "test_new.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    change = _paths(repo)["tests/test_new.py"]
    assert change.is_new and change.role == "test"
    assert [ln.new_lineno for ln in change.added] == [1, 2]


def test_gitignored_files_are_skipped(tmp_path: Path):
    repo = init_repo(tmp_path, {".gitignore": "build/\n"})
    (repo / "build").mkdir()
    (repo / "build" / "out.py").write_text("x = 1\n", encoding="utf-8")
    assert "build/out.py" not in _paths(repo)


def test_binary_untracked_file_is_not_parsed(tmp_path: Path):
    repo = init_repo(tmp_path, {"app.py": "x = 1\n"})
    (repo / "logo.png").write_bytes(b"\x89PNG\x00\x00data")
    change = _paths(repo)["logo.png"]
    assert change.is_binary and change.added == []


def test_repo_without_commits(tmp_path: Path):
    repo = init_repo(tmp_path, {"app.py": "x = 1\n"}, commit=False)
    git(repo, "add", "app.py")
    (repo / "extra.py").write_text("y = 2\n", encoding="utf-8")
    assert {"app.py", "extra.py"} <= set(_paths(repo))


def test_clean_tree_has_no_changes(tmp_path: Path):
    repo = init_repo(tmp_path, {"app.py": "x = 1\n"})
    assert from_worktree(repo).files == []
