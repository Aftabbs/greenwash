"""Plain-text report: the location, what happened, and the line itself.

Nothing is printed when there is nothing to report.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.model import Finding

DEFAULT_MAX_FINDINGS = 10


def render(
    findings: Sequence[Finding], *, max_findings: int = DEFAULT_MAX_FINDINGS, verbose: bool = False
) -> str:
    if not findings:
        return ""

    shown = findings[:max_findings]
    blocks = []
    for finding in shown:
        head = f"{finding.path}:{finding.line}  {finding.message}"
        if verbose:
            head += f"  [{finding.rule_id} {finding.severity.name.lower()}]"
        body = finding.line_text.strip()
        blocks.append(f"{head}\n    {body}" if body else head)

    hidden = len(findings) - len(shown)
    if hidden > 0:
        blocks.append(f"... and {hidden} more")
    return "\n\n".join(blocks)
