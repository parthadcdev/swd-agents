# Model guidance

This is the team's standing rule for which Claude model and effort level
each agent runs at, and for how an agent is briefed. It applies to every
swd run and to every agent in it.

Source: Anthropic's guidance for Claude Fable 5.2 and Claude Opus 5.5
(the model guide's sections "Migrating to Claude Fable 5.2" and
"Migrating to Claude Opus 5.5").
Taken: 2026-11-15.

Two rules here are not Anthropic's guidance: **Builders start on
`sonnet`** and **The first failed check moves the task to `opus`**.
They are the project owner's rule, set on 2026-11-17 to lower what
builders cost, and no measurement supports them yet. Everything else
in this file is Anthropic's guidance.

The guidance holds until Anthropic publishes newer guidance. When that
happens, this file is replaced, with the new source and date, and the
owner's rule is kept unless the owner changes it. The build playbook
applies this file; other files point at it and must agree with it.

## Every agent

- **Finish the whole task.** A model is more likely to stop early at
  `low` and `medium` effort. Whatever level you were dispatched at, do
  every part of the task in your brief before you report. If a part
  cannot be done, say which and why; do not leave it out silently. A part
  that needs a file you do not own, or an action your role forbids, is a
  part that cannot be done: stop and report it.
- **Report only what a tool result shows.** State that something works,
  passes or exists only when a command you ran or a file you read in
  this session shows it. What you did not run or read, say you did not.

## The principal: model and effort for each dispatch

Apply these as judgement to what each dispatch needs, except the two
owner's rules, which are rules and not judgement calls. They are not a
table to look up.

- **Know what every agent runs on.** Subagents can be most of a run's
  cost. Set the model and the effort explicitly on every dispatch, and
  never leave either to a default.
- **Effort is the main control** for intelligence, time and cost. To
  get less thinking, lower the effort level; telling an agent to think
  less does not work.
- **Start from Opus 5.5 at `medium`** for design and review: the
  architect, the code reviewer, the security reviewer and QA start from
  Opus 5.5 at `medium`. At `medium` it matches or beats the previous
  Opus at `high` on that work for about half the tokens, and agentic
  coding and code review are where it gains most. `low` comes close on
  several coding tasks at much lower cost, so use it for a check that
  is well specified.
- **Builders start on `sonnet`.** A builder's first attempt is on
  `sonnet`: the five engineer roles and the docs writer. You still
  choose the effort. `haiku` stays for work that is mechanical and fully
  specified, such as the preflight write check. A builder does not
  start above `sonnet`. A task that a root-cause re-plan adds in place
  of a task that failed starts on the model the failed task had
  reached, not on `sonnet` again.
- **The first failed check moves the task to `opus`.** When a check of
  a task's work fails and the task's row in `staffing.md` is on a model
  below `opus`, change that row to `opus` before you dispatch the fix.
  This is a rule, not a judgement call. Keep the effort as it was. In
  the same edit raise the `review` and `final` rows to at least `opus`,
  record the ruling in `decisions.md`, and seal again before the
  dispatch. A failed check is any of these: a reviewer's
  `Verdict: fail`, the task's own tests failing where the mode has no
  per-task review, a failed run of the test suite for a wave or for the
  final check that the task owns, and a failed final QA or final review
  that the task owns. A re-dispatch for a missing or unusable report, a
  report sent back for correction, and a dispatch the permission
  system refused are not failed checks and do not move the model.
- **A task already on `opus`** that fails again moves up by judgement:
  raise the effort first, and the model only when more effort is not
  what the failure needs.
- **Judge cost per completed task**, not per dispatch. A cheaper
  dispatch that needs more fix attempts is not cheaper.
- **Fable 5.2 conducts, at `high`,** or Opus 5.5 where the project's
  conductor setting is `opus` (`/swd:conductor`). Planning and
  orchestrating other models is what Fable 5.2 does well. Dispatch
  `fable` as a subagent only for work the others have failed at, and as
  the judge of a conductor that is not on Fable 5.2.
- **`xhigh` only where a gain has been shown:** the same task has
  failed at `high`.
- **Brief with the goal and the reason**, and the constraints, not an
  enumerated list of steps. Briefs written for earlier models are often
  too prescriptive, which lowers the quality of the result.
- **Checkers start fresh.** A separate checker with fresh context does
  better than self-critique, so nobody checks their own work.
