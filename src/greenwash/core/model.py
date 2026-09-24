"""Shared value types.

Kept free of git, regex and IO so that everything downstream can be tested with
hand-built objects and no subprocess.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Literal

Side = Literal["+", "-", " "]
Role = Literal["test", "source", "other"]


class Severity(IntEnum):
    """Ordered so that comparisons read naturally: HIGH > MEDIUM > INFO."""

    INFO = 0
    MEDIUM = 1
    HIGH = 2

    @property
    def actionable(self) -> bool:
        """The single definition of "worth interrupting a human for"."""
        return self >= Severity.MEDIUM

    @classmethod
    def parse(cls, value: str) -> Severity:
        try:
            return cls[value.strip().upper()]
        except KeyError:
            raise ValueError(f"unknown severity: {value!r}") from None


@dataclass(frozen=True, slots=True)
class Line:
    """One line of a diff, with its position in the pre- and post-image."""

    text: str
    side: Side
    old_lineno: int | None = None
    new_lineno: int | None = None

    @property
    def lineno(self) -> int:
        """The line number to show a human: post-image where it exists."""
        return self.new_lineno if self.new_lineno is not None else (self.old_lineno or 0)

    @property
    def stripped(self) -> str:
        return self.text.strip()


@dataclass(slots=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[Line] = field(default_factory=list)

    @property
    def added(self) -> list[Line]:
        return [ln for ln in self.lines if ln.side == "+"]

    @property
    def removed(self) -> list[Line]:
        return [ln for ln in self.lines if ln.side == "-"]


@dataclass(slots=True)
class FileChange:
    """Everything that happened to one file in one change."""

    path: str
    old_path: str | None = None  # set when the file was renamed
    hunks: list[Hunk] = field(default_factory=list)
    is_new: bool = False
    is_deleted: bool = False
    is_binary: bool = False
    language: str = "unknown"
    role: Role = "source"

    @property
    def added(self) -> list[Line]:
        return [ln for h in self.hunks for ln in h.lines if ln.side == "+"]

    @property
    def removed(self) -> list[Line]:
        return [ln for h in self.hunks for ln in h.lines if ln.side == "-"]

    @property
    def is_renamed(self) -> bool:
        return self.old_path is not None and self.old_path != self.path

    @property
    def is_test(self) -> bool:
        return self.role == "test"


_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Finding:
    """A single reported problem, anchored to a real line."""

    rule_id: str
    severity: Severity
    message: str
    path: str
    line: int
    line_text: str

    @property
    def fingerprint(self) -> str:
        """Stable identity for baselines.

        Deliberately excludes the line number: line numbers shift with unrelated
        edits, and a baseline keyed on them would decay within a day.
        """
        normalized = _WHITESPACE.sub(" ", self.line_text).strip()
        raw = f"{self.rule_id}\0{self.path}\0{normalized}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]
