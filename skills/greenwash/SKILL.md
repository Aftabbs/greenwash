---
name: greenwash
description: Use before telling the user that code or tests are done, fixed or passing, and whenever greenwash reports a finding. Checks uncommitted changes for weakened tests - removed assertions, skipped tests, swallowed failures, logic replaced by a hardcoded value.
---

# Show the work is real before calling it done

Before you tell the user the work is done, fixed or passing, run:

```bash
greenwash check
```

If `greenwash` is not on the PATH, run `python -m greenwash check` instead.

No output means none of these shortcuts appear in the uncommitted changes. Any
output is a list of findings, each with a file, a line number and the line itself.

## When greenwash reports a finding

Every finding means a check got weaker. For each one, do one of these:

1. **Restore it.** Put the assertion back, remove the skip, stop swallowing the
   exception, bring back the logic. Then fix the real problem.
2. **Say so.** Tell the user plainly which test you changed and why, before you
   describe the work as finished.

Do not make a finding disappear by:

- rewriting the test to assert something weaker,
- moving the assertion somewhere it will not run,
- adding a comment or suppression whose only purpose is to silence greenwash.

## What a clean result means

A clean result is not proof the code is correct. It only means none of these
particular shortcuts appear in the diff. Run the test suite as well.
