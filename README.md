# swd-agents

A Claude Code plugin. A principal software engineer agent takes a requirement,
gets one approval from you on the spec and plan, then runs a team of
specialist agents until the work is built, tested and committed on a branch.

## Requirements

- Claude Code
- Python 3 (standard library only), for the run checker
- git

## Use

Load the plugin for a session:

```bash
claude --plugin-dir /path/to/swd-agents
```

Then, in the project you want work done in:

```
/swd:build <your requirement>
```

## The team

| Role | Kind | Does |
|---|---|---|
| Principal engineer (`/swd:build`) | Coordinates | Clarifies, plans, staffs, dispatches, routes fixes, decides |
| Architect | Designs | Design, contracts and the task list |
| Backend engineer | Builds | APIs, services, business logic |
| Frontend engineer | Builds | Pages, components, client-side logic |
| Database engineer | Builds | Schemas, migrations, queries |
| DevOps engineer | Builds | CI, build scripts, containers, deploy config |
| Generalist engineer | Builds | CLIs, libraries, scripts, small mixed changes |
| Docs writer | Builds | README, usage docs, changelog |
| Code reviewer | Checks | Correctness, quality, performance |
| Security reviewer | Checks | Security of the change |
| QA engineer | Checks | Full test suite and the acceptance criteria |

Builders work test first and own the files the plan gives them. Checkers
report findings and never edit code. A run uses only the roles its plan
needs.

## Modes

The principal picks a delivery mode from your requirement and you can change
it at the approval gate.

- **Prototype / MVP:** fastest working result, fewest tokens, one review at
  the end.
- **Production:** every task reviewed for quality and security, full suite
  after every wave.

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
  showing the ledger and the timeline.

## Develop

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
