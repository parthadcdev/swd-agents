# swd-agents: design spec

Date: 2026-11-12
Status: awaiting review

## Purpose

A Claude Code plugin that takes a software requirement and delivers working,
tested code with one human approval along the way. A principal software
engineer agent runs a team of specialist agents from the initial requirement
through to completion.

## What was asked for

- One principal engineer agent controlling multiple specialist agents that
  coordinate from requirement to completion.
- Fully automated, with a single approval gate before building starts.
- Built on Claude now; extendable to other AI providers later.
- Handles new projects and existing repos, in any stack.
- A full department of specialists.
- Test-driven development always; full testing; errors fixed automatically
  until resolved; parallel execution wherever possible.
- Strong performance discipline (algorithmic complexity).
- The principal judges the required outcome: prototype or MVP work favours
  speed and low token use with light review; production work favours quality.

## Assumptions

- "Completion" means working, tested code committed on a branch, then
  delivered the way the user chose at the gate (merged and pushed, in a pull
  request, or left on the branch). It does not include deployment.
- One user, running the plugin from their own Claude Code session.
- Support for other AI providers is a design constraint in this version, not
  something built in it.

## Out of scope for this version

- Running outside Claude Code (standalone app, CI service).
- Adapters for other AI providers.
- Direct agent-to-agent messaging. All coordination goes through the
  principal and the run folder.
- A separate git worktree per builder.

## Structure

The repo is a Claude Code plugin named `swd`.

| Part | What it is |
|---|---|
| `/swd:build <requirement>` | The principal engineer's playbook. Running it makes the user's session the principal. |
| Agent files | One markdown file per specialist: responsibility, inputs, required output, permitted tools. |
| Standards files | The engineering bar for each delivery mode (see Delivery modes). |
| Run folder format | Where a run's spec, plan, ledger and reports live in the target project. |

Agent files, standards files and the run folder are plain markdown with no
Claude-specific syntax beyond the frontmatter Claude Code requires. They are
the part that ports to another AI tool. The command is the Claude-specific
layer.

## Roles

### Principal engineer

- Clarifies the requirement and owns the approval gate.
- Chooses the delivery mode and staffs the run with only the roles it needs.
- Chooses the model for each dispatch: a cheaper model for mechanical tasks,
  the most capable for design and difficult review.
- Dispatches tasks, in parallel when they own different files.
- Reads every report, routes fixes, settles disagreements, records rulings.
- Never writes product code.

### Specialists

| Role | Kind | Does |
|---|---|---|
| Architect | Designs | Reads the repo, writes the design, contracts and task list |
| Backend engineer | Builds | Server-side code and its tests |
| Frontend engineer | Builds | UI code and its tests |
| Database engineer | Builds | Schemas, migrations, queries |
| DevOps engineer | Builds | CI, build scripts, container and deploy config |
| Generalist engineer | Builds | Work that fits no specialty: CLIs, libraries, scripts |
| Docs writer | Builds | README, usage docs, changelog |
| Code reviewer | Checks | Correctness, quality and performance of finished tasks |
| Security reviewer | Checks | Security of the change |
| QA engineer | Checks | Runs the tests; verifies the acceptance criteria are met |

Rules:

- Builders own files. The plan assigns each task a set of files; no two
  tasks running at the same time share a file.
- Checkers do not edit. They report findings to the principal, who sends the
  fix to the builder that owns the code.

## Run folder

Location: `.swd/runs/<YYYY-MM-DD>-<short-name>/` in the target project.
Whether it is committed or gitignored is left to each project.

| File | Written by | Holds |
|---|---|---|
| `requirement.md` | Principal | The requirement verbatim, plus the user's answers to clarifying questions |
| `spec.md` | Principal | What will be built, acceptance criteria, assumptions, delivery mode and why |
| `standards.md` | Principal | The engineering bar for this run, taken from the plugin's standards file for the chosen mode, plus any per-run adjustments |
| `plan.md` | Architect | Design, contracts between parts, expected data sizes and complexity targets, task list in waves |
| `ledger.md` | Principal only | One line per task: status, role, attempt count |
| `reports/<task>-<role>.md` | The agent that did the work | What it did, files changed, commands run with output, open concerns |
| `decisions.md` | Principal | Every ruling and assumption made after the gate |
| `activity.md` | Principal | A timeline: one line per dispatch, result, verdict, commit, fix and ruling |

