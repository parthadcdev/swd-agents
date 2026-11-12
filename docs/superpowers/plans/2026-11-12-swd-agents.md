# swd-agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Claude Code plugin, `swd`, in which a principal engineer skill runs a team of ten specialist subagents from a requirement to tested, committed code with one approval gate.

**Architecture:** The principal is a skill (`/swd:build`) that runs in the user's session and dispatches plugin subagents with the Agent tool. All coordination goes through a run folder of plain markdown in the target project. One stdlib Python script, `scripts/check_run.py`, validates a plan and a finished run; the principal calls it at the gate and at the end, and the pilots call it to grade a run.

**Tech Stack:** Claude Code plugin (markdown skills and agents), Python 3 standard library only (`unittest`, `re`, `subprocess`, `pathlib`), bash, git.

**Spec:** `docs/superpowers/specs/2026-11-12-swd-agents-design.md`

## Global Constraints

- Plugin name is `swd`. Agents are dispatched as `swd:<agent-name>`.
- No third-party dependencies. Python is stdlib only.
- Agent files, standards files and run-folder files contain no Claude-specific syntax beyond the YAML frontmatter Claude Code requires.
- Run folder location: `.swd/runs/<YYYY-MM-DD>-<short-name>/` in the target project.
- Task status values: `todo`, `in-progress`, `in-review`, `done`, `blocked`.
- Fix loop: three fix attempts on the same failure, then an architect re-plan, then stop and report to the user.
- The team never pushes, merges, or changes the user's main branch. Work happens on `swd/<short-name>`.
- Never relaxed in any mode: tests written first; no completion with a failing test; destructive actions need the user's explicit yes.
- The principal never writes product code. Checkers never edit product code.
- Commit subjects: `T<n>: <title>` for a task commit, `W<n>: <summary>` for a prototype-mode wave commit.

## File Structure

| Path | Responsibility |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `README.md` | What the plugin is, how to load and run it |
| `skills/build/SKILL.md` | The principal engineer's playbook (`/swd:build`) |
| `agents/<role>.md` (ten files) | One specialist each |
| `standards/run-folder.md` | The exact format of every run-folder file and report |
| `standards/production.md`, `standards/prototype.md` | The engineering bar per delivery mode |
| `scripts/check_run.py` | Validates a plan (`--plan`) or a finished run |
| `scripts/swd-watch.sh` | Opens the herdr ledger and activity panes for a run |
| `tests/test_watch.py` | Tests `swd-watch.sh` against a stub `herdr` |
| `tests/test_structure.py` | Plugin files exist and have their required parts |
| `tests/test_check_run.py` | Unit tests for `check_run.py` |
| `tests/pilots/existing-repo/` | Sample repo with a planted bug, requirement, acceptance test |
| `tests/pilots/new-project/` | Requirement and acceptance test for a from-scratch build |
| `tests/run_pilot.sh` | Runs one pilot end to end in a temp folder and grades it |

Agent names: `architect`, `generalist-engineer`, `backend-engineer`, `frontend-engineer`, `database-engineer`, `devops-engineer`, `docs-writer`, `code-reviewer`, `security-reviewer`, `qa-engineer`.

## Review Focus

1. **The target project has uncommitted changes when a run starts.** Expected: the principal stops and asks, and does not carry the user's changes onto the `swd/` branch. Pinned in Task 4.
2. **The architect assigns one file to two tasks in the same wave.** Expected: caught before the gate, not discovered as a mid-wave collision. Pinned in Task 2 (`--plan` mode) and Task 4.
3. **An agent writes a malformed plan task or ledger row.** Expected: `check_run.py` reports the line as a problem and exits 1; it does not crash with a traceback. Pinned in Task 2.
4. **The requirement is a one-line change.** Expected: a one-task, one-wave plan is valid and the run is not staffed with ten roles. Pinned in Task 2 (single-task plan) and Task 7 (staffing rule).
5. **The target project has no test runner.** Expected: the architect's first task sets one up and `plan.md` records the test command. Pinned in Task 2 (`Test command:` required) and Task 3.

---

### Task 1: Plugin skeleton and structure test

