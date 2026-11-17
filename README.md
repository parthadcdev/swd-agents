# swd-agents

A Claude Code plugin. A principal software engineer agent takes a requirement,
gets one approval from you on the spec and plan, then runs a team of
specialist agents until the work is built, tested and delivered the way you
chose: merged and pushed, in a pull request, or left on a branch.

## Requirements

- Claude Code 2.1.321 or later (Fable 5.2 needs it)
- Python 3.9 or later (standard library only), for the hooks and the
  run's scripts. `/swd:setup` offers to install it on Windows.
- git, and on Windows Git for Windows (see below)

## Windows

swd runs on native Windows (Claude Code started from PowerShell or
CMD, not WSL) when Git for Windows is installed: Claude Code runs the
plugin's hooks and the team's commands in Git Bash. Without Git for
Windows Claude Code runs the hooks in PowerShell, where they fail.

Python 3.9 or later is needed. When it is missing, every prompt gets a
one-line notice, and `/swd:setup` offers to install Python 3.13 with
winget. It installs only after you say yes, then checks that Python
runs. On macOS and Linux it prints the command to run instead.

Looking for Python never installs it: the plugin starts Python with
`PYTHON_MANAGER_AUTOMATIC_INSTALL=false`, so the Python install
manager does not install a runtime on its own when none is installed.

If Claude runs commands in PowerShell instead of Bash, set
`CLAUDE_CODE_USE_POWERSHELL_TOOL=0`.

Not supported on Windows: the herdr watch panes, the end-to-end
pilots (`tests/run_pilot.sh`), and `/swd:queue` with Claude Code
installed by npm (`claude.cmd`); install Claude Code with the native
installer for the queue.

The test suite is set to run on Windows in CI
(`.github/workflows/test.yml`), with stubs for winget and Python. How a
real Claude Code session on Windows behaves, and the install manager
setting above, come from Claude Code's and Python's documentation;
nobody on the team has run it on a Windows machine yet.

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
before a run starts. Setup first checks that Python 3.9 or later is
there. Then it shows you the rules and adds them to
`.claude/settings.local.json` when you agree:

- one allow rule for each script a run needs, for each of `python3`,
  `python` and `py -3`, naming the script's full path in the installed
  version's folder, such as
  `Bash(python3 /Users/you/.claude/plugins/cache/swd-agents/swd/0.11.0/scripts/check_run.py *)`.
  Each matches that script with any arguments and nothing else.
  Setup writes them for the plugin's path as Claude Code gives it to
  the skills and, when that path resolves to another spelling (a
  symlinked `~/.claude`, for example), for that spelling too;
- two `sh` rules for the Python check and the watch terminals, and a
  rule to read the plugin's files;
- git, `gh pr`, a few read-only commands, edits inside `.swd/`, your
  test command, and the command that runs your code, such as
  `Bash(python3 *)`, which is the broadest rule in the set: it lets
  agents run any program with that interpreter in this project.

Before you say yes, read the rules for your project's commands.
`/swd:setup` takes them from `.swd/project.md` when there is one: the
test command from its `Test command:` line, and the lint, type check
and build commands it records. That file may have been written by an
agent in an earlier run. If one of them names a shell or a program that
runs other commands it is given, say no. Setup always writes the rules
for the `Test command:` line, so a wrong one is corrected in the file;
another command is left out by not passing it with `--command`.

Setup also writes seven ask rules: `Bash(python3 *swd-setup.*)`,
`Bash(python *swd-setup.*)`, `Bash(py *swd-setup.*)`,
`Bash(python3 *swd-queue.*)`, `Bash(python *swd-queue.*)`,
`Bash(py *swd-queue.*)` and `Bash(*SWD_UNATTENDED*)`. Claude Code asks you
before a command they match, whatever allow rule matches it too,
because an ask rule beats an allow rule. Once setup has written its
rules, Claude Code asks you to approve the setup and queue commands
that `/swd:setup` and `/swd:queue` run, every time, so that an agent
that follows the playbooks cannot change this project's permission
rules or start a queue without you; an agent set on getting round the
rules still can, as the limits below say.

