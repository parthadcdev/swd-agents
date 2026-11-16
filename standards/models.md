# Model guidance

This is the team's standing rule for which Claude model and effort level
each agent runs at, and for how an agent is briefed. It applies to every
swd run and to every agent in it.

Source: Anthropic's guidance for Claude Fable 5.2 and Claude Opus 5.5
(the model guide's sections "Migrating to Claude Fable 5.2" and
"Migrating to Claude Opus 5.5").
Taken: 2026-11-15.

It holds until Anthropic publishes newer guidance. When that happens,
this one file is replaced, with the new source and date. Nothing else in
the plugin repeats it.

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

Apply these as judgement to what each dispatch needs. They are not a
table to look up.

- **Know what every agent runs on.** Subagents can be most of a run's
  cost. Set the model and the effort explicitly on every dispatch, and
  never leave either to a default.
- **Effort is the main control** for intelligence, time and cost. To
  get less thinking, lower the effort level; telling an agent to think
  less does not work.
- **Start from Opus 5.5 at `medium`** for design, review and multistep
  building in an existing codebase. At `medium` it matches or beats the
  previous Opus at `high` on that work for about half the tokens, and
  agentic coding and code review are where it gains most. `low` comes
  close on several coding tasks at much lower cost, so use it for a
  task that is well specified.
- **Lower effort before a cheaper model.** Before choosing `sonnet` or
  `haiku`, consider `opus` at `low`. A cheaper model fits work that is
  mechanical and fully specified.
- **Judge cost per completed task**, not per dispatch. A cheaper
  dispatch that needs more fix attempts is not cheaper.
- **Fable 5.2 conducts, at `high`.** Planning and orchestrating other
  models is what it does well. Dispatch `fable` as a subagent only for
  work the others have failed at.
- **`xhigh` only where a gain has been shown:** the same task has
  failed at `high`. After a failed attempt, raise the effort before the
  model.
- **Brief with the goal and the reason**, and the constraints, not an
  enumerated list of steps. Briefs written for earlier models are often
  too prescriptive, which lowers the quality of the result.
- **Checkers start fresh.** A separate checker with fresh context does
  better than self-critique, so nobody checks their own work.
