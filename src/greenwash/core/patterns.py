"""Pattern banks and thresholds shared by the detectors.

Kept apart from the detection logic so the two can change independently: most
contributions add or tighten a pattern here without touching control flow.
"""

from __future__ import annotations

import re

ASSERTION = (
    re.compile(r"\bassert\b"),
    re.compile(r"\bself\.assert[A-Z]\w*\("),
    re.compile(r"\bpytest\.raises\("),
    re.compile(r"\bexpect\("),
    re.compile(r"\bassert\.\w+\("),
    re.compile(r"\.(toBe|toEqual|toMatch|toThrow|toHaveBeenCalled)\w*\("),
)

# The test stops running for everyone, permanently. `.only()` belongs here too:
# it silently disables every other test in the file. Anchored to the start of the
# line because a skip is a statement; the same text inside a string is data.
UNCONDITIONAL_SKIP = (
    re.compile(r"^\s*@pytest\.mark\.skip\b(?!if)"),
    re.compile(r"^\s*@unittest\.skip\b(?!If|Unless)"),
    re.compile(r"^\s*(it|test|describe|context)\.skip\("),
    re.compile(r"^\s*(xit|xdescribe|xtest)\("),
    re.compile(r"^\s*(it|test|describe)\.only\("),
)

# Skips written as a call. Usually inside `if sys.version_info < ...`, which makes
# them conditional; only an unguarded call is treated as disabling the test.
IMPERATIVE_SKIP = (
    re.compile(r"^\s*pytest\.skip\("),
    re.compile(r"^\s*t\.Skip(f|Now)?\("),
)
GUARD = re.compile(r"^\s*(if|elif|else)\b")
ENVIRONMENT_REASON = re.compile(
    r"python|version|platform|requires|only available|not (yet )?supported"
    r"|windows|linux|darwin|macos|runtime\.GOOS",
    re.IGNORECASE,
)

# Many asserts folded into one parametrized test: fewer assertion lines, same checks.
PARAMETRIZE = re.compile(r"^\s*@pytest\.mark\.parametrize\b|\b(it|test|describe)\.each\b")

# Gated on platform or interpreter version: compatibility work, not cheating.
CONDITIONAL_SKIP = (
    re.compile(r"^\s*@pytest\.mark\.skipif\b"),
    re.compile(r"^\s*@pytest\.mark\.xfail\b"),
    re.compile(r"^\s*@unittest\.skip(If|Unless)\b"),
)

SWALLOW_ONE_LINE = (
    re.compile(r"^\s*except\s+\w+.*:\s*(pass|\.\.\.)\s*$"),
    re.compile(r"\bcatch\s*(\([^)]*\))?\s*\{\s*\}"),
)
EXCEPT_HEADER = re.compile(r"^\s*except\b[^:]*:\s*$")
EXCEPT_TYPES = re.compile(r"^\s*except\b\s*(?P<types>.*?)\s*(?:\bas\s+\w+\s*)?:")

# Handlers that also swallow a failed assertion. Catching one specific, expected
# error (`except KeyError: pass`) is a deliberate idiom; catching these is not.
BROAD_EXCEPTIONS = frozenset({"", "Exception", "BaseException", "AssertionError"})
CATCH_HEADER = re.compile(r"\bcatch\s*(\([^)]*\))?\s*\{\s*$")
NOOP = re.compile(r"^\s*(pass|\.\.\.|\})?\s*$")
COMMENT = re.compile(r"^\s*(#|//|/\*|\*)")
TRAILING_COMMENT = re.compile(r"\s*(#|//).*$")

# A body that computes nothing. A hardcoded return is the silent failure, which
# makes it more dangerous than a loud `raise NotImplementedError`.
TRIVIAL_BODY = (
    re.compile(r"^\s*(pass|\.\.\.)\s*$"),
    re.compile(r"^\s*return\s*$"),
    re.compile(r"^\s*return\s+(None|True|False|null|undefined)\s*$"),
    re.compile(r"^\s*return\s+-?\d+(\.\d+)?\s*$"),
    re.compile(r"^\s*return\s+(\[\]|\{\})\s*$"),
)

# Wording that openly admits tests were moved or removed. Only ever used to
# lower severity, never to raise it.
ADMITS_REMOVAL = re.compile(
    r"\b(remove|delete|drop|prune|obsolete|dead|stale|cleanup|clean up|migrat\w+"
    r"|moved?|split|reorganis\w+|reorganiz\w+|consolidat\w+|extract\w*|refactor\w*"
    r"|revert\w*)\b",
    re.IGNORECASE,
)

# Above this many lost assertions in one file, report a single summary line.
MAX_LISTED_ASSERTIONS = 5

# A deleted test file whose lines mostly reappear elsewhere was moved.
RELOCATION_RATIO = 0.6

# How far below a handler header to look for its body.
BODY_LOOKAHEAD = 3
