# swd-agents

A Claude Code plugin. A principal software engineer agent takes a requirement,
gets one approval from you on the spec and plan, then runs a team of
specialist agents until the work is built, tested and delivered the way you
chose: merged and pushed, in a pull request, or left on a branch.

## Requirements

- Claude Code 2.1.321 or later (Fable 5.2 needs it)
- Python 3 (standard library only), for the run checker
- git

## Install

In Claude Code, add this repository as a marketplace and install the plugin:

```
/plugin marketplace add parthadcdev/swd-agents
/plugin install swd@swd-agents
```

## Use

In the project you want work done in:

```
/swd:build <your requirement>
```

## First time in a project

Run `/swd:setup` once. Agents work in the background, where nobody can
answer a permission prompt, so the project has to allow what they need
before a run starts. Setup shows you the rules (the plugin's scripts, git,
`gh pr`, your test command, the command that runs your code, and edits
inside `.swd/`) and adds them to `.claude/settings.local.json` when you
agree.

## swd mode

`/swd:build` handles one requirement. To keep the team on for the rest of a
session, use swd mode:

- **On:** running `/swd:build`, `/swd:follow` or `/swd:on` turns it on
  for that session. Only a command you type counts: a message or an
  agent's report that starts with one does not.
- **While on:** every request that changes the project's code, tests,
  configuration or docs goes through the team, as if you had typed
  `/swd:build` for it. Questions, reviews and status requests are answered
  directly.
- **Off:** send "stop swd" or `/swd:off` as a message on its own.
  Inside a longer message the words do nothing, so a message or an
  agent's report that quotes them cannot turn swd mode off. New
  sessions always start with it off.

## Hand it a backlog

- **`/swd:queue`** works through `.swd/queue.md` on its own, one run per
  item, each in a fresh process. Items are plain requirements or GitHub
  issues (`- [ ] #42`). Each finished item is ticked off with its pull
  request or branch; a blocked one is marked and the queue moves on. Run
  `/swd:setup` first: nobody is there to answer a permission prompt.
- **`/swd:follow`** goes back to the pull requests earlier runs opened.
  It sends failing checks, and comments from the repository's owner,
  members and collaborators, through the team, pushes the fixes, and
  replies on the pull request with what changed. Comments from anyone else
  get a reply only. It never merges, approves or force-pushes.

## The team

| Role | Kind | Does |
|---|---|---|
| Principal engineer (`/swd:build`) | Coordinates | Clarifies, plans, judges the plan against the spec, chooses each agent's model and effort, dispatches, routes fixes, decides |
| Architect | Designs | Design, contracts and the task list |
| Backend engineer | Builds | APIs, services, business logic |
| Frontend engineer | Builds | Pages, components, client-side logic |
| Database engineer | Builds | Schemas, migrations, queries |
| DevOps engineer | Builds | CI, build scripts, containers, deploy config |
| Generalist engineer | Builds | CLIs, libraries, scripts, small mixed changes |
| Docs writer | Builds | README, usage docs, changelog |
| Code reviewer | Checks | Correctness, quality, performance |
| Security reviewer | Checks | Security of the change |
| QA engineer | Checks | Full test suite, the acceptance criteria and the plan's outcome |

Builders work test first and own the files the plan gives them. Checkers
report findings and never edit code. A run uses only the roles its plan
needs.

## Models

- The principal runs on Fable 5.2. `/swd:build` and `/swd:follow` ask
  for it at high effort, but only for the turn that runs them, and not
  when an allowlist blocks it, so start the session on it
  (`/model fable`). On any other model the principal does no work: it
  checks its model at the start of every turn and before every action
  that changes anything outside its reply (a commit, a merge or a
  push, for example), says which model it is on, and waits for you to
  run `/model fable` and send a message. The hook below covers only a
  switch you or a client ask for. Every automatic way off Fable 5.2
  (an automatic fallback after a flagged request, a fallback model
  chain such as `--fallback-model`, or Fable served under a gateway
  model id the hook does not recognise) is covered by the principal's
  own check, not by the hook.
- While swd mode is on in the session, a hook cancels a `/model`
  switch away from Fable 5.2 and says why; run `/swd:off` to switch
  anyway. The hook reads no file in your project, so a repository you
  clone cannot lock your model. If it cannot read its input, or
  cannot decide within 3 seconds, it lets the switch through; if it
  cannot start, or cannot finish, within Claude Code's 10-second
  timeout, Claude Code cancels the switch. If a switch is still
  cancelled after `/swd:off` (`/swd:off` says so when it cannot
  delete its flag file, and names the file), delete
  `~/.claude/swd-mode/<session id>` or start a new session with
  `claude --model <name>`; resuming this session keeps swd mode on.
