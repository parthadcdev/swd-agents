# Engineering standard: prototype

This run is building a prototype or MVP. Everyone on the team works to this
standard. The formats for the plan, ledger and reports follow below it.

## Priority

The fastest working outcome, with the least effort and the fewest tokens.
Build the smallest thing that meets the acceptance criteria. Leave out
anything the requirement does not ask for: options, abstractions, extra
error handling, polish.

Three things are not relaxed: tests are written first, the run does not
finish with a failing test, and nothing destructive happens without the
user's yes.

## Builder process

Every builder task follows this order.

1. Read your task in `plan.md`, the contracts above the task list, and the
   reports your brief names.
2. Write a test for the behaviour the task requires.
3. Run it and watch it fail. Copy the command and its output into
   `## Test first (failing)` in your report.
4. Write the simplest code that makes it pass.
5. Run it and watch it pass. Copy the command and its output into
   `## Test after (passing)`.
6. Run the task's `Check` command from `plan.md` and confirm it passes.
7. Write your report. Keep it short.

Change only the files your task owns. If you need a change in a file you do
not own, or the plan is missing something or is wrong, stop and say exactly
what you need under `## Concerns`.

## Testing

- Tests cover the acceptance criteria and the core path. Skip edge cases
  the requirement does not mention.
- During a wave, run only your own tests. The full suite runs once, at the
  end of the run.

## Review

One code review of the whole change, at the end of the run. Tasks are not
reviewed one by one. The review looks for what is wrong or broken, not for
polish.

## Security

A security review happens only when the change touches a trust boundary:
authentication, secrets, user input that reaches a query or a shell, or
payments. Even in a prototype, never put a secret in code and never build a
query or shell command by joining strings with user input.

## Performance

Avoid choices that are plainly wrong for the data involved, such as a query
inside a loop. There are no complexity targets. Under `## Complexity` in
your report, one line is enough.

## Docs

A short README: what it is and how to run it.

## Commits

One commit per wave, subject `W<n>: <summary>`, made by the principal after
every task in the wave has returned with its own tests passing. Builders and
checkers do not commit.
