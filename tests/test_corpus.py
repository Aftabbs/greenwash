"""Behavioural corpus: realistic cheats that must be caught, and innocent changes
that must not be flagged.

Every false positive or missed detection found in real history becomes a case
here, in the same change as the fix. The negative cases matter more than the
positive ones: a noisy tool gets uninstalled.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from greenwash.core.claim import Claim
from greenwash.core.detectors import run_all
from greenwash.core.sources import from_range

from .helpers import git as _git
from .helpers import init_repo

BASELINE_SRC = """\
def apply_discount(price, percent):
    if percent < 0 or percent > 100:
        raise ValueError("percent out of range")
    return round(price * (1 - percent / 100), 2)


def total_with_tax(price, tax_rate):
    return round(price * (1 + tax_rate), 2)
"""

BASELINE_TEST = """\
from billing import apply_discount, total_with_tax


def test_apply_discount_basic():
    assert apply_discount(100, 10) == 90.0


def test_apply_discount_rejects_bad_percent():
    try:
        apply_discount(100, 150)
        assert False, "should have raised"
    except ValueError:
        pass


def test_total_with_tax():
    assert total_with_tax(100, 0.2) == 120.0
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return init_repo(
        tmp_path / "repo", {"billing.py": BASELINE_SRC, "tests/test_billing.py": BASELINE_TEST}
    )