Setup removes the rules an earlier version of the plugin wrote: the
three rules that let Python run anything under the plugin's folder, the
0.8.x `Bash(<plugin folder>/*)`, and the `sh` and per-script rules of
another version's folder. It lists them before you say yes, keeps every
other rule, yours included, in order, and reports how many rules it
added and how many it removed. A settings file that is not valid JSON
is left unchanged, and setup says so.

The plugin's hook, `hooks/swd-mode.py`, is not one of the scripts the
allow rules name. Setup also adds three deny rules,
`Bash(python3 *swd-mode.*)`, `Bash(python *swd-mode.*)` and
`Bash(py *swd-mode.*)`, so Claude Code refuses the plain ways of
running the hook by name, even in a project with an interpreter rule:
without them an agent could pipe a forged event into the hook there
and turn swd mode off or set the conductor to `opus`. A
deny rule refuses the command; it does not ask. The rules name the
file up to its dot, `swd-mode.`, so the hook's compiled copy in
`hooks/__pycache__/` is refused too, while a run folder whose name
contains `swd-mode` is not caught. They name no folder at all, so they
hold after an update, and in a project with them a command that starts
with `python3`, `python` or `py` and contains `swd-mode.` is refused,
also as one part of a pipe or a chain, while one that runs Python under
another name, such as `/usr/bin/python3` or `python3.12`, is not.
Claude Code still runs the hook itself on its
events: permission rules apply to Claude's tool calls, not to hooks.
They are not a hard boundary: they match command text, so they do not
stop the name in another letter case on a file system that ignores
case (macOS, Windows), the name written another way, such as part of
it quoted or given through a shell variable, a shell wildcard, or code
a run executes by design, such as its tests.

Run `/swd:setup` again after each plugin update: the allow rules name
the installed version's folder, so they stop matching after an update
and a run asks permission for those commands. Until you run it,
`/swd:queue` stops and sends you here: it starts only when
`swd-setup.py --print` ends with `In place:`, which it does only when
the settings file holds every rule setup lists and none an earlier
version wrote.

### What the rules do not stop

The allow rules name each script a run needs by its full path, so a
command that runs the setup or queue script, a path that climbs out of
the plugin's folder with `..`, or a script name, the hook's included,
in another letter case, with a shell wildcard or partly quoted, matches
none of the plugin's allow rules: Claude Code asks before running it,
and in an unattended run, where nobody can answer, it does not run.

A project's interpreter rule, such as `Bash(python3 *)`, still lets an
agent run Python of its choice there, the hook or the setup script
under another spelling included: the ask and deny rules match command
text, so they catch only the plain spellings.

Some rules a run needs let an agent run a program of its choice in any
project: `Bash(git *)` matches `git -c` options that make git run a
program it names, the plugin's test runner runs the command a plan
names, and a run executes its own tests. So the rules keep an agent
that follows the playbooks from running the setup or queue script, but
they do not stop one that sets out to get round them.

Deny and ask rules hold in every permission mode, a mode that skips
permission checks included, except that a mod you installed can
approve a call they would stop when no managed settings or Team or
Enterprise login are in place; in a mode that skips permission checks
every command they do not match runs without a prompt, the other
spellings above included.

Setup refuses a project command, the test command in `.swd/project.md`
included, whose first word is not a plain program name or path or is
one of the programs it lists that run another command they are given,
not every program that can run another command: read each project
command's rules before you say yes. Setup also refuses to run from a
plugin folder whose path is not absolute, holds a `..` folder, is too
high (the file-system root, one folder below it, or your home folder
or above it), or holds a character other than letters, digits and
`. _ - + @ / : ~` (a space included), given with `--plugin-root` or
found by itself, because such a path would make its rules match
commands or files other than the plugin's scripts; it writes nothing
then. A plugin path with a space is not supported: the skills type the
path unquoted.

An agent could also change the rules by editing
`.claude/settings.local.json` itself. Claude Code's documentation lists
`.claude/` among the protected folders: an allow rule never
pre-approves an edit there, so the edit asks you in a session you
attend, is denied in a queue run, is left to the classifier in auto
mode, and goes through in a mode that skips permission checks. A
program an agent runs can still write the file in any mode.