Each task in `plan.md` has: an id, the role, the files it owns, the tasks it
depends on, and the check that proves it is done.

Task status values: `todo`, `in-progress`, `in-review`, `done`, `blocked`.

### Coordination

- A dispatch brief names the task id, the paths to `spec.md`, `plan.md` and
  `standards.md`, the files the agent owns, and which earlier reports to read.
- Contracts between specialists (API shapes, schemas) are written into
  `plan.md` before either side starts.
- An agent that finds the plan missing or wrong stops and states what it
  needs in its report. The principal rules, records it, and re-dispatches.
- An agent writes only its owned files and its own report. Only the
  principal writes the ledger.
- An interrupted run resumes from the ledger: running `/swd:build` in a
  project with an unfinished run offers to continue it.

## Delivery modes

The principal chooses a mode at intake from the wording of the requirement
and the state of the repo, states it and its reasoning in `spec.md`, and the
user can change it at the gate.

| | Prototype / MVP | Production |
|---|---|---|
| Priority | Fastest working outcome, lowest token use | Quality over speed |
| Staffing | Fewest roles that can deliver; often architect, one or two builders, QA | Every role the plan calls for |
| Models | Cheaper models wherever the task allows | Most capable model for design and review |
| TDD | Yes; tests cover the acceptance criteria and core path | Yes; tests also cover edge cases and failure paths |
| Code review | One review of the whole change at the end | Every task reviewed before commit |
| Security review | Only where the change touches a trust boundary: auth, secrets, user input, payments | Full pass on every run |
| Full-suite runs | Once, at the end | After every wave and at the end |
| Performance | Avoid plainly wrong choices; no complexity targets | Complexity targets set in the plan and enforced in review |
| Docs | Short README: what it is, how to run it | Usage docs and changelog |

The mode is a starting point, not a fixed setting. The principal raises the
bar for a single task when the task carries real risk, such as money, auth
or a data migration inside a prototype, and records the call in
`decisions.md`.

Never relaxed in any mode: tests are written first; the run does not
complete with a failing test; destructive actions need the user's yes.

## Workflow

1. **Intake.** The principal asks clarifying questions, picks the mode, and
   writes `requirement.md`, `spec.md` and `standards.md`.
2. **Design.** The architect reads the repo and writes `plan.md`.
3. **Gate.** The user approves the spec and plan. The only planned stop.
4. **Build.** The principal runs the plan wave by wave.
5. **Final verification.** QA runs the full suite, lint, type check and
   build, and exercises each acceptance criterion against the real running
   software. Security review runs as the mode requires.
6. **Report.** What was built, the test evidence, and `decisions.md`.

### Test-driven development

- Every builder task: write the test, run it and see it fail, write the
  code, run it and see it pass.
- The report includes both outputs. A task without them is rejected.
- Work with no meaningful unit test gets a check written first: CI config is
  validated by running it, docs by running the commands they show.

### Fix loop

- Any failure from a test, reviewer, security or QA becomes a fix task for
  the builder that owns the code, and the fix is re-checked.
- The loop repeats until everything passes.
- If the same failure survives three fix attempts, the architect diagnoses
  the root cause and re-plans that part.
- If the re-plan also fails, the principal stops and reports to the user
  with the evidence.

### Parallel execution

- All tasks in a wave run at the same time.
- Code review and security review of a task run at the same time.
- Fix tasks for unrelated failures run at the same time.
- Full-suite runs are not concurrent, because agents share one working copy.
  During a wave a builder runs only its own tests.

### Performance standard (production mode)

- The architect states expected data sizes and a complexity target for any
  part that handles data at scale.
- Builders choose the algorithm and data structure that meet the target and
  state the time and space complexity of non-trivial logic in their report.