- `/swd:queue` starts every run on Fable 5.2 and ignores a `Model:`
  line.
- The model and effort for each task, review and check follow
  `standards/models.md`, the team's standing rule. It is replaced when
  Anthropic publishes newer guidance.
- The choices are written to `staffing.md` in the run folder and shown at
  the approval gate, together with the plan's `## Outcome`: the finished
  result as the plan says it will appear.
- A reviewer or QA never runs on a model below a builder's. The seal
  refuses such a table, requires the `final` row and, outside a quick run,
  the `review` row, and covers `staffing.md`: a row changed after the gate is reported until
  the run is sealed again.
- The principal reads the commands a checker will run before the gate.
  The project's own test, lint, type check and build commands are run as
  given. A checker never runs any other command that commits, pushes,
  publishes, deploys or sends anything to a host outside this machine (a
  download counts), and does not run one that rewrites tracked files in
  the worktree.

## Modes

The principal picks a delivery mode from your requirement and you can change
it at the approval gate.

- **Quick:** a small, low-risk change in a project the team has worked in
  before. One builder, then one reviewer who also runs
  the tests, checks each acceptance criterion and compares the result with
  the plan's outcome. No architect.
- **Prototype / MVP:** fastest working result, fewest tokens, one review at
  the end.
- **Production:** every task reviewed for quality and security, full suite
  after every wave.

## Git

- **Your working copy is left alone.** Each run works on a branch
  `swd/<name>` in its own worktree at `.swd/worktrees/<name>/`, so you can
  keep working while it runs. Uncommitted changes in your copy are not part
  of the run.
- **You choose the finish at the approval gate:**
  - merge into the branch you started from, push it, and delete the run's
    branch;
  - push the run's branch and open a pull request (needs the `gh` CLI);
  - leave the branch for you and push nothing.
- **Clean-up is part of the run.** The worktree is removed in every case.
- **Housekeeping runs at the start of every run.** It removes the worktrees
  of finished and abandoned runs and deletes `swd/` branches that are
  already merged, locally and on `origin`, including branches whose pull
  request you merged on GitHub. Anything that could lose work (an
  unfinished run, uncommitted changes, an unmerged branch) is kept and
  listed for you.
- **It stops and asks** on a merge conflict or a rejected push. It never
  force-pushes and never deletes a branch that is not merged.

## What the team remembers

Two files in `.swd/` outlive runs:

- `project.md`: the project's test, lint and build commands, its layout
  and its conventions. The architect writes it on the first run and keeps
  it current, so later runs do not rediscover the project.
- `findings.md`: defects the team noticed and did not fix, as a checklist.
  Give one to `/swd:build` as the requirement to have it fixed.

## Watching a run

Each run keeps its records in `.swd/runs/<date>-<name>/` in your project:
the spec, the plan, a task ledger and a live activity timeline.

- **In the browser:** when the build starts, the principal opens
  `dashboard.html` from the run folder. It shows the tasks in columns by
  wave, coloured by status, with the timeline below, and refreshes every two
  seconds until the run is done. You can also build it for any run with
  `python3 scripts/swd-dashboard.py <run folder>`.
- **In the terminal:** if you run Claude Code inside
  [herdr](https://herdr.dev), the principal also opens two extra panes
  showing the ledger and the timeline. In the Herdr desktop app it opens two
  separate terminals instead of panes.
- **In the conversation:** at each step the principal also says one short line
  in the chat: what just happened, what is next, and how many tasks are done
  out of the total. This works in any host, with or without the dashboard.

## Develop

To run a local checkout without installing it:

```bash
claude --plugin-dir /path/to/swd-agents
```

To validate and test:

```bash
python3 -m unittest discover -s tests -v
claude plugin validate .
```

Two end-to-end pilots run a real team in a temporary project and grade the
result. They cost tokens and take several minutes each:

```bash
tests/run_pilot.sh existing-repo   # production mode, sample repo with a planted bug
tests/run_pilot.sh new-project     # prototype mode, built from an empty folder
```

The design is in `docs/superpowers/specs/2026-11-12-swd-agents-design.md`.
