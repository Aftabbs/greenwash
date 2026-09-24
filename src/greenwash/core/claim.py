"""What a change says about itself, such as a commit message."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ClaimSource = Literal["none", "cli", "commit-message"]


@dataclass(frozen=True, slots=True)
class Claim:
    """The stated intent of a change.

    Only ever used to *lower* severity when a change openly admits removing tests.
    It is never trusted as evidence: the agent that wrote the diff usually wrote
    the commit message too.
    """

    text: str = ""
    source: ClaimSource = "none"


NO_CLAIM = Claim()
