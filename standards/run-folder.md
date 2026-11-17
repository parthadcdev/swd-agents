# Run folder format

Every run has a folder at `.swd/runs/<YYYY-MM-DD>-<short-name>/` in the
project being worked on. It is the team's shared memory. An agent knows only
what is in its brief and in this folder.

These formats are checked by `scripts/check_run.py`. Follow them exactly.
A finished run must also have every change committed, and every checker
report in `reports/` must say `Verdict: pass`.

## Who writes what

| File | Written by | Holds |
|---|---|---|
| `requirement.md` | Principal | The requirement verbatim, plus the user's answers to clarifying questions |
| `spec.md` | Principal | What will be built, acceptance criteria, assumptions, delivery mode and why |
| `standards.md` | Principal | The engineering bar for this run, the model guidance, then this document |
| `plan.md` | Architect | Outcome, design, contracts, test command, task list in waves |
| `staffing.md` | Principal | The agent, model and effort for each task, for the reviews and for the final check |
| `ledger.md` | Principal only | One row per task: status, role, attempt count |
| `activity.md` | Principal only | A timeline of the run, one line per event |
| `decisions.md` | Principal | Every ruling and assumption made after the gate |
| `dashboard.html` | `swd-dashboard.py`, started by the principal | The live view of the run; never edited by hand |
| `reports/*.md` | The agent that did the work | One report per piece of work |
| `evidence/*.txt` | `swd-test.py` only | What each recorded test run printed and how it exited. Never written by hand |

An agent writes only its owned files and its own report.

Two files outlive runs and sit beside the `runs/` folder, in `.swd/`:

| File | Written by | Holds |
|---|---|---|
| `project.md` | Architect | The project notes: test, lint and build commands, layout, conventions. Your brief names its path on the `Project notes:` line. Read it before you start |
| `findings.md` | `swd-findings.py`, run by the principal | The backlog of defects the team has seen and not fixed |

## Where to work

The run's code lives in a worktree of its own, not in the user's working
copy. Your brief names it on the `Work in:` line, and you start in it: your
shell's working directory is already the worktree. Run `pwd` once to
confirm; if it prints anything else, stop and say so in your report.

Run commands plainly from there, without `cd`: one plain command per call,
with no shell variables, no `;` or `&&` chains, and no pipes where you can
avoid them. Plain commands are the least likely to be held for approval.
Read files with the Read tool, not with `cat`. With the file tools, use
paths under the worktree. File paths in `plan.md` and in reports are
relative to it.

If a command is refused, that is usually about the form of that one command,
not about your access to the shell. Run it again as one plain command, or
split it into several. Report a permission problem as a blocker only when
one plain command, such as `pwd` or the task's check command on its own, is
refused too, and quote the exact command and the refusal in your report.

The run folder is somewhere else, at the path your brief gives on the
`Run folder:` line. Never change anything in the project outside the
worktree.

Files you need only for your own checking (sample inputs, captured output,
throwaway scripts) are not part of the project. Put them in `scratch/`
inside the run folder, never in the worktree and never in the user's
working copy.

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

## Outcome
$ python3 -c "from shop.cart import total; print(total([(100, 2)], discount_percent=10))"
180.0

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
- Outcome: `total([(100, 2)], discount_percent=10)` returns `180.0`
```

The `## Outcome` section is required. It shows the finished result as it
will really appear: the command and what it prints, the screen, or the text
of the file. It does not describe the result. Quoted text that contains
headings or task fields is indented four spaces, because the checker does
not know code fences.

`check_run.py --plan` and `--seal` require `## Outcome` and every
task's `- Outcome:`. The check of a finished run does not, for a run that
has a `Plan checksum:` line, so a run that was sealed before these existed
still checks clean; a run never sealed is held to them. When a sealed run's
plan is amended, the amendment adds them, because the plan is sealed again.

Rules for tasks:

- The heading is `### T<n>: <title>`. Ids are unique.
- All six fields are required, written exactly as `- Role:`, `- Wave:`,
  `- Files:`, `- Depends:`, `- Check:`, `- Outcome:`.
- `Role` is a builder: `generalist-engineer`, `backend-engineer`,
  `frontend-engineer`, `database-engineer`, `devops-engineer` or
  `docs-writer`.
- `Wave` is a number. Wave 1 runs first.
- `Files` is a comma-separated list of every file the task may create or
  change, tests included. No file appears in two tasks of the same wave.
