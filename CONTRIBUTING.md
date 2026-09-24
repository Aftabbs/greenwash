# Contributing

## Setup

```bash
git clone https://github.com/Aftabbs/greenwash
cd greenwash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check . && python -m ruff format --check .
```

## The rule that matters

**Every false positive and every missed case becomes a test.** Add it to
`tests/test_corpus.py` in the same change as the fix, with a docstring naming where
it was found. The corpus is how the tool remembers what it got wrong.

Cases that must stay quiet matter more than cases that must be caught. A noisy
checker gets uninstalled, and then it catches nothing.

## Reporting a false positive

Open an issue with the diff, or the repository and commit hash, and the line that
was flagged. That is usually enough to write the regression test.

## Where things live

| Path | What it does |
|---|---|
| `src/greenwash/core/diff.py` | Parses `git diff` output, keeping line numbers per hunk |
| `src/greenwash/core/sources.py` | Collects changes from a commit range or the working tree |
| `src/greenwash/core/patterns.py` | Pattern banks and thresholds |
| `src/greenwash/core/detectors.py` | One function per kind of weakened test |
| `src/greenwash/integrations/` | Claude Code hooks and `greenwash install` |
| `hooks/`, `skills/`, `.claude-plugin/` | The Claude Code plugin |
| `scripts/replay.py` | Measures how often greenwash speaks up on a repo's history |

Most contributions add or tighten a pattern in `patterns.py` and add corpus cases.

## Measuring false positives

```bash
git clone --depth 150 https://github.com/pydantic/pydantic /tmp/pydantic
python scripts/replay.py /tmp/pydantic 145
```

Run this before and after changing a detector. The flag rate should not go up.

## Design constraints

- **No model calls in the checks.** A checker that reasons like the agent can be
  fooled like the agent.
- **Advisory by default.** Nothing fails a build unless the user asks for it with
  `--fail-on`.
- **Fail open.** Bad input, a missing repository or a git error means saying
  nothing, never blocking the agent.
- **Unknown languages produce no findings.**