**Files:**
- Create: `.claude-plugin/plugin.json`, `README.md`, `.gitignore`, `tests/test_structure.py`

**Interfaces:**
- Produces: `tests/test_structure.py` with module constants later tasks extend:
  - `REQUIRED_AGENTS: list[str]` (starts empty)
  - `AGENT_SECTIONS = ["## Responsibility", "## Inputs", "## Process", "## Report", "## Never"]`
  - `REQUIRED_FILES: list[str]` (starts as `[".claude-plugin/plugin.json", "README.md"]`)
  - helper `frontmatter(path: Path) -> dict[str, str]` parsing the `---` block as `key: value` lines.

- [ ] **Step 1: Write the failing test**

`tests/test_structure.py`, `unittest`, run from the repo root:

```python
def test_required_files_exist(self):          # every path in REQUIRED_FILES exists
def test_manifest(self):                      # plugin.json parses; ["name"] == "swd"; has "description" and "version"
def test_required_agents_exist(self):         # agents/<name>.md exists for each REQUIRED_AGENTS entry
def test_agent_files_well_formed(self):       # for every agents/*.md: frontmatter name == file stem,
                                              # non-empty description, non-empty tools, every AGENT_SECTIONS heading present
def test_no_dangling_agent_references(self):  # every `swd:<name>` found by regex r"swd:([a-z-]+)" in skills/ and standards/
                                              # is "build" or has agents/<name>.md
```

- [ ] **Step 2: Run it to see it fail**

Run: `python3 -m unittest tests.test_structure -v`
Expected: FAIL on `test_required_files_exist` and `test_manifest`.

- [ ] **Step 3: Create the skeleton**

- `plugin.json`: `name` `swd`, `version` `0.1.0`, `description` "A principal engineer agent running a team of specialist software engineering agents, from requirement to tested code."
- `README.md`: what it is, `claude --plugin-dir <path>` to load it, `/swd:build <requirement>` to run it, Python 3 required, link to the spec.
- `.gitignore`: `__pycache__/`.

- [ ] **Step 4: Run tests and the platform validator**

Run: `python3 -m unittest tests.test_structure -v && claude plugin validate .`
Expected: all tests pass; validate exits 0.

- [ ] **Step 5: Commit** — `git commit -m "Add plugin skeleton and structure test"`

---

### Task 2: Run-folder format and `check_run.py`

**Files:**
- Create: `standards/run-folder.md`, `scripts/check_run.py`, `tests/test_check_run.py`
- Modify: `tests/test_structure.py` (add `standards/run-folder.md` and `scripts/check_run.py` to `REQUIRED_FILES`)

**Interfaces:**
- Produces, in `scripts/check_run.py`:
  - `BUILDERS = {"generalist-engineer", "backend-engineer", "frontend-engineer", "database-engineer", "devops-engineer", "docs-writer"}`
  - `STATUSES = {"todo", "in-progress", "in-review", "done", "blocked"}`
  - `parse_plan(text: str) -> tuple[list[dict], list[str]]` — tasks and problems. Task keys: `id` (`"T1"`), `title`, `role`, `wave` (int), `files` (list[str]), `depends` (list[str]), `check` (str).
  - `parse_ledger(text: str) -> tuple[dict[str, dict], list[str]]` — `{id: {"role", "status", "attempts": int}}` and problems.
  - `check_plan(run_dir: Path) -> list[str]`
  - `check_run(run_dir: Path, repo_dir: Path) -> list[str]`
  - `latest_run(repo_dir: Path) -> Path | None` — last by name under `.swd/runs/`.
  - CLI: `python3 scripts/check_run.py [--plan] <repo_dir>`; prints one problem per line; exit 0 when none, 1 otherwise, 1 with `no run folder found` when there is none.

**Formats (`standards/run-folder.md` documents exactly these):**

`spec.md` contains a line `Mode: prototype` or `Mode: production`, and a `## Acceptance criteria` heading.

`plan.md` contains a line ``Test command: `<command>` `` and tasks in this form:

```markdown
### T1: Add total() to cart
- Role: generalist-engineer
- Wave: 1
- Files: shop/cart.py, tests/test_cart.py
- Depends: none
- Check: `python3 -m unittest tests.test_cart`
```

