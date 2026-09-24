"""Register the hooks in a project's Claude Code settings.

Writes to `.claude/settings.local.json` by default, which Claude Code treats as
personal and git-ignores, because the hook command points at this machine's
Python. Existing settings are merged, never replaced, and running install twice
changes nothing.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

MARKER = "-m greenwash"
EDIT_TOOLS = "Edit|Write|MultiEdit|NotebookEdit"


class SettingsError(RuntimeError):
    """The settings file exists but is not valid JSON; we refuse to overwrite it."""


def _python() -> str:
    # Forward slashes keep the path valid when hooks run under Git Bash on Windows.
    return Path(sys.executable).as_posix()


def stop_command() -> str:
    return f'"{_python()}" {MARKER} hook stop'


def guard_command(protected: list[str]) -> str:
    globs = " ".join(f"'{glob}'" for glob in protected)
    return f'"{_python()}" {MARKER} hook guard --protect {globs}'


def settings_path(repo: Path, *, shared: bool) -> Path:
    name = "settings.json" if shared else "settings.local.json"
    return repo / ".claude" / name


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as err:
        raise SettingsError(f"{path} is not valid JSON ({err}); fix it and rerun") from err
    if not isinstance(data, dict):
        raise SettingsError(f"{path} does not contain a JSON object")
    return data


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".greenwash-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def _strip_ours(entries: list) -> list:
    """Drop any hook entry we installed earlier, keeping everyone else's."""
    kept = []
    for entry in entries:
        hooks = [h for h in entry.get("hooks", []) if MARKER not in h.get("command", "")]
        if hooks:
            kept.append({**entry, "hooks": hooks})
    return kept


def _set_event(hooks: dict, event: str, entry: dict | None) -> None:
    entries = _strip_ours(hooks.get(event, []))
    if entry is not None:
        entries.append(entry)
    if entries:
        hooks[event] = entries
    else:
        hooks.pop(event, None)


def install(repo: Path, *, protected: list[str], shared: bool = False) -> Path:
    """Add (or refresh) greenwash's hooks. Returns the settings file written."""
    path = settings_path(repo, shared=shared)
    settings = _read(path)
    hooks = settings.setdefault("hooks", {})
    _set_event(hooks, "Stop", {"hooks": [{"type": "command", "command": stop_command()}]})
    guard = None
    if protected:
        guard = {
            "matcher": EDIT_TOOLS,
            "hooks": [{"type": "command", "command": guard_command(protected)}],
        }
    _set_event(hooks, "PreToolUse", guard)
    _write_atomic(path, settings)
    return path


def uninstall(repo: Path, *, shared: bool = False) -> Path | None:
    """Remove greenwash's hooks and nothing else."""
    path = settings_path(repo, shared=shared)
    if not path.exists():
        return None
    settings = _read(path)
    hooks = settings.get("hooks", {})
    for event in ("Stop", "PreToolUse"):
        _set_event(hooks, event, None)
    if not hooks:
        settings.pop("hooks", None)
    _write_atomic(path, settings)
    return path