`/swd:queue` sets `SWD_UNATTENDED` to the model it starts each run
with, `fable` or `opus`, and `check_run.py` reads it: the seal takes
the model from it, not from the `Conductor:` line. A run you start
yourself has no such variable. The ask rule `Bash(*SWD_UNATTENDED*)`
catches a command in which the name is written out plainly, not every
command that names the variable: a quoted or escaped spelling, or a
name built when the command runs, gets past it. The seal reads the
judge's line from `decisions.md`, which the conductor writes, so it
cannot show that the judge gave it. Whether Claude Code passes
`SWD_UNATTENDED` on to the commands a run executes has not been tried
on a live Claude Code; if it does not, a queue run seals as an attended
one does, as in 0.10.0.

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

## Which model conducts

The principal, the conductor of every run, runs on Fable 5.2 by
default. `/swd:conductor` lets Opus 5.5 conduct too, project by
project, for example when your Fable 5.2 quota is low:

```
/swd:conductor opus
/swd:conductor fable
/swd:conductor
```

The first lets Fable 5.2 or Opus 5.5 conduct runs in this project, the
second lets only Fable 5.2 (the default), and the third shows the
current setting. Type it yourself in a session in the project. The
reply's first line says what the hook did, such as
`swd conductor: set to opus`, and its second line which models may
conduct and in which folder:
`Fable 5.2 or Opus 5.5 may conduct swd runs in /work/p, its .swd/worktrees included.`
Any value other than `fable` or `opus` is refused and stores nothing:
the reply starts `swd conductor: refused, still <current setting>`.

- The setting is kept per project in `~/.claude/swd-conductor/`, one
  file per project, named by a hash of the project's folder.
  It applies in that folder and in the run worktrees under its
  `.swd/worktrees/`. A session started in another folder, a subfolder
  of the project included, has its own setting, which is `fable` until
  you set it there, so type the command in the folder you start Claude
  Code in for the project. It is kept until you change it.
- The hook stores it only for a command you type, and reads no file in
  your project to decide it, so no file in a repository you clone
  changes it by what it says. An entry the hook cannot read counts as
  `fable`. Code that runs as you can still change it, such as an
  agent's command or the project's own tests run by the team: it can
  run the hook or write the file directly. Setup's deny rules refuse
  the plain ways of running the hook by name, but they are not a hard
  boundary, and no rule covers writing the file (see First time in a
  project).
- Each run records the model it is conducted on in its `decisions.md`,
  as `Conductor: Fable 5.2` or `Conductor: Opus 5.5`.

## Hand it a backlog

- **`/swd:queue`** works through `.swd/queue.md` on its own, one run per
  item, each in a fresh process. Items are plain requirements or GitHub
  issues (`- [ ] #42`). Each finished item is ticked off with its pull
  request or branch; a blocked one is marked and the queue moves on. Run
  `/swd:setup` first: nobody is there to answer a permission prompt.
  Every run the queue starts is unattended. A run on Opus 5.5 stops as
  blocked when the Fable judge cannot be reached for its plan, and its
  plan is sealed only on the judge's verdict that it holds.
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
| Judge | Checks | On Fable 5.2, a verdict on the plan and on disputed or trust-boundary rulings, when the principal conducts on Opus 5.5 |

Builders work test first and own the files the plan gives them. Checkers
report findings and never edit code. A run uses only the roles its plan
needs.

## Models

- The principal runs on Fable 5.2, or on Fable 5.2 or Opus 5.5 in a
  project set to `opus` (see Which model conducts).
  `/swd:build` and `/swd:follow` no longer ask for a model: the
  session's model conducts, at high effort, so start the session on an
  accepted model (`/model fable`, or `/model opus` where the setting
  allows it). While swd mode is on, the hook's reminder on every
  message tells the principal which models the setting accepts; with
  no reminder it accepts only Fable 5.2. On any other model the
  principal does no work: it checks its model at the start of every
  turn and before every action that changes anything outside its reply
  (a commit, a merge or a push, for example), says which model it is
  on, and waits for you to run `/model fable` and send a message (or
  `/model opus`, where the setting is `opus`). So with the default
  setting a session on another model is stopped on the first turn;
  in 0.9.0 the skill's own `model: fable` ran that turn on Fable 5.2.
  The hook below covers only a switch you or a client ask for. Every
  automatic way off Fable 5.2, or off Opus 5.5 under `opus` (an
  automatic fallback after a flagged request, a fallback model chain
  such as `--fallback-model`, or a model served under a gateway model
  id the hook does not recognise), is covered by the principal's own
  check, not by the hook.