`ledger.md` is a table with header `| Task | Role | Status | Attempts |` and one row per task.

Builder report `reports/T<n>-<role>.md` headings: `## Summary`, `## Files changed`, `## Test first (failing)`, `## Test after (passing)`, `## Complexity`, `## Concerns`.

Checker report headings: `## Findings` and a line `Verdict: pass` or `Verdict: fail`. Names: `reports/T<n>-code-reviewer.md`, `reports/T<n>-security-reviewer.md`, `reports/final-code-reviewer.md`, `reports/final-security-reviewer.md`, `reports/final-qa-engineer.md`.

**Rules `check_plan` enforces:** `spec.md` and `plan.md` exist; `Mode:` line valid; `Test command:` present; at least one task; every task has all five fields; ids unique; `Role` is a known agent name; every `Depends` id exists and is in an earlier wave; no file appears in two tasks of the same wave.

`activity.md` is a list of lines `- <HH:MM:SS> <event> <detail>` where `<event>` is one of `dispatch`, `return`, `verdict`, `commit`, `fix`, `replan`, `ruling`, `wave-done`, `blocked`, `done`.

**Rules `check_run` adds:** `requirement.md`, `standards.md`, `ledger.md`, `decisions.md`, `activity.md` exist; `activity.md` has at least one `dispatch` line per plan task and ends with a `done` line; every plan task has a ledger row with status `done`; every builder task has its report with all six headings, and the two test sections are non-empty; `reports/final-qa-engineer.md` exists with `Verdict: pass`; production mode: every builder task has `reports/T<n>-code-reviewer.md` with `Verdict: pass`; prototype mode: `reports/final-code-reviewer.md` exists with `Verdict: pass` and there are no `T<n>-code-reviewer.md` files; for each commit on the current branch whose subject starts `T<n>:` every changed path is in that task's `Files` or under `.swd/`; for `W<n>:` every changed path is in some wave-`n` task's `Files` or under `.swd/`. Commits come from `git log --name-only --format=%x00%s` run in `repo_dir`.

- [ ] **Step 1: Write the failing tests**

`tests/test_check_run.py` builds run folders in `tempfile.TemporaryDirectory()` with a helper `make_run(tmp, mode="production", **overrides) -> tuple[Path, Path]` that writes a valid two-task, two-wave run, runs `git init`, and makes one `T<n>:` commit per task. Tests:

```python
def test_valid_production_run_has_no_problems(self)
def test_valid_prototype_run_has_no_problems(self)        # W1:/W2: commits, final-code-reviewer only
def test_single_task_plan_is_valid(self)                  # Review Focus 4
def test_same_wave_shared_file_is_reported(self)          # Review Focus 2; problem mentions both task ids and the path
def test_dependency_in_same_or_later_wave_is_reported(self)
def test_missing_test_command_is_reported(self)           # Review Focus 5
def test_malformed_task_is_reported_not_raised(self)      # Review Focus 3; task missing "- Files:"
def test_malformed_ledger_row_is_reported_not_raised(self)# Review Focus 3; status "finished", attempts "x"
def test_task_not_done_is_reported(self)
def test_missing_fail_then_pass_evidence_is_reported(self)# empty "## Test first (failing)" section
def test_commit_outside_owned_files_is_reported(self)
def test_missing_task_review_in_production_is_reported(self)
def test_per_task_review_in_prototype_is_reported(self)
def test_failing_qa_verdict_is_reported(self)
def test_missing_dispatch_in_activity_is_reported(self)
def test_cli_exit_codes(self)                             # 0 valid, 1 invalid, 1 and "no run folder found" for an empty dir
def test_cli_plan_mode_ignores_missing_ledger(self)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m unittest tests.test_check_run -v`
Expected: FAIL, `No module named scripts.check_run` (add empty `scripts/__init__.py` and `tests/__init__.py` only if imports need them).

- [ ] **Step 3: Implement `scripts/check_run.py`** to the interfaces and rules above. Parsing is line-based with `re`; a line that does not match adds a problem string naming the file and line number. No exceptions escape `main()` for bad input.

