"""Parser for `git diff` output that keeps line numbers.

Tracking `@@` hunk headers is what lets a finding say `tests/test_billing.py:47`
instead of just naming a file, and it keeps hunks separate so that lines from
different parts of a file are never mistaken for neighbours.
"""

from __future__ import annotations

import re

from .model import FileChange, Hunk, Line

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_BINARY = re.compile(r"^Binary files (?:a/)?(.+?) and (?:b/)?(.+?) differ$")
_NO_NEWLINE = r"\ No newline at end of file"
_DEV_NULL = "/dev/null"


def _clean_path(raw: str) -> str:
    path = raw.strip()
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path.replace("\\", "/")


class _Parser:
    """A line-at-a-time state machine over one diff."""

    def __init__(self) -> None:
        self.files: list[FileChange] = []
        self._file: FileChange | None = None
        self._hunk: Hunk | None = None
        self._old = self._new = 0
        self._left_old = self._left_new = 0
        self._reset_header()

    def _reset_header(self) -> None:
        self._is_new = self._is_deleted = False
        self._rename_from: str | None = None
        self._old_path = ""

    def _start_file(self, path: str, old_path: str | None = None) -> None:
        self._file = FileChange(
            path=path, old_path=old_path, is_new=self._is_new, is_deleted=self._is_deleted
        )
        self.files.append(self._file)
        self._hunk = None

    def _in_hunk_body(self) -> bool:
        return self._hunk is not None and (self._left_old > 0 or self._left_new > 0)

    def feed(self, raw: str) -> None:
        line = raw.rstrip("\r")
        # Inside a hunk, the header counts say exactly how many body lines follow,
        # so a removed `-- sql comment` is never mistaken for a `--- a/file` header.
        if self._in_hunk_body() and (line == "" or line[0] in "+- "):
            self._body_line(line or " ")
        elif line.startswith("diff --git"):
            self._file = self._hunk = None
            self._reset_header()
        elif not self._header_line(line):
            self._hunk_header(line)

    def _header_line(self, line: str) -> bool:
        if line.startswith("new file mode"):
            self._is_new = True
        elif line.startswith("deleted file mode"):
            self._is_deleted = True
        elif line.startswith("rename from "):
            self._rename_from = _clean_path(line[len("rename from ") :])
        elif line.startswith("rename to "):
            self._start_file(_clean_path(line[len("rename to ") :]), self._rename_from)
        elif line.startswith(("Binary files", "GIT binary patch")):
            self._binary(line)
        elif line.startswith("--- "):
            self._old_path = _clean_path(line[4:])
        elif line.startswith("+++ "):
            self._new_path(_clean_path(line[4:]))
        else:
            return False
        return True

    def _new_path(self, path: str) -> None:
        # A deleted file reports `+++ /dev/null`; its real name is in the `---` line.
        if path == _DEV_NULL:
            path = self._old_path
        if path == _DEV_NULL:
            self._file = self._hunk = None
            return
        already_renamed = (
            self._file is not None and self._file.is_renamed and self._file.path == path
        )
        if not already_renamed:
            self._start_file(path)
        self._hunk = None

    def _binary(self, line: str) -> None:
        if self._file is None:
            match = _BINARY.match(line)
            path = _clean_path(match.group(2)) if match else self._old_path
            if path:
                self._start_file(path)
        if self._file is not None:
            self._file.is_binary = True

    def _hunk_header(self, line: str) -> None:
        match = _HUNK_HEADER.match(line)
        if not match or self._file is None:
            return
        old_start, old_count, new_start, new_count = match.groups()
        self._hunk = Hunk(int(old_start), int(old_count or 1), int(new_start), int(new_count or 1))
        self._file.hunks.append(self._hunk)
        self._old, self._new = int(old_start), int(new_start)
        self._left_old, self._left_new = self._hunk.old_count, self._hunk.new_count

    def _body_line(self, line: str) -> None:
        assert self._hunk is not None
        marker, text = line[0], line[1:]
        if marker == "+":
            self._hunk.lines.append(Line(text, "+", None, self._new))
            self._new += 1
            self._left_new -= 1
        elif marker == "-":
            self._hunk.lines.append(Line(text, "-", self._old, None))
            self._old += 1
            self._left_old -= 1
        else:
            self._hunk.lines.append(Line(text, " ", self._old, self._new))
            self._old += 1
            self._new += 1
            self._left_old -= 1
            self._left_new -= 1


def parse_diff(diff_text: str) -> list[FileChange]:
    """Parse unified diff text into per-file, per-hunk line records.

    Handles renames, new and deleted files, binary files, CRLF line endings and
    Windows path separators.
    """
    parser = _Parser()
    for raw in diff_text.splitlines():
        if raw.rstrip("\r") != _NO_NEWLINE:
            parser.feed(raw)
    return [f for f in parser.files if f.path]
