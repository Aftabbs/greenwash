"""Detectors: each one looks for a single way a change can weaken a test suite.

Every finding is anchored to a real line in the diff. Nothing here calls a model;
a check that reasons the way an agent reasons can be fooled the same way.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from . import patterns as p
from .model import FileChange, Finding, Hunk, Line, Severity
from .sources import Changes


def _matching(bank: Iterable[re.Pattern[str]], lines: Iterable[Line]) -> list[Line]:
    return [line for line in lines if any(rx.search(line.text) for rx in bank)]


def _is_trivial(line: Line) -> bool:
    return any(rx.match(line.text) for rx in p.TRIVIAL_BODY)


def _is_substantive(line: Line) -> bool:
    return bool(line.stripped) and not p.COMMENT.match(line.text) and not _is_trivial(line)


def _without_comment(text: str) -> str:
    return p.TRAILING_COMMENT.sub("", text).strip()


def _finding(
    rule_id: str, severity: Severity, message: str, change: FileChange, line: Line
) -> Finding:
    return Finding(rule_id, severity, message, change.path, line.lineno, line.text)


def _removal_severity(changes: Changes) -> Severity:
    admitted = p.ADMITS_REMOVAL.search(changes.claim.text)
    return Severity.INFO if admitted else Severity.HIGH


def _consolidated(change: FileChange) -> bool:
    """Assertions folded into a parametrized test, which keeps the checks."""
    added = change.added
    return bool(_matching([p.PARAMETRIZE], added)) and bool(_matching(p.ASSERTION, added))


def assertions_removed(changes: Changes) -> list[Finding]:
    """Assertions that vanished rather than moved elsewhere in the change."""
    relocated = changes.relocated()
    findings: list[Finding] = []
    for change in changes.test_files:
        lost = [ln for ln in _matching(p.ASSERTION, change.removed) if ln.stripped not in relocated]
        net = len(lost) - len(_matching(p.ASSERTION, change.added))
        if net <= 0:
            continue
        severity = Severity.INFO if _consolidated(change) else _removal_severity(changes)
        if net > p.MAX_LISTED_ASSERTIONS:
            message = f"{net} assertions removed from this file"
            findings.append(_finding("assertions.removed", severity, message, change, lost[0]))
            continue
        findings.extend(
            _finding("assertions.removed", severity, "assertion removed", change, ln)
            for ln in lost[:net]
        )
    return findings


def _net_added(bank: Iterable[re.Pattern[str]], change: FileChange) -> list[Line]:
    added = _matching(bank, change.added)
    removed = len(_matching(bank, change.removed))
    return added[: max(0, len(added) - removed)]


def _indent(text: str) -> int:
    return len(text) - len(text.lstrip())


def _is_guarded(change: FileChange, line: Line) -> bool:
    """True when a skip call sits inside an `if`, or names the environment it
    depends on. The enclosing `if` is the nearest earlier added line with less
    indentation."""
    if p.ENVIRONMENT_REASON.search(line.text):
        return True
    earlier = [
        ln
        for ln in change.added
        if ln.new_lineno is not None
        and line.new_lineno is not None
        and ln.new_lineno < line.new_lineno
        and ln.stripped
    ]
    for candidate in reversed(earlier):
        if _indent(candidate.text) < _indent(line.text):
            return bool(p.GUARD.match(candidate.text))
    return False


def tests_disabled(changes: Changes) -> list[Finding]:
    """Newly skipped tests. Unconditional skips and `.only()` are the classic way
    to turn a red suite green; platform- or version-gated skips are noted quietly."""
    findings: list[Finding] = []
    for change in changes.test_files:
        imperative = _net_added(p.IMPERATIVE_SKIP, change)
        disabled = _net_added(p.UNCONDITIONAL_SKIP, change)
        disabled += [ln for ln in imperative if not _is_guarded(change, ln)]
        conditional = _net_added(p.CONDITIONAL_SKIP, change)
        conditional += [ln for ln in imperative if _is_guarded(change, ln)]
        findings.extend(
            _finding("tests.disabled", Severity.HIGH, "test disabled", change, ln)
            for ln in disabled
        )
        findings.extend(
            _finding("tests.conditional_skip", Severity.INFO, "conditional skip added", change, ln)
            for ln in conditional
        )
    return findings


def _body_after(hunk: Hunk, anchor: Line) -> list[Line]:
    """Added lines directly below `anchor`, within the same hunk.

    With `--unified=0`, the next entry in a flat list of added lines can come from
    a different hunk hundreds of lines away, so the hunk boundary matters.
    """
    if anchor.new_lineno is None:
        return []
    return [
        ln
        for ln in hunk.added
        if ln.new_lineno is not None and 1 <= ln.new_lineno - anchor.new_lineno <= p.BODY_LOOKAHEAD
    ]


def _catches_broadly(text: str) -> bool:
    """True for handlers that would also swallow a failed assertion.

    JavaScript's `catch` has no type filter, so it is always broad.
    """
    match = p.EXCEPT_TYPES.match(text)
    if match is None:
        return True
    names = {name.strip(" ()") for name in match.group("types").split(",")}
    return bool(names & p.BROAD_EXCEPTIONS)


def _handler_kind(hunk: Hunk, line: Line) -> str | None:
    """Classify an added handler as silent, explained, narrow, or not a handler."""
    one_line = any(rx.search(line.text) for rx in p.SWALLOW_ONE_LINE)
    header = p.EXCEPT_HEADER.match(line.text) or p.CATCH_HEADER.search(line.text)
    if not one_line and not header:
        return None
    if not one_line:
        body = _body_after(hunk, line)
        if any(
            b.stripped and not p.NOOP.match(b.text) and not p.COMMENT.match(b.text) for b in body
        ):
            return None  # the handler does real work
        if any(p.COMMENT.match(b.text) for b in body):
            return "explained"
    return "silent" if _catches_broadly(line.text) else "narrow"


def failures_swallowed(changes: Changes) -> list[Finding]:
    """Exception handlers that make a failure disappear."""
    findings: list[Finding] = []
    for change in changes.files:
        pre_existing = {_without_comment(ln.text) for ln in change.removed}
        for hunk in change.hunks:
            for line in hunk.added:
                if _without_comment(line.text) in pre_existing:
                    continue  # the handler already existed; only its comment changed
                kind = _handler_kind(hunk, line)
                if kind in ("explained", "narrow"):
                    findings.append(
                        _finding(
                            f"failures.swallowed_{kind}",
                            Severity.INFO,
                            f"empty handler ({kind})",
                            change,
                            line,
                        )
                    )
                elif kind == "silent":
                    severity = Severity.HIGH if change.is_test else Severity.MEDIUM
                    findings.append(
                        _finding(
                            "failures.swallowed",
                            severity,
                            "failure silently swallowed",
                            change,
                            line,
                        )
                    )
    return findings


def stub_regressed(changes: Changes) -> list[Finding]:
    """Real logic replaced by a hardcoded value while the signature stayed put.

    A brand-new `raise NotImplementedError` is deliberately not flagged: it is loud
    and fails fast, and punishing it pushes agents toward silent hardcoded returns.
    """
    findings: list[Finding] = []
    for change in changes.source_files:
        for hunk in change.hunks:
            gutted = any(_is_substantive(ln) for ln in hunk.removed)
            adds_work = any(_is_substantive(ln) for ln in hunk.added)
            if not gutted or adds_work:
                continue  # new logic alongside a `return None` is control flow
            findings.extend(
                _finding(
                    "stub.regressed", Severity.HIGH, "logic replaced by a trivial value", change, ln
                )
                for ln in hunk.added
                if _is_trivial(ln)
            )
    return findings


def test_file_deleted(changes: Changes) -> list[Finding]:
    """A whole test file removed, rather than moved."""
    relocated = changes.relocated()
    severity = _removal_severity(changes)
    findings: list[Finding] = []
    for change in changes.test_files:
        if not change.is_deleted:
            continue
        body = [ln.stripped for ln in change.removed if ln.stripped]
        moved = sum(1 for text in body if text in relocated)
        if body and moved / len(body) > p.RELOCATION_RATIO:
            continue
        anchor = change.removed[0] if change.removed else Line("", "-", 1, None)
        message = f"test file deleted ({len(body)} lines)"
        findings.append(_finding("tests.file_deleted", severity, message, change, anchor))
    return findings


DETECTORS = (
    assertions_removed,
    tests_disabled,
    failures_swallowed,
    stub_regressed,
    test_file_deleted,
)


def run_all(changes: Changes) -> list[Finding]:
    """Run every detector and return findings, most severe first."""
    findings = [finding for detector in DETECTORS for finding in detector(changes)]
    return sorted(findings, key=lambda f: (-f.severity, f.path, f.line))
