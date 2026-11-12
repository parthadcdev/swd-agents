# Engineering standard: production

This run is building production code. Everyone on the team works to this
standard. The formats for the plan, ledger and reports follow below it.

## Priority

Quality over speed. A slower run that ships correct, tested, maintainable
code is the goal. Do not cut a check to finish sooner.

## Builder process

Every builder task follows this order. The order is the point: a test
written after the code only proves the code does what it already does.

1. Read your task in `plan.md`, the contracts above the task list, and the
   reports your brief names.
2. Write the test for the behaviour the task requires.
3. Run it and watch it fail. Copy the command and its output into
   `## Test first (failing)` in your report. It must fail because the
   behaviour is missing, not because of a typo or import error.
4. Write the code that makes it pass, following the conventions the repo
   already uses.
5. Run it and watch it pass. Copy the command and its output into
   `## Test after (passing)`.
6. Run the task's `Check` command from `plan.md` and confirm it passes.
7. Write your report.

When the work has no meaningful unit test (CI config, docs), write a check
first instead: run the config, or run the commands the docs show. The same
fail-then-pass evidence goes in the report.

Change only the files your task owns. If you need a change in a file you do
not own, or the plan is missing something or is wrong, stop. Say exactly what
you need under `## Concerns` and finish your report. Do not work around it:
the principal will decide and send the work to whoever owns that file.

## Testing

- Tests cover the core path, the edge cases (empty, zero, one, many, limits)
  and the failure paths (bad input, missing data, errors from dependencies).
- Test behaviour through the public interface, not internal details.
- During a wave, run only your own tests. Other builders are editing the
  same working copy, so the full suite may be mid-change. QA runs the full
  suite when the wave ends.

## Review

Every task is reviewed by the code reviewer before it is committed. A task
whose report lacks the failing and passing test output is rejected without
further review.

## Security

Every task and the whole change get a security review. Builders validate
input at trust boundaries, never put secrets in code or logs, and never
build queries or shell commands by joining strings with user input.

## Performance

- The architect's plan states the expected data sizes and sets a complexity
  target for every part that handles data at scale.
- Meet the complexity target the plan sets for your task.
- State the time and space complexity of any non-trivial logic under
  `## Complexity` in your report. Write "trivial" when there is none.
- Choose the algorithm and data structure that fit the expected data size
  the plan states.
- These are rejected in review:
  - a nested loop where a hash lookup works;
  - a database or network call inside a loop;
  - recomputing the same value repeatedly;
  - loading a whole table or file to use one row.
- When code is on a hot path, measure it and put the measurement in the
  report. Do not guess.
- Do not micro-optimise at the cost of readability.

## Docs

Usage docs and a changelog entry for anything a user of the code can see.

## Commits

One commit per task, subject `T<n>: <title>`, made by the principal after the
task passes review. Builders and checkers do not commit.
