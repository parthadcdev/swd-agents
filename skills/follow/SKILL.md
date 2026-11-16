---
name: follow
description: Follow up the pull requests that earlier swd runs opened. Fixes failing checks and addresses review comments through the swd team, pushes the fixes and replies on the pull request. Use when the user runs /swd:follow.
---

# Follow up pull requests

A run that finished with a pull request is not finished for the user until
the pull request is green and its review comments are answered. This skill
picks those runs up again.

The plugin root is two directories above this skill's base directory;
`<plugin>` means that path. `<run>` is a run folder under `.swd/runs/` in
the user's project, given as an absolute path.

The rules of the build playbook apply to every change you make here. Read
the Design steps 4 and 5, Gate, Build, Fix loop and Never sections of
`<plugin>/skills/build/SKILL.md` before you dispatch anyone. You still
never write product code yourself.

## Steps

1. Find the runs to follow: every run folder whose last `Finish:` line in
   `decisions.md` is `Finish: pr`.
2. For each, ask what its pull request needs, waiting up to five minutes
   for checks that are still running:

   ```bash
   python3 <plugin>/scripts/swd-pr.py --wait 300 <run>
   ```

   | Exit code | Meaning | What you do |
   |---|---|---|
   | 0 | Green with nothing new, or merged or closed | Report its state. A merged pull request's branch is cleaned up by housekeeping at the start of the next run |
   | 20 | Checks are still running | Say so; the user can run `/swd:follow` again later |
   | 1 | Could not tell | Report the message it printed |
   | 10 | Failing checks or new comments | Work through "When action is needed" below |

3. Report, for each pull request: its link, what was wrong, what you
   changed, what you replied, and what is still open.

## When action is needed

The script has written the failing checks and the new comments to
`<run>/reports/pr-feedback-<n>.md`.

1. **Go back into the run.** If the run's worktree (the `Worktree:` line in
   `decisions.md`) is gone, recreate it from the run's branch:
   `git worktree add <worktree path> <branch>`. Move into it as a command
   of its own and confirm with `pwd`.
2. **Sort the feedback.** For each item decide: a change to make, or a
   reply only. A question, or a request you judge wrong for the code, gets
   a reply that explains, with no change. Do not make changes nobody asked
   for.
3. **Route each change to its owner.** The builder role that owns the file
   in `plan.md` gets the normal brief plus `Fix: reports/pr-feedback-<n>.md`.
   Test-first, the `check_run.py --task` check, the reviews for the run's
   mode and the commit all work exactly as in the build playbook's Fix
   loop. Set the Agent tool's `model` and `effort` on every dispatch, as
   `<plugin>/standards/models.md` says: the task's row in the run's
   `staffing.md` for its builder and the `review` row for its reviewers (the `final` row in a quick run),
   where there are such rows, your own choice by that rule where there are
   not.
   If a change is in a file no task owns, send the architect to add a
   task, then check, judge, staff and seal the amended plan as the build
   playbook's Gate describes, and build that task. A run from before 0.8.0
   has no `## Outcome`, no `- Outcome:` lines and no `staffing.md`, and
   the seal needs all three: have the architect add the Outcome section
   and every task's `- Outcome:` in the same amendment, and write
   `staffing.md` with a row for every task and the `review` and
   `final` rows the run's mode has, no checker's model below a builder's.
   A run sealed under 0.8.0 is held to the same rows and floor when it is
   sealed again, so raise a `review` or `final` row that sits below a
   builder's first. That seal also reads any line with a `|` as a row and
   refuses a `For` that is not a task id, `plan`, `review` or `final`, so
   rename such a row and take any `|` out of a note. A change to `staffing.md` without an amended plan is
   sealed again without a new `Plan judged:` line. A finished task's row
   says what a fix to it is dispatched at.
4. **Keep the records.** Update the ledger and log every dispatch, verdict
   and commit with `swd-log.sh`. When the fixes are in, log `done` again and
   run `python3 <plugin>/scripts/check_run.py <run>` until it prints
   nothing.
5. **Push.** `git -C <work> push origin <branch>`. A plain push only; if it
   is rejected, stop and ask the user.
6. **Reply on the pull request.** Write `<run>/pr-reply-<n>.md`. Its first
   line starts with `[swd]`, which is how the team's own comments are told
   apart from feedback. Then one line per item: what changed and in which
   commit, or why nothing changed. Post it:

   ```bash
   gh pr comment <branch> --body-file <run>/pr-reply-<n>.md
   ```

7. **Close the loop.** Record the feedback as dealt with, leave the
   worktree, and remove it:

   ```bash
   python3 <plugin>/scripts/swd-pr.py --mark-handled <run>
   ```

   then `cd <project folder>`, `git worktree remove <worktree path>` and
   `python3 <plugin>/scripts/check_run.py --finish <run>`.
8. **Check again.** Run step 2 once more for this pull request, so a check
   that fails on the new commit is caught. Do at most three rounds for one
   pull request in one go; after that, report what is still failing and
   stop.

## Never

- Never merge a pull request, approve it, or dismiss or resolve someone's
  review. Those are the user's and the reviewers' decisions.
- Never force-push.
- Never post a comment that does not start with `[swd]`.
- Never change code for feedback that is not in the feedback report.