- [ ] **Step 4: Write `standards/run-folder.md`** with the formats above, one filled-in example of each file, and the table of who writes which file from the spec.

- [ ] **Step 5: Run all tests**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS.

- [ ] **Step 6: Commit** — `git commit -m "Add run-folder format and run checker"`

---

### Task 3: Production standard and the core team

**Files:**
- Create: `standards/production.md`, `agents/architect.md`, `agents/generalist-engineer.md`, `agents/code-reviewer.md`, `agents/qa-engineer.md`
- Modify: `tests/test_structure.py`

**Interfaces:**
- Consumes: formats in `standards/run-folder.md`; `AGENT_SECTIONS` from Task 1.
- Produces: `STANDARD_SECTIONS = ["## Priority", "## Builder process", "## Testing", "## Review", "## Security", "## Performance", "## Docs", "## Commits"]` in `tests/test_structure.py`; the four agents dispatchable as `swd:architect`, `swd:generalist-engineer`, `swd:code-reviewer`, `swd:qa-engineer`.

- [ ] **Step 1: Extend the test first**

Add the four names to `REQUIRED_AGENTS`, `standards/production.md` to `REQUIRED_FILES`, and:

```python
def test_standards_have_required_sections(self):  # every standards/{production,prototype}.md that exists has all STANDARD_SECTIONS
def test_checkers_cannot_edit(self):              # frontmatter tools of code-reviewer, security-reviewer, qa-engineer (those that exist) do not include "Edit"
```

- [ ] **Step 2: Run to see it fail** — `python3 -m unittest tests.test_structure -v`; expected FAIL on missing agent files.

- [ ] **Step 3: Write `standards/production.md`**

Content per section, taken from the spec's production column:
- Priority: quality over speed.
- Builder process: write the test, run it and paste the failing output, write the code, run it and paste the passing output; work with no unit test gets a check written first; touch only owned files; if the plan is missing or wrong, stop and say what is needed under `## Concerns`.
- Testing: tests cover the core path, edge cases and failure paths; during a wave run only your own tests.
- Review: every task reviewed before commit.
- Security: full pass on every run.
- Performance: meet the plan's complexity target; state time and space complexity of non-trivial logic under `## Complexity`; the four rejected patterns from the spec; measure hot paths; no readability-costing micro-optimisation.
- Docs: usage docs and changelog.
- Commits: one per task, subject `T<n>: <title>`, made by the principal after the task passes review.

- [ ] **Step 4: Write the four agent files**

Frontmatter: `name`, `description` (one sentence saying when the principal dispatches it), `tools`. No `model` key, so the principal chooses per dispatch.

| Agent | tools | Process must state |
|---|---|---|
| `architect` | Read, Glob, Grep, Bash, Write | Read `requirement.md`, `spec.md`, `standards.md` and the repo's own conventions; find or choose the test command and record it as `Test command:`; if there is no test runner, make setting one up task `T1` alone in wave 1; write contracts between tasks into `plan.md` before the task list; state expected data sizes and a complexity target for any part handling data at scale (production mode); group tasks into waves so no two tasks in a wave share a file; write only `plan.md`. On a re-plan dispatch: read the failing reports, diagnose the root cause, amend `plan.md`, and say whether the amendment changes the approved spec. |
| `generalist-engineer` | Read, Write, Edit, Glob, Grep, Bash | Read the brief, the task in `plan.md`, and `standards.md`; follow `## Builder process` there; write the report at `reports/T<n>-generalist-engineer.md` in the builder format. |
| `code-reviewer` | Read, Glob, Grep, Bash, Write | Review the named task (or the whole branch diff for `final`) against the spec, the plan's contracts and `standards.md`; reject a builder report without both test outputs; reject the performance patterns the standard lists; write only its report with `Verdict:` and `## Findings`, each finding with file, line and what to change. |
| `qa-engineer` | Read, Glob, Grep, Bash, Write | Run the plan's test command plus the repo's lint, type check and build where they exist; for `final`, exercise every acceptance criterion in `spec.md` against the real running software and record the command and output for each; write only its report. |

