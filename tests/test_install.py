"""`greenwash install` must merge into existing settings, never replace them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from greenwash.integrations.install import (
    MARKER,
    SettingsError,
    install,
    settings_path,
    uninstall,
)

OTHER_HOOK = {"hooks": [{"type": "command", "command": "npm run lint"}]}


def _read(repo: Path, *, shared: bool = False) -> dict:
    return json.loads(settings_path(repo, shared=shared).read_text(encoding="utf-8"))


def _write(repo: Path, data: dict, *, shared: bool = False) -> None:
    path = settings_path(repo, shared=shared)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _ours(entries: list) -> list:
    return [h for e in entries for h in e["hooks"] if MARKER in h["command"]]


def test_fresh_install_writes_a_local_stop_hook(tmp_path: Path):
    path = install(tmp_path, protected=[])
    assert path.name == "settings.local.json"
    assert len(_ours(_read(tmp_path)["hooks"]["Stop"])) == 1
    assert "PreToolUse" not in _read(tmp_path)["hooks"]


def test_install_is_idempotent(tmp_path: Path):
    install(tmp_path, protected=["tests/**"])
    install(tmp_path, protected=["tests/**"])
    hooks = _read(tmp_path)["hooks"]
    assert len(_ours(hooks["Stop"])) == 1
    assert len(_ours(hooks["PreToolUse"])) == 1


def test_existing_settings_and_hooks_are_preserved(tmp_path: Path):
    _write(tmp_path, {"model": "opus", "hooks": {"Stop": [OTHER_HOOK]}})
    install(tmp_path, protected=[])
    settings = _read(tmp_path)
    assert settings["model"] == "opus"
    commands = [h["command"] for e in settings["hooks"]["Stop"] for h in e["hooks"]]
    assert "npm run lint" in commands and any(MARKER in c for c in commands)


def test_protect_registers_a_guard_for_edit_tools(tmp_path: Path):
    install(tmp_path, protected=["tests/**"])
    (entry,) = _read(tmp_path)["hooks"]["PreToolUse"]
    assert "Edit" in entry["matcher"] and "tests/**" in entry["hooks"][0]["command"]


def test_invalid_json_is_never_overwritten(tmp_path: Path):
    path = settings_path(tmp_path, shared=False)
    path.parent.mkdir(parents=True)
    path.write_text("{ broken", encoding="utf-8")
    with pytest.raises(SettingsError):
        install(tmp_path, protected=[])
    assert path.read_text(encoding="utf-8") == "{ broken"


def test_uninstall_removes_only_greenwash(tmp_path: Path):
    _write(tmp_path, {"hooks": {"Stop": [OTHER_HOOK]}})
    install(tmp_path, protected=["tests/**"])
    uninstall(tmp_path)
    assert _read(tmp_path) == {"hooks": {"Stop": [OTHER_HOOK]}}


def test_shared_install_targets_settings_json(tmp_path: Path):
    assert install(tmp_path, protected=[], shared=True).name == "settings.json"