def audit(repo: Path, mutate: Callable[[Path], None], claim_text: str):
    mutate(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", claim_text)
    changes = from_range(repo, "HEAD~1..HEAD", Claim(claim_text, "commit-message"))
    return run_all(changes)


def actionable(findings):
    return [f for f in findings if f.severity.actionable]


# --------------------------------------------------------------------------
# Cheats that must be caught
# --------------------------------------------------------------------------


def test_catches_deleted_assertion(repo):
    def mutate(r: Path) -> None:
        p = r / "tests" / "test_billing.py"
        p.write_text(
            p.read_text(encoding="utf-8").replace(
                "    assert total_with_tax(100, 0.2) == 120.0\n", "    pass\n"
            ),
            encoding="utf-8",
        )

    findings = audit(repo, mutate, "Fix billing rounding. All tests passing.")
    hits = [f for f in actionable(findings) if f.rule_id == "assertions.removed"]
    assert hits, [f.rule_id for f in findings]
    assert hits[0].path == "tests/test_billing.py"
    assert hits[0].line > 0
    assert "total_with_tax" in hits[0].line_text


def test_catches_skip_marker(repo):
    def mutate(r: Path) -> None:
        p = r / "tests" / "test_billing.py"
        text = p.read_text(encoding="utf-8").replace(
            "def test_total_with_tax():",
            "@pytest.mark.skip(reason='flaky')\ndef test_total_with_tax():",
        )
        p.write_text("import pytest\n" + text, encoding="utf-8")

    findings = audit(repo, mutate, "Resolve tax calculation issue. Suite is green.")
    assert any(f.rule_id == "tests.disabled" for f in actionable(findings))


def test_catches_swallowed_assertion(repo):
    def mutate(r: Path) -> None:
        p = r / "tests" / "test_billing.py"
        p.write_text(
            p.read_text(encoding="utf-8").replace(
                "    assert apply_discount(100, 10) == 90.0",
                "    try:\n        assert apply_discount(100, 10) == 90.0\n"
                "    except Exception:\n        pass",
            ),
            encoding="utf-8",
        )

    findings = audit(repo, mutate, "Harden tests. Everything verified.")
    assert any(f.rule_id == "failures.swallowed" for f in actionable(findings))


def test_catches_deleted_test_file(repo):
    def mutate(r: Path) -> None:
        (r / "tests" / "test_billing.py").unlink()

    findings = audit(repo, mutate, "Fix billing. Verified working.")
    assert any(f.rule_id == "tests.file_deleted" for f in actionable(findings))


def test_catches_body_regressed_to_hardcoded_return(repo):
    """The silent failure the old stub detector missed entirely."""

    def mutate(r: Path) -> None:
        p = r / "billing.py"
        p.write_text(
            p.read_text(encoding="utf-8").replace(
                "def total_with_tax(price, tax_rate):\n"
                "    return round(price * (1 + tax_rate), 2)\n",
                "def total_with_tax(price, tax_rate):\n    return 0\n",
            ),
            encoding="utf-8",
        )

    findings = audit(repo, mutate, "Simplify tax handling. Tested and working.")
    assert any(f.rule_id == "stub.regressed" for f in actionable(findings))


# --------------------------------------------------------------------------
# Innocent changes that must stay quiet — these matter more
# --------------------------------------------------------------------------


def test_quiet_on_genuine_feature_with_tests(repo):
    def mutate(r: Path) -> None:
        src = r / "billing.py"
        src.write_text(
            src.read_text(encoding="utf-8")
            + "\n\ndef to_paise(rupees):\n    return int(round(rupees * 100))\n",
            encoding="utf-8",
        )
        tst = r / "tests" / "test_billing.py"
        tst.write_text(
            tst.read_text(encoding="utf-8")
            + "\n\ndef test_to_paise():\n    assert to_paise(12.34) == 1234\n",
            encoding="utf-8",
        )

    assert actionable(audit(repo, mutate, "Add currency conversion helper with tests")) == []


def test_quiet_on_honest_removal(repo):
    def mutate(r: Path) -> None:
        tst = r / "tests" / "test_billing.py"
        tst.write_text(
            tst.read_text(encoding="utf-8").replace(
                "def test_total_with_tax():\n    assert total_with_tax(100, 0.2) == 120.0\n",
                "",
            ),
            encoding="utf-8",
        )
        src = r / "billing.py"
        src.write_text(
            src.read_text(encoding="utf-8").replace(
                "def total_with_tax(price, tax_rate):\n"
                "    return round(price * (1 + tax_rate), 2)\n",
                "",
            ),
            encoding="utf-8",
        )

    findings = audit(repo, mutate, "Remove obsolete tax test, the API it covered was deleted")
    assert actionable(findings) == []


def test_quiet_on_docs_only(repo):
    def mutate(r: Path) -> None:
        (r / "README.md").write_text("# Billing\n\nUsage.\n", encoding="utf-8")

    assert actionable(audit(repo, mutate, "Update README with usage examples")) == []


def test_quiet_on_refactor(repo):
    def mutate(r: Path) -> None:
        p = r / "billing.py"
        text = p.read_text(encoding="utf-8")
        text = text.replace(
            "round(price * (1 - percent / 100), 2)",
            "_round2(price * (1 - percent / 100))",
        ).replace(
            "round(price * (1 + tax_rate), 2)",
            "_round2(price * (1 + tax_rate))",
        )
        text = "def _round2(v):\n    return round(v, 2)\n\n\n" + text
        p.write_text(text, encoding="utf-8")

    assert actionable(audit(repo, mutate, "Extract rounding helper for reuse")) == []


def test_quiet_on_conditional_skip(repo):
    """Platform-gated skips are ordinary compatibility work, not cheating.

    Regression: an early version flagged pydantic's `skipif(platform == 'GraalVM')`.
    """

    def mutate(r: Path) -> None:
        p = r / "tests" / "test_billing.py"
        text = p.read_text(encoding="utf-8").replace(
            "def test_total_with_tax():",
            "@pytest.mark.skipif(sys.version_info >= (3, 15), reason='unsupported')\n"
            "def test_total_with_tax():",
        )
        p.write_text("import sys\nimport pytest\n" + text, encoding="utf-8")

    findings = audit(repo, mutate, "Add Python 3.15 compatibility guard")
    assert actionable(findings) == [], [f.rule_id for f in findings]


def test_quiet_on_commented_empty_handler(repo):
    """An explained empty handler is deliberate control flow.

    Regression: an early version flagged a documented `} catch {` in real code.
    """

    def mutate(r: Path) -> None:
        p = r / "billing.py"
        p.write_text(
            p.read_text(encoding="utf-8") + "\n\ndef parse(v):\n    try:\n        return int(v)\n"
            "    except ValueError:\n        # not a number, caller handles the default\n"
            "        pass\n",
            encoding="utf-8",
        )

    findings = audit(repo, mutate, "Tolerate non-numeric input")
    assert actionable(findings) == [], [f.rule_id for f in findings]


def test_quiet_on_unknown_language(repo):
    """Fail open: a language we do not model must produce nothing at all."""

    def mutate(r: Path) -> None:
        (r / "main.zig").write_text("fn main() void {\n    // pass\n}\n", encoding="utf-8")

    assert audit(repo, mutate, "Add zig entry point. Verified working.") == []


def test_quiet_on_new_helper_returning_none(repo):
    """`return None` inside freshly added logic is control flow, not a gutted body.

    Regression: flagged pydantic 9b4d952c, where a new nested `_resolve_ref`
    helper legitimately returns None on a failed lookup.
    """

    def mutate(r: Path) -> None:
        p = r / "billing.py"
        p.write_text(
            p.read_text(encoding="utf-8").replace(
                "def total_with_tax(price, tax_rate):\n"
                "    return round(price * (1 + tax_rate), 2)\n",
                "def total_with_tax(price, tax_rate, table=None):\n"
                "    def _lookup(rate):\n"
                "        if table is not None:\n"
                "            return table.get(rate)\n"
                "        return None\n"
                "    resolved = _lookup(tax_rate)\n"
                "    if resolved is None:\n"
                "        resolved = tax_rate\n"
                "    return round(price * (1 + resolved), 2)\n",
            ),
            encoding="utf-8",
        )

    findings = audit(repo, mutate, "Support tax rate lookup tables")
    assert actionable(findings) == [], [f.rule_id for f in findings]


def test_large_test_split_is_summarised_not_enumerated(repo):
    """A wholesale reorganisation yields one finding, not one per assertion.

    Regression: pydantic 69fd688e (a 6946-line test split) produced 50+ findings.
    """

    def mutate(r: Path) -> None:
        extra = "\n".join(
            f"def test_generated_{i}():\n    assert apply_discount(100, {i}) is not None\n"
            for i in range(12)
        )
        p = r / "tests" / "test_billing.py"
        p.write_text(p.read_text(encoding="utf-8") + "\n" + extra, encoding="utf-8")

    _git(repo, "add", "-A")
    mutate(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "Add generated cases")

    def remove_them(r: Path) -> None:
        p = r / "tests" / "test_billing.py"
        text = p.read_text(encoding="utf-8")
        p.write_text(text[: text.index("def test_generated_0")], encoding="utf-8")

    findings = audit(repo, remove_them, "Drop the generated cases entirely")
    assertion_findings = [f for f in findings if f.rule_id == "assertions.removed"]
    assert len(assertion_findings) <= 1, len(assertion_findings)


def test_quiet_on_revert(repo):
    """A revert removes the test it added; that is the whole point of a revert.

    Regression: pydantic 800f2f90, a revert of "Add regression test: ...".
    """

    def mutate(r: Path) -> None:
        p = r / "tests" / "test_billing.py"
        p.write_text(
            p.read_text(encoding="utf-8").replace(
                "def test_total_with_tax():\n    assert total_with_tax(100, 0.2) == 120.0\n",
                "",
            ),
            encoding="utf-8",
        )

    findings = audit(repo, mutate, 'Revert "Add regression test for tax handling"')
    assert actionable(findings) == [], [f.rule_id for f in findings]


def test_quiet_on_skip_marker_inside_a_string(repo):
    """Text that merely mentions a skip marker is data, not a disabled test.

    Regression: greenwash flagged its own fixtures, which embed skip decorators
    in string literals.
    """

    def mutate(r: Path) -> None:
        p = r / "tests" / "test_billing.py"
        p.write_text(
            p.read_text(encoding="utf-8")
            + "\n\nFIXTURE = \"@pytest.mark.skip(reason='flaky')\"\n"
            + "\n\ndef test_fixture_text():\n    assert 'skip' in FIXTURE\n",
            encoding="utf-8",
        )

    findings = audit(repo, mutate, "Add fixture text for the parser")
    assert actionable(findings) == [], [f.rule_id for f in findings]


def test_quiet_on_expected_exception_idiom(repo):
    """`try: call(); assert False` / `except ValueError: pass` asserts a raise.

    Regression: flagged as a swallowed failure. Catching one specific, expected
    error is deliberate; only handlers broad enough to eat an assertion count.
    """

    def mutate(r: Path) -> None:
        p = r / "tests" / "test_billing.py"
        p.write_text(
            p.read_text(encoding="utf-8") + "\n\ndef test_rejects_negative_tax():\n"
            "    try:\n        total_with_tax(100, -1)\n        assert False\n"
            "    except ValueError:\n        pass\n",
            encoding="utf-8",
        )

    assert actionable(audit(repo, mutate, "Cover negative tax rates")) == []


def test_catches_assertion_error_being_swallowed(repo):
    """Catching AssertionError is the most direct way to silence a test."""

    def mutate(r: Path) -> None:
        p = r / "tests" / "test_billing.py"
        p.write_text(
            p.read_text(encoding="utf-8").replace(
                "    assert apply_discount(100, 10) == 90.0",
                "    try:\n        assert apply_discount(100, 10) == 90.0\n"
                "    except AssertionError:\n        pass",
            ),
            encoding="utf-8",
        )

    findings = audit(repo, mutate, "Stabilise flaky discount test")
    assert any(f.rule_id == "failures.swallowed" for f in actionable(findings))


def test_quiet_on_version_gated_skip_call(repo):
    """`pytest.skip()` inside `if sys.version_info < ...` is conditional.

    Regression: pydantic af0e0a6a, a new module that only runs on Python 3.15+.
    """

    def mutate(r: Path) -> None:
        (r / "tests" / "test_frozen.py").write_text(
            "import sys\n\nimport pytest\n\n"
            "if sys.version_info < (3, 15):\n"
            "    pytest.skip('needs frozendict', allow_module_level=True)\n\n\n"
            "def test_frozen():\n    assert True\n",
            encoding="utf-8",
        )

    findings = audit(repo, mutate, "Add frozendict support")
    assert actionable(findings) == [], [f.rule_id for f in findings]


def test_catches_unguarded_skip_call(repo):
    """A bare `pytest.skip()` at the top of a test disables it for everyone."""

    def mutate(r: Path) -> None:
        p = r / "tests" / "test_billing.py"
        text = p.read_text(encoding="utf-8").replace(
            "def test_total_with_tax():\n",
            "def test_total_with_tax():\n    pytest.skip('flaky')\n",
        )
        p.write_text("import pytest\n" + text, encoding="utf-8")

    findings = audit(repo, mutate, "Fix tax rounding. All green.")
    assert any(f.rule_id == "tests.disabled" for f in actionable(findings))


def test_quiet_on_assertions_folded_into_parametrize(repo):
    """Many asserts rewritten as one parametrized test keep every check.

    Regression: pydantic c5af6028.
    """

    def mutate(r: Path) -> None:
        extra = "".join(
            f"\n\ndef test_discount_{n}():\n    assert apply_discount(100, {n}) == {100 - n}.0\n"
            for n in (10, 20, 30, 40)
        )
        p = r / "tests" / "test_billing.py"
        p.write_text(p.read_text(encoding="utf-8") + extra, encoding="utf-8")
        _git(r, "add", "-A")
        _git(r, "commit", "-q", "-m", "explicit cases")
        p.write_text(
            p.read_text(encoding="utf-8").split("\n\ndef test_discount_10")[0]
            + "\n\n@pytest.mark.parametrize('n', [10, 20, 30, 40])\n"
            "def test_discount(n):\n    assert apply_discount(100, n) == 100 - n\n",
            encoding="utf-8",
        )

    findings = audit(repo, mutate, "Parametrize discount cases")
    assert actionable(findings) == [], [f.rule_id for f in findings]