- `Depends` is `none` or a comma-separated list of task ids, each in an
  earlier wave.
- `Check` is the command that proves the task is done.
- `Outcome` is one line saying what observably exists or happens once the
  task is done.

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
- 10:00:00 dispatch T1 generalist-engineer (opus medium)
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

It starts with five lines the principal writes in preflight:
`Base commit: <sha>`, `Base branch: <name>`, `Branch: swd/<short-name>`,
`Worktree: <path>` and `Conductor: Fable 5.2` or `Conductor: Opus 5.5`,
the model the principal conducts on. Whenever the last `Conductor:` line
does not name the model the principal is on, it appends a new one.
`check_run.py --plan` and `--seal` read only the last, and report a run
without one:

    decisions.md: needs a line 'Conductor: Fable 5.2' or 'Conductor: Opus 5.5'; the principal records the model it conducts on

The check of a finished run does not ask for it, so a run from before
0.10.0, which has none, still checks clean. Preflight housekeeping adds `Housekeeping: removed <n>,
kept <m>`. At the gate it gains `Finish: merge-push`, `Finish: pr`
or `Finish: branch`. Below those, a list: each entry says what was decided,
why, and what it costs if wrong.

Before the seal the principal adds one line, `Plan judged: <one sentence>`,
saying the plan was judged against the spec.
Each time the plan is amended and sealed again, the principal adds a
new `Plan judged:` line below the last `Plan checksum:` line;
`check_run.py --seal` refuses to seal without it. A change to `staffing.md`
alone is sealed again without a new `Plan judged:` line.

