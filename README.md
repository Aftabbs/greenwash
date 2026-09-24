# greenwash

Catches coding agents that weaken your tests and then report success.

Your agent says *"Done, all tests pass."* Sometimes it deleted the failing
assertion, skipped the test, wrapped it in `try/except: pass`, or replaced the
function body with `return 0`. greenwash reads the diff and tells you, and tells
the agent, the moment it tries to stop.

```text
greenwash: the uncommitted changes weaken the test suite. Restore the checks
below, or tell the user plainly why each change is intentional.

tests/test_billing.py:47  assertion removed
    assert total_with_tax(100, 0.2) == 120.0
```

It is deterministic: no model, no network, no API key. It reads `git diff` and
nothing else.

## Install

Requires Python 3.10+ and git.

```bash
pipx install git+https://github.com/Aftabbs/greenwash
```

Then, in the project you use Claude Code in:

```bash
greenwash install
```

This adds a Stop hook to `.claude/settings.local.json`. When the agent finishes a
turn, greenwash checks the uncommitted work. If a test was weakened, the agent is
kept going and shown the report, so it can fix the problem before you look.

### As a Claude Code plugin

No Python install step needed; the plugin runs greenwash from its own checkout.

```text
/plugin marketplace add Aftabbs/greenwash
/plugin install greenwash@greenwash
```

The plugin also ships a `greenwash` skill that tells the agent how to respond to a
finding: restore the check, or say plainly why it changed.

## Usage

```bash
greenwash                    # check uncommitted work (staged, unstaged, untracked)
greenwash HEAD~1..HEAD       # check a commit range
greenwash --verbose          # include informational notes and rule ids
greenwash install --protect  # also block agent edits to test files
greenwash install --uninstall
```

`greenwash` prints nothing when there is nothing to report. By default it exits 0
either way; pass `--fail-on high` if you want a non-zero exit.

## What it catches

| Rule | What happened |
|---|---|
| `assertions.removed` | Assertions deleted from a test and not moved anywhere else in the change |
| `tests.disabled` | `@pytest.mark.skip`, `it.skip`, `xit`, `.only()`, or an unguarded `pytest.skip()` |
| `failures.swallowed` | A new `except:` / `except Exception:` / `catch {}` that does nothing |
| `stub.regressed` | Real logic replaced by `pass` or a hardcoded return value |
| `tests.file_deleted` | A test file removed rather than moved |

Python and JavaScript/TypeScript test conventions are recognised. Files in other
languages produce no findings.

It deliberately stays quiet about things that look similar but are fine:

- skips gated on a Python version or platform (`skipif`, `pytest.skip` inside an `if`)
- tests moved, split, consolidated into `@pytest.mark.parametrize`, or reverted
- narrow handlers such as `except KeyError: pass`, and empty handlers with a comment
- `return None` inside logic that was added in the same change
- a new `raise NotImplementedError`, which fails loudly rather than silently

## Blocking edits to tests

```bash
greenwash install --protect                 # default test globs
greenwash install --protect 'tests/**'      # your own globs
```

This adds a PreToolUse hook that refuses the agent's `Edit` and `Write` calls on
protected paths. It prevents the problem instead of reporting it afterwards. It is
off by default because it also blocks legitimate test changes, and it only covers
the file-editing tools: an agent can still change a file through the shell.

## Why no LLM

A model asked to judge whether an agent really finished tends to trust confident
wording. In [a study of 11,000+ agent trajectories](https://arxiv.org/abs/2606.09863),
no configuration of five LLM judges and five prompting strategies exceeded an
AUROC of 0.65 at detecting false success. The same study found false success fell
from 44–52% of failures to 3% when an independent check could inspect the actual
state.

greenwash is that independent check, kept narrow on purpose. A diff either
removed an assertion or it did not.

## Accuracy

Checked against the recent history of two projects, where commits are human
written and overwhelmingly honest:

| Repository | Commits | Commits flagged |
|---|---|---|
| pydantic | 145 | 1 (0.7%) |
| psf/requests | 55 | 0 |

The flagged pydantic commit removes an assertion during an optimisation, which is
worth a reviewer's look. Every earlier false positive found this way is now a test
case in `tests/test_corpus.py`, and `scripts/replay.py` reruns the measurement.

## Limitations

- **A clean result is not a guarantee.** greenwash sees the shape of the diff, not
  whether the code is right. An agent can still weaken a test in ways it does not
  recognise, for example by changing `== 42` to `is not None`, or by never writing
  a meaningful test at all.
- It has not yet been measured on a labelled set of real agent sessions, so its
  recall is unknown. The numbers above show it is rarely wrong when it speaks, not
  how much it misses.
- When checking a commit range, a commit message that admits removing tests
  ("remove obsolete test") lowers the severity. Hook mode has no commit message and
  is unaffected.
- Only Claude Code hooks are provided so far. `greenwash check` works anywhere.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version: every false positive or
missed case you report becomes a test in the corpus, in the same change as the fix.

## License

[Apache-2.0](LICENSE)