- The reviewer rejects avoidable inefficiency: a nested loop where a hash
  lookup works, a query inside a loop, repeated recomputation, loading a
  whole table to use one row.
- Hot paths are measured, not guessed. Micro-optimisation that makes code
  harder to read is not wanted.

### Git

- Work happens on a branch `swd/<short-name>`, checked out in its own
  worktree at `.swd/worktrees/<short-name>/`. The user's working copy stays
  on its branch and is never changed. A new project gets `git init` first.
- A task is committed when it passes its checks (per task in production
  mode; per wave in prototype mode).
- At the approval gate the user chooses the finish, recorded in
  `decisions.md`: `merge-push` (fast-forward the base branch, push it,
  delete the run's branch), `pr` (push the run's branch and open a pull
  request) or `branch` (leave the branch, push nothing). Pre-approval
  without a choice means `branch`.
- After the run passes, the principal carries out the finish, removes the
  worktree, and `check_run.py --finish` confirms it.
- The team never force-pushes, never deletes an unmerged branch, and never
  merges or pushes other than as the chosen finish says. A merge conflict or
  a rejected push stops the run and goes to the user.

## Watching a run

The principal appends one line to `activity.md` for every event, in the form
`- <HH:MM:SS> <event> <detail>`. Events: `dispatch`, `return`, `verdict`,
`commit`, `fix`, `replan`, `ruling`, `wave-done`, `blocked`, `done`.

When the principal's session is running inside herdr (the `HERDR_PANE_ID`
environment variable is set), it runs `scripts/swd-watch.sh` once the ledger
exists. The script splits the principal's pane and opens two more: one
showing `ledger.md` refreshed every two seconds, one following
`activity.md`. Outside herdr the script prints the two commands so they can
be run in any terminal. herdr is optional; the plugin works without it.

The principal also starts `scripts/swd-dashboard.py --watch --open` in the
background when the build begins. It writes `dashboard.html` in the run
folder and opens it in the browser: tasks in columns by wave, coloured by
status, with the timeline below. The script rebuilds the page every two
seconds from `plan.md`, `ledger.md` and `activity.md` and stops when the
timeline's last event is `done`, so the view costs no agent work.

Specialists are subagents inside the principal's session and do not get
panes of their own. Running each specialist as its own process in a herdr
pane is a possible later change, tied to supporting other AI providers.

## Failure handling

| Situation | What the principal does |
|---|---|
| An agent returns no report, or an unusable one | Re-dispatches once; a second failure counts as a fix attempt |
| A builder edits files it does not own | Rejects the task and sends it back to undo those edits |
| The plan is wrong mid-run | The architect amends it and the ruling is recorded; if the change alters the approved spec, it goes back to the user |
| A true blocker: missing credentials, external service down | Stops and asks the user |
| A destructive action: deleting data, dropping tables, force-pushing, migrating a non-local database | Never done without the user's explicit yes |
| The session is interrupted | Resumes from the ledger |

## Testing the plugin

- **Structure check (automated).** A script confirms every agent file has
  its required sections and the command refers only to agents that exist.
- **Pilot runs (end to end).** Two fixed sample requirements, run when the
  prompts change:
  - a small new project built from an empty folder, in prototype mode;
  - a feature added to a small sample repo containing a planted bug, in
    production mode.
- A pilot passes when all tests pass, every builder report shows the
  fail-then-pass evidence, the ledger shows every task done, no agent edited
  outside its files, the planted bug is caught, and the prototype pilot used
  the light path (one end review, reduced staffing).

## Build order

1. Thin slice: the command, architect, generalist engineer, code reviewer,
   QA, the run folder, production mode. Proven on the existing-repo pilot.
2. Prototype mode and model selection. Proven on the new-project pilot.
3. The remaining specialists: backend, frontend, database, DevOps, security,
   docs.

## Extending to other AI providers

Not built in this version. The design keeps it cheap later: role files,
standards files and the run folder carry no Claude-specific content, so a
port means writing a new command layer for the other tool and reusing the
rest.
