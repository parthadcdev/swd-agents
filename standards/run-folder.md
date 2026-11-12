# Run folder format

Every run has a folder at `.swd/runs/<YYYY-MM-DD>-<short-name>/` in the
project being worked on. It is the team's shared memory. An agent knows only
what is in its brief and in this folder.

These formats are checked by `scripts/check_run.py`. Follow them exactly.

## Who writes what

| File | Written by | Holds |
|---|---|---|
| `requirement.md` | Principal | The requirement verbatim, plus the user's answers to clarifying questions |
| `spec.md` | Principal | What will be built, acceptance criteria, assumptions, delivery mode and why |
| `standards.md` | Principal | The engineering bar for this run, followed by this document |
| `plan.md` | Architect | Design, contracts, test command, task list in waves |
| `ledger.md` | Principal only | One row per task: status, role, attempt count |
| `activity.md` | Principal only | A timeline of the run, one line per event |
| `decisions.md` | Principal | Every ruling and assumption made after the gate |
| `reports/*.md` | The agent that did the work | One report per piece of work |

An agent writes only its owned files and its own report.

## spec.md

Must contain a mode line and an acceptance criteria section:

```markdown
# Spec: cart total

Mode: production

Why this mode: the repo is an existing library with users.

## What will be built
A `total()` function in `shop/cart.py`.

## Acceptance criteria
- `total([(100, 2)])` returns `200`.
- A 10% discount on 200 returns `180`.

## Assumptions
- Tax is applied after the discount.
```

The mode line is exactly `Mode: prototype` or `Mode: production`.

## plan.md

Must contain a test command line and at least one task:

```markdown
# Plan: cart total

Test command: `python3 -m unittest`

## Design
`total()` composes `subtotal()` and `apply_discount()`.

## Contracts
`total(items, discount_percent=0, tax_percent=0) -> float`, rounded to 2 decimals.

## Tasks

### T1: Add total() to cart
- Role: generalist-engineer
- Wave: 1
- Files: shop/cart.py, tests/test_cart.py
- Depends: none
- Check: `python3 -m unittest tests.test_cart`
```

Rules for tasks:

- The heading is `### T<n>: <title>`. Ids are unique.
- All five fields are required, written exactly as `- Role:`, `- Wave:`,
  `- Files:`, `- Depends:`, `- Check:`.
- `Role` is a builder: `generalist-engineer`, `backend-engineer`,
  `frontend-engineer`, `database-engineer`, `devops-engineer` or
  `docs-writer`.
- `Wave` is a number. Wave 1 runs first.
- `Files` is a comma-separated list of every file the task may create or
  change, tests included. No file appears in two tasks of the same wave.
- `Depends` is `none` or a comma-separated list of task ids, each in an
  earlier wave.
- `Check` is the command that proves the task is done.

## ledger.md

```markdown
| Task | Role | Status | Attempts |
|---|---|---|---|
| T1 | generalist-engineer | done | 1 |
| T2 | backend-engineer | in-review | 2 |
```

Status is one of `todo`, `in-progress`, `in-review`, `done`, `blocked`.
`Attempts` counts dispatches of the task, starting at 1 for the first.

## activity.md

One line per event, oldest first:

```markdown
- 10:00:00 dispatch T1 generalist-engineer (sonnet)
- 10:04:12 return T1 report written
- 10:04:30 dispatch T1 code-reviewer
- 10:06:02 verdict T1 code-reviewer pass
- 10:06:10 commit T1
- 10:06:15 wave-done 1
- 10:09:40 done all tasks complete
```

The form is `- <HH:MM:SS> <event> <detail>`. Events: `dispatch`, `return`,
`verdict`, `commit`, `fix`, `replan`, `ruling`, `wave-done`, `blocked`,
`done`. Every task has at least one `dispatch` line naming its id. The last
line of a finished run is a `done` event.

## decisions.md

A list. Each entry says what was decided, why, and what it costs if wrong.

## Builder reports

File: `reports/T<n>-<role>.md`, for example `reports/T1-generalist-engineer.md`.
All six headings are required. The two test sections must contain the real
command and its real output.

```markdown
## Summary
Added total() and fixed apply_discount().

## Files changed
- shop/cart.py
- tests/test_cart.py

## Test first (failing)
$ python3 -m unittest tests.test_cart
AttributeError: module 'shop.cart' has no attribute 'total'
FAILED (errors=4)

## Test after (passing)
$ python3 -m unittest tests.test_cart
Ran 6 tests in 0.001s
OK

## Complexity
total() is O(n) time in the number of items, O(1) extra space.

## Concerns
None.
```

A fix for a task overwrites the same report with the new evidence.

## Checker reports

A checker report has a verdict line and a findings section:

```markdown
Verdict: fail

## Findings
- shop/cart.py:14 — apply_discount subtracts the percent as an amount. Multiply by (1 - percent / 100).
```

The verdict line is exactly `Verdict: pass` or `Verdict: fail`.

| Report | File |
|---|---|
| Code review of one task | `reports/T<n>-code-reviewer.md` |
| Security review of one task | `reports/T<n>-security-reviewer.md` |
| Code review of the whole change | `reports/final-code-reviewer.md` |
| Security review of the whole change | `reports/final-security-reviewer.md` |
| QA of a finished wave | `reports/wave-<n>-qa-engineer.md` |
| Final QA | `reports/final-qa-engineer.md` |

## Commits

- A task commit has the subject `T<n>: <title>` and changes only that task's
  files.
- A prototype-mode wave commit has the subject `W<n>: <summary>` and changes
  only files owned by tasks in that wave.
- Files under `.swd/` may be included in any commit.
