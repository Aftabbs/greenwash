"""greenwash: catch coding agents that weaken your tests and report success."""

from .__about__ import __version__
from .core.detectors import run_all
from .core.model import Finding, Severity
from .core.sources import Changes, from_range, from_worktree

__all__ = [
    "Changes",
    "Finding",
    "Severity",
    "__version__",
    "from_range",
    "from_worktree",
    "run_all",
]
