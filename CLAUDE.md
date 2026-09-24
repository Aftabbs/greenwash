# Notes for coding agents working on greenwash

Read CONTRIBUTING.md first. It has the setup, layout and design constraints.

- This project exists because agents report work they did not verify. Run
  `python -m pytest` and `python -m ruff check .` before saying a change works.
- Every false positive or missed case you fix gets a regression test in
  `tests/test_corpus.py` in the same change.
- Before changing a detector, run `scripts/replay.py` against a real repository
  and confirm the flag rate does not rise.
- Never weaken or skip a test here to make the suite pass. greenwash would flag it.

Traps that have already caused bugs:

- With `git diff --unified=0`, added lines from different hunks sit next to each
  other in a flat list. Anything that looks at "the next line" must stay inside
  one hunk and check line numbers.
- Inside a hunk, trust the `@@` counts rather than line prefixes: a removed
  `-- comment` line appears as `--- comment`.
- Moves, splits, reverts and parametrize rewrites all remove assertion lines
  legitimately.
- A blocking Stop hook can trap the agent in a loop. Keep the per-session memory of
  what was already reported, and never block when `stop_hook_active` is set.
