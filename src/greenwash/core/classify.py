"""Decide what a file is: which language, and whether it is a test."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

_TEST_PATHS = (
    re.compile(r"(^|/)tests?/"),
    re.compile(r"(^|/)__tests__/"),
    re.compile(r"(^|/)spec/"),
    re.compile(r"(^|/)test_[^/]*\.py$"),
    re.compile(r"[^/]*_test\.(py|go|js|ts)$"),
    re.compile(r"[^/]*\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs)$"),
)

_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".go": "go",
}


def detect_language(path: str) -> str:
    """Return the language for a path, or "unknown", which yields no findings."""
    return _LANGUAGES.get(PurePosixPath(path).suffix.lower(), "unknown")


def detect_role(path: str) -> str:
    normalized = path.replace("\\", "/")
    if any(rx.search(normalized) for rx in _TEST_PATHS):
        return "test"
    return "source" if detect_language(normalized) != "unknown" else "other"