Every agent's `## Never` section: never push or merge; never run a destructive action; never write the ledger; never edit a file outside its owned files (checkers: never edit product code).

- [ ] **Step 5: Run tests and validate** — `python3 -m unittest discover -s tests -v && claude plugin validate .`; expected PASS, exit 0.

- [ ] **Step 6: Commit** — `git commit -m "Add production standard and core team agents"`

---

### Task 4: The principal engineer skill

**Files:**
- Create: `skills/build/SKILL.md`, `scripts/swd-watch.sh`, `tests/test_watch.py`
- Modify: `tests/test_structure.py`

**Interfaces:**
- Consumes: `swd:architect`, `swd:generalist-engineer`, `swd:code-reviewer`, `swd:qa-engineer`; `scripts/check_run.py` CLI; `standards/production.md`, `standards/run-folder.md`.
- Produces: `/swd:build <requirement>`; `scripts/swd-watch.sh <run_dir>` (exit 0 always).

- [ ] **Step 1: Extend the test first**

Add `skills/build/SKILL.md` to `REQUIRED_FILES`, and:

```python
PRINCIPAL_SECTIONS = ["## Preflight", "## Intake", "## Delivery mode", "## Design", "## Gate", "## Build",
                      "## Fix loop", "## Final verification", "## Report", "## Resume", "## Never"]
def test_principal_sections(self):          # all present, in this order
def test_principal_frontmatter(self):       # name == "build", non-empty description
def test_principal_pins_review_focus(self): # text contains "uncommitted" and "check_run.py --plan"
def test_principal_watch_and_activity(self): # text contains "activity.md", "swd-watch.sh" and "HERDR_PANE_ID"
```

`tests/test_watch.py` puts a stub `herdr` on `PATH` (a shell script that appends its arguments to a log file and prints `{"result":{"pane":{"pane_id":"p2"}}}`):

```python
def test_outside_herdr_prints_fallback(self):  # HERDR_PANE_ID unset: exit 0, stdout contains "ledger.md" and "tail -f", stub never called
def test_inside_herdr_opens_two_panes(self):   # HERDR_PANE_ID=p1: log has two "pane split" calls (first with --current --direction right,
                                               # second with p2 --direction down) and two "pane run" calls, one mentioning ledger.md, one activity.md
def test_herdr_failure_is_not_fatal(self):     # stub exits 1: script still exits 0
```

- [ ] **Step 2: Run to see it fail** — `python3 -m unittest tests.test_structure -v`; expected FAIL.

- [ ] **Step 3: Write `skills/build/SKILL.md`**

Each section states these decisions:

- **Preflight.** The plugin root is two directories above this skill's base directory. If the project has an unfinished run (a ledger with any task not `done`), go to Resume. If the project is a git repo with uncommitted changes, stop and ask the user. If the folder is empty or not a repo, `git init`. Create branch `swd/<short-name>`.
- **Intake.** Ask clarifying questions one at a time, only those that change what gets built. Write `requirement.md` (verbatim plus answers) and `spec.md` (what will be built, `## Acceptance criteria`, assumptions).
- **Delivery mode.** In this task: write `Mode: production` and say why. (Task 6 adds prototype.) Write the run's `standards.md` by concatenating `<plugin root>/standards/<mode>.md` and `<plugin root>/standards/run-folder.md`.
- **Design.** Dispatch `swd:architect` with the run-folder path. Then run `python3 <plugin root>/scripts/check_run.py --plan <project>`; if it reports problems, send them back to the architect and repeat.
- **Gate.** Show the user the spec and plan summary and wait for approval. If the user's original message explicitly pre-approved, record that in `decisions.md` and continue. This is the only planned stop.
- **Build.** Write `ledger.md` with every task `todo` and create `activity.md`. If `HERDR_PANE_ID` is set, run `<plugin root>/scripts/swd-watch.sh <run folder>` once. Append one line to `activity.md` for every dispatch, return, verdict, commit, fix, re-plan, ruling, finished wave and blocker, and a final `done` line. For each wave: dispatch all its tasks in one message so they run in parallel; each brief names the task id, the run-folder path, the owned files, and earlier reports to read. When a task returns, verify with `git status` that only its owned files changed, set it `in-review`, dispatch its review. On `Verdict: pass`, commit `T<n>: <title>` and set `done`. When the wave is done, dispatch `swd:qa-engineer` for a full-suite run before the next wave. Only the principal writes the ledger.
- **Fix loop.** Any failure becomes a fix dispatch to the builder that owns the code, naming the failing report; increment `Attempts`; re-check. At three attempts on the same failure dispatch `swd:architect` to re-plan; if the re-planned work fails, stop and report with the evidence. A missing or unusable report: re-dispatch once, then count it as an attempt. Out-of-scope edits: reject and send back to undo them. A plan amendment that changes the approved spec goes back to the user. Record every ruling in `decisions.md`.
- **Final verification.** Dispatch `swd:qa-engineer` and `swd:code-reviewer` for `final` as the standard requires. Then run `python3 <plugin root>/scripts/check_run.py <project>` and fix whatever it reports.
- **Report.** What was built, the branch name, test evidence, and the contents of `decisions.md`.
- **Resume.** Read the ledger; treat `in-progress` and `in-review` tasks as `todo` after checking `git status` for half-finished edits in their owned files; continue from the first unfinished wave.
- **Never.** Never write product code. Never push, merge or touch the main branch. Never run a destructive action (deleting data, dropping tables, force-pushing, migrating a non-local database) without the user's explicit yes. Never finish with a failing test. Stop and ask on a true blocker (missing credentials, external service down).

