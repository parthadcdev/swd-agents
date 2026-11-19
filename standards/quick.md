# Engineering standard: quick

This run is a small, low-risk change to a project the team already knows.
It takes the short path: one builder, then one reviewer who also does QA's
job. The formats for the plan, ledger and reports follow below.

## Priority

A correct small change, delivered fast. Do exactly what was asked and
nothing around it. If the change turns out to be bigger or riskier than it
looked, say so under `## Concerns` and stop: the principal will move the
run to a fuller mode.

## Builder process

1. Read the project notes your brief names, your part of the plan, which
   the command on your brief's `Read the plan with:` line prints, and the
   reports your brief names.
2. Write the test for the behaviour the task requires.
3. Run it and watch it fail. Copy the command and its output into
   `## Test first (failing)` in your report.
4. Write the code that makes it pass, following the project's conventions.
5. Run it and watch it pass. Copy the command and its output into
   `## Test after (passing)`.
6. Run the task's `Check` command and the project's test command, and
   confirm both pass.
7. Write your report. Keep it short.

Run the check with the command on your brief's `Run tests with:` line, not
by hand. It runs your task's check in the worktree and records the real
output and result in the run folder, in the order they happened. That
record, a failing run followed by a passing one, is what proves the test
came first; a run you make by hand proves nothing to the reviewer. Copy
what it prints into your report.

Change only the files your task owns. If you need a change in a file you do
not own, stop and say exactly what you need under `## Concerns`.

## Testing

Tests cover the behaviour that changed, including the edge cases the change
itself creates. The builder runs the project's whole test command before
reporting, because nobody else will before review.

## Review

One review of the whole change. The reviewer is the only checker, so it
also runs the project's test command, exercises each acceptance criterion
in `spec.md` against the real software and compares the result with the
plan's `## Outcome`, and records the command and output for each.

## Security

There is no separate security review, because a change that touches a
trust boundary (authentication, secrets, user input that reaches a query
or a shell, payments) does not belong in quick mode. If the change turns
out to touch one, the builder or reviewer says so and the run moves to
production mode.

## Performance

Do not make the code slower in an obvious way. Under `## Complexity`, one
line is enough.

## Docs

Update the docs and the changelog when the change is visible to a user of
the code. Otherwise none.

## Commits

One commit, subject `T1: <title>`, made by the principal after the review
passes. Builders and checkers do not commit.