- While swd mode is on in the session, a hook cancels a `/model`
  switch away from the models the project's setting accepts, and says
  why; run `/swd:off` to switch anyway. Under `fable` that is any
  switch away from Fable 5.2, as in 0.9.0. Under `opus` a switch
  between Fable 5.2 and Opus 5.5 is allowed either way, and a switch
  from either to any other model is cancelled with
  `swd: this session stays on Fable 5.2 or Opus 5.5, because the principal of this project runs on them and swd mode is on in this session. To switch anyway, run /swd:off.`
  The hook reads no file
  in your project, so a repository you
  clone cannot lock your model. If it cannot read its input, or
  cannot decide within 3 seconds, it lets the switch through; if it
  cannot start, or cannot finish, within Claude Code's 10-second
  timeout, Claude Code cancels the switch. If a switch is still
  cancelled after `/swd:off` (`/swd:off` says so when it cannot
  delete its flag file, and names the file), delete
  `~/.claude/swd-mode/<session id>` or start a new session with
  `claude --model <name>`; resuming this session keeps swd mode on.
- **The Fable judge.** When the principal conducts on Opus 5.5, it
  asks a Fable 5.2 subagent, the judge (`swd:judge`), for a verdict at
  three points: the plan, before the seal and after each amendment; a
  ruling that touches a trust boundary (permissions, secrets, or input
  that reaches a shell); and a ruling a builder or a checker disputes.
  Its brief holds the question, never the principal's answer; it reads
  the run folder, runs nothing, and writes `reports/judge-<n>.md`. The
  principal records each verdict in `decisions.md` and follows it, or
  records why it overrules it (`Judge overruled:`). When the judge
  cannot be reached (the dispatch fails or is cut off, for example
  because the Fable quota has run out, or it returns no verdict, which
  includes a judge that finds it is not on Fable 5.2), what happens
  depends on whether anyone attends the run. In a run you attend, the
  principal then judges alone, records `Judge unreachable:`, and the
  run goes on. A run `/swd:queue` started on Opus 5.5 stops as blocked
  instead, and its seal accepts the plan only on the judge's verdict
  that the plan holds.
  `check_run.py --seal` refuses to seal a plan conducted on Opus 5.5
  without a `Judge plan:` or `Judge unreachable:` line since the last
  seal; a seal with `plan.md` unchanged since the last one, such as
  after a change to `staffing.md` or `spec.md` alone, needs none. That
  check is a reminder, not proof: it reads only lines the
  principal writes, so it cannot show that the judge was dispatched.
  On Fable 5.2 there is no judge.
- `/swd:queue` starts every run with the model the project's conductor
  setting gives: `--model fable`, or `--model opus` under `opus`, and
  prints it before each run. Under `opus` it starts on Opus 5.5 rather
  than on Fable 5.2 with a fallback, because `--fallback-model` does
  not switch on a rate-limit or usage-limit error. It ignores a
  `Model:` line.
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
  wave, coloured by status, each with the model and effort it is staffed
  at, with the timeline below, and refreshes every two seconds until the
  run is done. Above the tasks it shows the conductor's model (from the
  last `Conductor:` line in `decisions.md`) and the model and effort of
  the reviews and the final check (from `staffing.md`); what a run has no
  record of is left out. You can also build it for any run with
  `python3 scripts/swd-dashboard.py <run folder>` on macOS and Linux,
  with `python` or `py -3` on Windows.
- **In the terminal (macOS and Linux):** if you run Claude Code inside
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

To validate and test (`python3` on macOS and Linux; `python` or `py -3`
on Windows, in Git Bash):

```bash
python3 -m unittest discover -s tests -v
claude plugin validate .
```

GitHub Actions (`.github/workflows/test.yml`) runs the suite on Windows,
macOS and Linux, on Python 3.9 and 3.13, on every push and pull request.
Tests that cannot run on Windows are skipped there with the reason.

Two end-to-end pilots run a real team in a temporary project and grade the
result. They cost tokens, take several minutes each, and run on macOS and
Linux only:

```bash
tests/run_pilot.sh existing-repo   # production mode, sample repo with a planted bug
tests/run_pilot.sh new-project     # prototype mode, built from an empty folder
```

The design is in `docs/superpowers/specs/2026-11-12-swd-agents-design.md`.