- [ ] **Step 4: Write `scripts/swd-watch.sh <run_dir>`**

Bash, executable. Without `HERDR_PANE_ID`: print the two commands below and exit 0. With it: `herdr pane split --current --direction right --no-focus`, read the new pane id from `.result.pane.pane_id` with `python3 -c`, `herdr pane rename <id> "swd ledger"`, `herdr pane run <id> "while :; do clear; cat <run_dir>/ledger.md; sleep 2; done"`; then `herdr pane split <id> --direction down --no-focus`, rename it `swd activity`, and `herdr pane run <id2> "tail -f <run_dir>/activity.md"`. Any herdr failure prints a one-line warning and exits 0, so a run never fails because of the dashboard.

- [ ] **Step 5: Run tests and validate** — `python3 -m unittest discover -s tests -v && claude plugin validate .`; expected PASS, exit 0.

- [ ] **Step 6: Commit** — `git commit -m "Add principal engineer skill and herdr watch panes"`

---

### Task 5: Existing-repo pilot (production mode)

**Files:**
- Create: `tests/pilots/existing-repo/repo/shop/__init__.py`, `tests/pilots/existing-repo/repo/shop/cart.py`, `tests/pilots/existing-repo/repo/tests/__init__.py`, `tests/pilots/existing-repo/repo/tests/test_cart.py`, `tests/pilots/existing-repo/repo/README.md`, `tests/pilots/existing-repo/requirement.txt`, `tests/pilots/existing-repo/acceptance.py`, `tests/run_pilot.sh`

**Interfaces:**
- Consumes: `/swd:build`, `scripts/check_run.py`.
- Produces: `tests/run_pilot.sh <pilot-name>` — exit 0 when the pilot passes. Prints the temp project path.

- [ ] **Step 1: Write the fixture repo**

`shop/cart.py`:
- `subtotal(items: list[tuple[float, int]]) -> float` — sum of price × quantity. Correct.
- `apply_discount(amount: float, percent: float) -> float` — **planted bug:** returns `amount - percent`.

`tests/test_cart.py` tests `subtotal` only, and passes. `README.md` says tests run with `python3 -m unittest`.

- [ ] **Step 2: Write the requirement and acceptance test**

`requirement.txt`: "Add `total(items, discount_percent=0, tax_percent=0)` to `shop/cart.py`. It returns the subtotal with the discount applied, then tax added, rounded to 2 decimals. This is production code. I pre-approve the spec and plan; do not wait for me."

`acceptance.py` (run from the project root, exit 1 on any failure):