A principal that is not on Fable 5.2 asks the Fable judge first (the build
playbook's **The Fable judge.**) and records what came back in these lines:

    Judge plan: <the verdict sentence> (reports/judge-<n>.md)
    Judge ruling: <the verdict sentence> (reports/judge-<n>.md)
    Judge overruled: reports/judge-<n>.md, because <why>
    Judge unreachable: <what the dispatch returned, in one line>

While the last `Conductor:` line names a model other than Fable 5.2,
`check_run.py --seal` refuses a plan with neither a `Judge plan:` nor a
`Judge unreachable:` line below the last `Plan checksum:` line, a value that
is empty or a placeholder not counting:

    decisions.md: the conductor is on Opus 5.5, so the plan needs the Fable judge: a 'Judge plan: ...' line, or 'Judge unreachable: ...', below the last 'Plan checksum:' line

As with `Plan judged:`, a seal after a change to `staffing.md` alone needs
no new judge line.

In a run `/swd:queue` started on a model other than Fable 5.2, which
nobody attends, the seal takes the model from the queue, not from the
`Conductor:` line, and a `Judge unreachable:` line does not count: of
the `Judge plan:` and `Judge unreachable:` lines below the last
`Plan checksum:` line, the last must be a `Judge plan:` line whose
verdict is that the plan holds. Otherwise `check_run.py --seal`
refuses, and the run stops as blocked, or, for a verdict that the plan
does not hold, the plan goes back to the architect:

    decisions.md: this run was started by /swd:queue and the conductor is on Opus 5.5, so the plan needs the Fable judge's verdict: the last 'Judge plan:' or 'Judge unreachable:' line below the last 'Plan checksum:' line must be 'Judge plan: ...'; 'Judge unreachable:' is not enough, and the run stops as blocked
    decisions.md: this run was started by /swd:queue and the conductor is on Opus 5.5, so the plan needs the Fable judge's verdict that it holds: the last 'Judge plan:' line below the last 'Plan checksum:' line does not say 'the plan holds', and the conductor of such a run does not overrule it; the plan goes back to the architect

A run started any other way seals as above. In a run `/swd:queue`
started, `check_run.py --task` and the check of a finished run also
report a run whose `decisions.md` has no `Plan checksum:` line, and
no builder is dispatched for a plan the seal has not accepted:

    decisions.md: this run was started by /swd:queue and has no 'Plan checksum:' line: its plan was never sealed, so no builder may work on it, and the run stops as blocked

`check_run.py --seal` adds lines of the form `Plan checksum: <sha256>` and,
from 0.8.1, `Staffing checksum: <sha256>`. The last of each must match
`plan.md` and `staffing.md`; nobody writes these by hand. A run with no
`Staffing checksum:` line was sealed by an earlier version, and its
`staffing.md` is not compared.

## staffing.md

The principal writes it before the seal. A row per plan task is required;
the `plan`, `review` and `final` rows are written in the modes that have
those dispatches. The `review` row is for the code reviewer and the
security reviewer wherever the mode dispatches them, for one task or for
the whole change; the `final` row is for final QA. A prototype's `review`
row is its one review at the end. A quick run has no `plan` or `review`
row, and its `final` row names `code-reviewer`. The seal requires the
`final` row in every mode and the `review` row in production and prototype
mode.

```markdown
# Staffing

| For | Agent | Model | Effort | Why |
|---|---|---|---|---|
| plan | architect | opus | medium | Design in an existing codebase |
| T1 | generalist-engineer | opus | medium | Multistep change to the checker and its tests |
| T2 | docs-writer | opus | low | Well-specified wording change |
| review | code-reviewer, security-reviewer | opus | medium | Review is where Opus 5.5 gains most |
| final | qa-engineer | opus | low | Runs commands and compares output |
```

`For` is a task id, or `plan`, `review` or `final`. `Agent` is the bare role
name as in the ledger, with no `swd:` prefix; agents sharing a row are
comma-separated. A task's `Agent` is the `Role` its plan names. `Model` is
`haiku`, `sonnet`, `opus` or `fable`; `Effort` is `low`, `medium`, `high` or
`xhigh`. When a task is moved up after a failed fix, its row is changed and
the ruling goes in `decisions.md`, and the run is sealed again.

Every line of this file that contains `|` is read as a row, with or
without a leading `|`. Only the header (its first four cells are `For`,
`Agent`, `Model`, `Effort`) and a separator whose cells hold nothing but
dashes and colons are skipped. `check_run.py --seal` refuses a row that
does not have five cells, and a row whose `For` cell is not a task id of
the plan, `plan`, `review` or `final`, an empty cell included. So a note
in this file must not contain `|`, and neither may a `Why` cell.

The model on a `review` or `final` row may not rank below the model on
any task's row (`haiku` < `sonnet` < `opus` < `fable`); a row naming
two agents is compared once, by its one `Model` cell. Effort is not
compared. `check_run.py --seal` refuses a table that breaks this.

The seal covers this file. After it, a changed row is reported by
`check_run.py --task` and by the check of a finished run until the
principal seals again.

## Builder reports

File: `reports/T<n>-<role>.md`, for example `reports/T1-generalist-engineer.md`.
All six headings are required. The two test sections must contain the real
command and its real output. `## Files changed` lists every file the task
created, changed or deleted, one per line, by its path from the project
root: the principal compares it with what actually changed.

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

The verdict line is exactly `Verdict: pass` or `Verdict: fail`, and a report
has exactly one. Do not quote another report's verdict line at the start of
a line.

| Report | File |
|---|---|
| Code review of one task | `reports/T<n>-code-reviewer.md` |
| Security review of one task | `reports/T<n>-security-reviewer.md` |
| Code review of the whole change | `reports/final-code-reviewer.md` |
| Security review of the whole change | `reports/final-security-reviewer.md` |
| Final QA | `reports/final-qa-engineer.md` |

## Judge reports

File: `reports/judge-<n>.md`, numbered from 1 in the run, written only by
the judge (`swd:judge`). It is not a checker report: its verdict is a
sentence, not `pass` or `fail`, and `check_run.py` does not read it.

    Verdict: <one sentence: the decision the principal is to follow>

    ## Question
    <the question from the brief, word for word>

    ## Reasoning
    <what in the run folder and the project decides it, by file and line>

The `Verdict: ` line is the first line and the only line that starts with
`Verdict:`. On the plan it is `Verdict: the plan holds` or
`Verdict: the plan does not hold: <what must change>`.

Before each judge dispatch, choose the lowest `n` with no
`reports/judge-<n>.md`; a reply that starts `No verdict` did not reach
the judge, whatever file is there. The judge never reads
`reports/pr-feedback-*.md` or `pr-reply-*.md`; a brief quotes the items
a question turns on.

## Commits

- A task commit has the subject `T<n>: <title>` and changes only that task's
  files.
- A prototype-mode wave commit has the subject `W<n>: <summary>` and changes
  only files owned by tasks in that wave.
- Files under `.swd/` may be included in any commit.