```python
assert apply_discount(200, 10) == 180            # the planted bug is fixed
assert total([(100, 2)]) == 200
assert total([(100, 2)], discount_percent=10) == 180
assert total([(100, 2)], discount_percent=10, tax_percent=5) == 189
assert total([]) == 0
```

- [ ] **Step 3: Run the acceptance test against the untouched fixture to see it fail**

Run: `cd tests/pilots/existing-repo/repo && python3 ../acceptance.py`
Expected: FAIL (`total` does not exist).

- [ ] **Step 4: Write `tests/run_pilot.sh`**

Given `<pilot-name>`: make a temp dir; copy `tests/pilots/<pilot-name>/repo/` into it if present; `git init` and commit when files were copied; run

```bash
claude -p --plugin-dir "$ROOT" \
  --allowedTools "Read Write Edit Glob Grep Agent Skill Bash(git *) Bash(python3 *)" \
  "Use the swd:build skill for this requirement: $(cat "$PILOT/requirement.txt")"
```

from the temp dir; then run `python3 "$ROOT/scripts/check_run.py" "$TMP"` and `python3 "$PILOT/acceptance.py"` from the temp dir. Exit non-zero if either fails. `set -euo pipefail`.

- [ ] **Step 5: Run the pilot**

Run: `tests/run_pilot.sh existing-repo`
Expected: exit 0; `check_run.py` prints nothing; `acceptance.py` exits 0.

- [ ] **Step 6: Fix the prompts until it passes**

For each problem the pilot shows, change the skill, agent or standard that caused it (not the checker, unless the checker is wrong), re-run the unit tests, and re-run the pilot. Record in the commit message what each change fixed. If `claude -p` cannot invoke the skill or dispatch plugin agents with this tool allowlist, adjust the allowlist in `run_pilot.sh` and note it in `README.md`.

- [ ] **Step 7: Commit** — `git commit -m "Add existing-repo pilot and fixes it surfaced"`

---

### Task 6: Prototype mode and model selection

**Files:**
- Create: `standards/prototype.md`, `tests/pilots/new-project/requirement.txt`, `tests/pilots/new-project/acceptance.py`
- Modify: `skills/build/SKILL.md` (Delivery mode, Build, Final verification), `tests/test_structure.py`

**Interfaces:**
- Consumes: `STANDARD_SECTIONS`; `check_run.py` prototype rules from Task 2.

- [ ] **Step 1: Extend the tests first**

Add `standards/prototype.md` to `REQUIRED_FILES`, and:

```python
def test_principal_covers_both_modes(self):   # SKILL.md contains "Mode: prototype", "Mode: production", "W<n>:" and "model"
```

Write `tests/pilots/new-project/requirement.txt`: "Build a quick prototype command-line tool in Python. `python3 wc_lite.py <file>` prints `<lines> <words> <bytes> <file>` on one line, like `wc`. A missing file prints an error to stderr and exits 1. This is a prototype; favour speed. I pre-approve the spec and plan; do not wait for me."

Write `acceptance.py`: creates `sample.txt` containing `"one two\nthree four five\n"`; asserts `python3 wc_lite.py sample.txt` prints `2 5 24 sample.txt` and exits 0; asserts `python3 wc_lite.py nope.txt` exits 1 with non-empty stderr.

- [ ] **Step 2: Run to see it fail** — `python3 -m unittest tests.test_structure -v`; expected FAIL.

- [ ] **Step 3: Write `standards/prototype.md`** with the same eight sections, content from the spec's prototype column: fastest working outcome; tests first but only for the acceptance criteria and core path; one code review of the whole change at the end; security review only when the change touches auth, secrets, user input or payments; avoid plainly wrong performance choices, no complexity targets; short README; one commit per wave, subject `W<n>: <summary>`, after the wave's own tests pass; full suite once at the end.

- [ ] **Step 4: Update `skills/build/SKILL.md`**

- **Delivery mode:** choose `prototype` when the requirement says prototype, MVP, proof of concept, demo, spike or quick, or the project is an empty folder with a small requirement; choose `production` for an existing repo with users, or when the requirement says production; when unsure choose `production`. State the mode and reasoning in `spec.md`; the user can change it at the gate. Raise the bar for a single task that carries real risk (money, auth, data migration) and record it in `decisions.md`.
- **Staffing:** dispatch only roles the plan names. In prototype mode ask the architect for the fewest tasks and roles that can deliver.
- **Model per dispatch** (the Agent tool's `model` parameter): prototype — `haiku` for builders and QA, `sonnet` for architect and review. Production — the session's model for architect and review, `sonnet` for builders and QA. Escalate a task one tier after a failed fix attempt.
- **Build / Final verification:** follow the run's `standards.md` for when to review, when to run the full suite and how to commit; in prototype mode the code review is `reports/final-code-reviewer.md` only.

- [ ] **Step 5: Run unit tests, then the pilot**

Run: `python3 -m unittest discover -s tests -v && tests/run_pilot.sh new-project`
Expected: tests PASS; pilot exits 0; the temp project's `spec.md` says `Mode: prototype`.

- [ ] **Step 6: Fix prompts until the pilot passes**, as in Task 5 Step 6. Then re-run `tests/run_pilot.sh existing-repo` to confirm production mode still passes.

- [ ] **Step 7: Commit** — `git commit -m "Add prototype mode and per-dispatch model selection"`

---

### Task 7: The remaining specialists

**Files:**
- Create: `agents/backend-engineer.md`, `agents/frontend-engineer.md`, `agents/database-engineer.md`, `agents/devops-engineer.md`, `agents/docs-writer.md`, `agents/security-reviewer.md`
- Modify: `skills/build/SKILL.md` (Delivery mode staffing, Build), `agents/architect.md`, `tests/test_structure.py`, `README.md`

**Interfaces:**
- Consumes: `## Builder process` in the standards; checker report format.

- [ ] **Step 1: Extend the test first** — add the six names to `REQUIRED_AGENTS`; add:

```python
def test_roster_matches_checker(self):   # {stems of agents/*.md} - {"architect","code-reviewer","security-reviewer","qa-engineer"} == check_run.BUILDERS
```

- [ ] **Step 2: Run to see it fail** — `python3 -m unittest tests.test_structure -v`; expected FAIL.

- [ ] **Step 3: Write the six agent files**

The five builders have tools `Read, Write, Edit, Glob, Grep, Bash`, follow `## Builder process` in `standards.md`, and add only what is specific to the specialty:

| Agent | Specialty guidance in `## Process` |
|---|---|
| `backend-engineer` | Build to the API contract in `plan.md` exactly; validate input at the boundary; no query inside a loop. |
| `frontend-engineer` | Build to the API contract; follow the repo's existing components and styling; keyboard and screen-reader access; test behaviour, not markup. |
| `database-engineer` | Every schema change is a migration with a tested rollback; index what the plan's queries filter on; run migrations only against a local or test database. |
| `devops-engineer` | The check written first is running the config (lint, dry-run or a local build); never deploy; never put a secret in a file. |
| `docs-writer` | The check written first is running every command the docs show; document only what exists in the branch. |

`security-reviewer`: tools `Read, Glob, Grep, Bash, Write`; reviews the task or the whole branch for input validation, auth and authorisation, secrets in code or logs, injection, unsafe dependencies and data exposure; checker report format; each finding has severity, file, line and the fix.

- [ ] **Step 4: Update the architect and the principal**

- `agents/architect.md`: a table of the six builder roles and when to assign each; assign `generalist-engineer` when none fits; do not create a task for a role the requirement does not need.
- `skills/build/SKILL.md`: review dispatches send `swd:code-reviewer` and `swd:security-reviewer` in one message so they run in parallel; `swd:security-reviewer` runs per task and at `final` in production mode, and in prototype mode only at `final` and only when the change touches a trust boundary; a one-task plan is normal and gets one builder.
- `README.md`: the roster table.

- [ ] **Step 5: Run everything**

Run: `python3 -m unittest discover -s tests -v && claude plugin validate . && tests/run_pilot.sh existing-repo && tests/run_pilot.sh new-project`
Expected: all pass, both pilots exit 0.

- [ ] **Step 6: Commit** — `git commit -m "Add remaining specialist agents"`
