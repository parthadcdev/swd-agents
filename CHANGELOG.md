# Changelog

## 0.12.0

- Builders start on Sonnet: a builder's first attempt is on `sonnet`,
  at the effort the principal chooses (`haiku` stays for mechanical,
  fully specified work such as the preflight write check). Builders are
  the five engineer roles and the docs writer. Before 0.12.0 every
  design, review and build dispatch started from Opus 5.5.
- The first failed check of a task's work moves the task to `opus`
  before its fix is dispatched, keeping its effort, and raises the
  `review` and `final` rows to at least `opus` in the same edit; the
  principal records the ruling and seals again. A failed check is a
  reviewer's `Verdict: fail`, the task's own tests failing where the
  mode has no per-task review, a failed run of the test suite for a
  wave or for the final check that the task owns, or a failed final QA
  or final review that the task owns. A re-dispatch for a missing or
  unusable report, a report sent back for correction, and a dispatch
  the permission system refused do not move the model. A task already
  on `opus` that fails again follows the old rule: raise the effort
  first. A task a re-plan adds in place of a failed one starts on the
  model the failed task had reached.
- The architect, the code and security reviewers and QA still start
  from Opus 5.5 at `medium`, and no checker runs below a builder.
- This is the project owner's rule, set on 2026-11-17 to lower what
  builders cost, beside Anthropic's guidance in `standards/models.md`;
  no measurement supports it yet. `check_run.py` does not enforce it.
- Run `/swd:setup` again after updating: its allow rules name the
  installed version's folder.

## 0.11.0

- `/swd:setup` writes one allow rule per script a run needs, for each
  of `python3`, `python` and `py -3`, naming the script's full path in
  the installed version's folder, in place of the three broad Python
  rules, which matched any command that starts with the Python name and
  the plugin's folder. The seven scripts are `check_run.py`,
  `swd-clean.py`, `swd-dashboard.py`, `swd-findings.py`, `swd-log.py`,
  `swd-pr.py` and `swd-test.py`. Every rule naming the plugin's folder
  is written for the plugin's path as typed and, when it resolves to
  another spelling, as resolved, so with a symlinked `~/.claude` both
  spellings match. Run `/swd:setup` again after updating; until you do,
  `/swd:queue` sends you there.
- `/swd:setup` writes seven ask rules: `Bash(python3 *swd-setup.*)`,
  `Bash(python *swd-setup.*)`, `Bash(py *swd-setup.*)`, the same three
  for `swd-queue.`, and `Bash(*SWD_UNATTENDED*)`. An ask rule beats an
  allow rule. Once setup has written its rules, Claude Code asks you to
  approve the setup and queue commands that `/swd:setup` and
  `/swd:queue` run, every time, so that an agent that follows the
  playbooks cannot change this project's permission rules or start a
  queue without you; an agent set on getting round the rules still
  can, as the limits below say. The two skills tell you so before the
  first prompt. In an unattended run nobody can answer, so such a
  command does not run.
- `/swd:setup` removes the rules an earlier version of the plugin
  wrote, after your yes: the three broad Python rules, the 0.8.x
  `Bash(<plugin folder>/*)`, and the `sh` and per-script rules of
  another version's folder. `--print` lists them under
  `Rules an earlier version of the plugin wrote, which setup removes:`,
  and the real run reports the count, as
  `setup: <a> rules added to <settings>; <r> rules an earlier version of the plugin wrote removed`.
  Every other rule, yours included, is kept in order. A settings file
  that is not valid JSON, `NaN`, `Infinity` and a key repeated in one
  object included, is refused and left unchanged.
- `--print` ends with one line: `In place:` when the settings file holds
  every rule it lists and none an earlier version wrote, and
  `Not in place:` otherwise. `/swd:queue` starts only on `In place:`,
  in place of comparing the rules one by one.
- `swd-setup.py` refuses a plugin path, whether given with
  `--plugin-root` or found by setup itself, that is not absolute,
  that holds a `..` folder, that is the file-system root, one folder
  below it, your home folder or above it, or that holds a character
  other than letters, digits and `. _ - + @ / : ~` (a space
  included), with exit 2, one line on standard error and nothing
  written: such a path would make the rules match commands or files
  other than the plugin's scripts. A plugin path with a space is not
  supported: the skills type the path unquoted.
- Setup refuses a `--command`, or the test command in
  `.swd/project.md`, that is empty, whose first word holds a `*`, that
  holds a control character, whose first word is not a plain program
  name or path, whose first word is `env`, `xargs`, `sudo`, `doas`,
  `eval` or `exec`, that is `sh`, `bash`, `zsh`, `dash`, `ksh`, `fish`
  or `npx` alone or followed by an option (`bash scripts/test.sh` and
  `npx jest` are accepted), or that names the plugin's own folder. It
  prints one line saying why, exits 2 and writes nothing. The setup
  skill warns that every command it takes from `.swd/project.md`, the
  test, lint, type check and build commands, may have been written by
  an agent in an earlier run: a wrong `Test command:` line is corrected
  in the file, because setup always writes the rules for that line,
  and another command is left out by not passing it with `--command`.
- `/swd:queue` starts each run with `SWD_UNATTENDED` set to the model
  it starts it with, `fable` or `opus`, and `check_run.py` reads it:
  the seal takes the model from it, not from the `Conductor:` line. In
  a run started so on Opus 5.5, the seal of a changed plan needs the
  last `Judge plan:` or `Judge unreachable:` line since the last seal
  to be the judge's verdict that the plan holds, and the build playbook
  stops the run as blocked when the judge could not be reached. `check_run.py --seal`
  refuses otherwise, with one of these lines:

      decisions.md: this run was started by /swd:queue and the conductor is on Opus 5.5, so the plan needs the Fable judge's verdict: the last 'Judge plan:' or 'Judge unreachable:' line below the last 'Plan checksum:' line must be 'Judge plan: ...'; 'Judge unreachable:' is not enough, and the run stops as blocked
      decisions.md: this run was started by /swd:queue and the conductor is on Opus 5.5, so the plan needs the Fable judge's verdict that it holds: the last 'Judge plan:' line below the last 'Plan checksum:' line does not say 'the plan holds', and the conductor of such a run does not overrule it; the plan goes back to the architect

  In such a run, on either model, `check_run.py --task` and the check
  of a finished run report a plan that was never sealed:

      decisions.md: this run was started by /swd:queue and has no 'Plan checksum:' line: its plan was never sealed, so no builder may work on it, and the run stops as blocked

  In a run you attend nothing changes: the principal judges alone when
  the judge cannot be reached, and the run goes on. Whether Claude Code
  passes `SWD_UNATTENDED` on to a run's commands has not been tried on a
  live Claude Code; if it does not, a queue run seals as in 0.10.0.
- What the rules do not stop:

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
  command's rules before you say yes.

## 0.10.0

- A conductor setting per project. Type `/swd:conductor opus` in a
  project to let Fable 5.2 or Opus 5.5 conduct its runs, and
  `/swd:conductor fable` (the default) for Fable 5.2 alone;
  `/swd:conductor` with no value shows the setting. Any other value is
  refused and stores nothing. The hook stores it only for a command
  you type, in `~/.claude/swd-conductor/`, one file per project named
  by a hash of the project's folder, and reads no file in your project
  to decide it. It applies in that folder and its `.swd/worktrees/`; a
  session started in a subfolder of the project has its own setting,
  `fable` until set. An entry the hook cannot read counts as `fable`.
- With nothing stored, or `fable`, the hook's reminder and its switch
  rule are as in 0.9.0. Under `opus` the reminder names both models and
  tells an Opus 5.5 principal to dispatch the Fable judge. Under `opus`
  a switch between Fable 5.2 and Opus 5.5 is allowed either way while
  swd mode is on, and a switch from either to any other model is
  cancelled, with its own message.
- `/swd:build` and `/swd:follow` no longer have `model: fable` and keep
  `effort: high`: the session's model conducts. The principal checks it
  against the models the reminder accepts, as before, and stops on any
  other, naming `/model fable` (or `/model opus` under `opus`). So with
  the default setting a session on another model is now stopped on the
  first turn, where 0.9.0 ran that turn on Fable 5.2.
- Preflight writes `Conductor: Fable 5.2` or `Conductor: Opus 5.5` in
  `decisions.md` after the first four lines, and the principal appends
  a new one whenever it finds itself on the other accepted model.
  `check_run.py --plan` and `--seal` report a run without one. Runs
  from before 0.10.0 have none and still check clean once finished.
- The Fable judge, a new agent (`swd:judge`). A principal on Opus 5.5
  dispatches it with `model: fable` and `effort: high`, before writing
  its own answer, on the plan (before the seal and after each
  amendment), on a ruling that touches a trust boundary, and on a
  ruling a builder or a checker disputes. The judge reads the run
  folder, runs nothing, and writes `reports/judge-<n>.md`, whose first
  line is its verdict. The principal records it as `Judge plan:` or
  `Judge ruling:` and follows it, records `Judge overruled:` with its
  reason when it does not, and records `Judge unreachable:` and judges
  alone when the dispatch fails or returns no verdict (a Fable quota
  that has run out among the reasons). `check_run.py --seal` refuses a
  plan whose last `Conductor:` line is not Fable 5.2 without a
  `Judge plan:` or `Judge unreachable:` line since the last seal; a
  seal with `plan.md` unchanged since the last one, such as after a
  change to `staffing.md` or `spec.md` alone, needs none. That check is
  a reminder, not proof: it reads lines the principal writes and cannot
  show the judge was dispatched.
- `/swd:queue` starts every run with the project's setting:
  `--model fable` as before, or `--model opus` under `opus`. It does not
  start on Fable 5.2 and fall back, because `--fallback-model` does not
  switch on a rate-limit or usage-limit error. It prints
  `starting with --model <model>: <item>` before each run, and its dry
  run shows `model: <model>`.
- `/swd:setup` also adds three deny rules, `Bash(python3 *swd-mode.*)`,
  `Bash(python *swd-mode.*)` and `Bash(py *swd-mode.*)`, so Claude Code
  refuses the plain ways of running the plugin's hook by name, even
  under the broad Python rules; in 0.9.0 an agent could pipe a forged
  event into the hook unprompted. A deny rule refuses the command; it
  does not ask. The rules name the file up to its dot, so the hook's
  compiled copy is refused too and a run folder named with `swd-mode`
  is not caught. They are not a hard boundary: they match command
  text, so they do not stop the name in another letter case on a file
  system that ignores case, the name written another way, such as part
  of it quoted or given through a shell variable, a shell wildcard, or
  code a run executes by design, such as its tests, and a session in a
  mode that skips permission checks is protected by no rule. Whether
  another allowed command can run the hook, such as `find -exec` or a
  git alias, has not been checked. Setup keeps every rule
  already there and removes none. Run `/swd:setup` again after
  updating; until you do, `/swd:queue` sends you there.
- `dashboard.html` shows each task's model and effort from
  `staffing.md`, the model and effort of the reviews and the final
  check, and the conductor's model from the last `Conductor:` line.
  A run without them still gets its page, with that model left out.

## 0.9.0

- The plugin runs on native Windows, with Git for Windows (Claude Code
  started from PowerShell or CMD, not WSL): Claude Code runs the hooks
  and the team's commands in Git Bash. The test suite is set to run on
  Windows in CI; nobody on the team has run it on a Windows machine yet, so a real
  Claude Code session there is still to be tried.
- The hooks start Python through `scripts/swd-python.sh`, run as
  `sh <path>`. It tries `python3`, `python`, then `py -3`, and skips
  the Microsoft Store stub and any Python older than 3.9. It looks only
  in absolute folders on the PATH: empty and relative `PATH` entries
  are ignored, so a `python` in a cloned project is never run as the
  hook's Python (a Python reachable only through an entry starting with
  a literal `~` is no longer found). On Windows it also looks in the
  per-user folders winget's Python installs to. With no Python, every
  prompt gets a one-line notice naming `/swd:setup`, and no prompt,
  command or model switch is blocked.
- Looking for Python never installs it: the launcher starts every
  Python it tries with `PYTHON_MANAGER_AUTOMATIC_INSTALL=false` and
  without `PYLAUNCHER_ALLOW_INSTALL` or `PYLAUNCHER_ALWAYS_INSTALL`, so
  the Python install manager on Windows does not install a runtime on
  its own.
- Python is installed only after you say yes. `/swd:setup`,
  `/swd:build`, `/swd:follow` and `/swd:queue` first run
  `sh <plugin>/scripts/swd-python.sh check`. When Python is missing on
  Windows with winget, `/swd:setup` asks, naming the winget command and
  that it accepts the package's license agreements, and installs Python
  3.13 only on your own yes typed in the conversation, then checks that
  Python runs. An unattended run stops instead. On macOS and Linux it
  prints the command for your package manager and installs nothing.
  `/swd:on` says when Python is missing.
- The playbooks run every script as `<python> <plugin>/scripts/...`,
  with the Python `check` found, and tell the principal to use the Bash
  tool, never PowerShell, with forward slashes in paths.
  `scripts/swd-log.py` replaces `swd-log.sh`, which is removed. The
  watch script is run as `sh <plugin>/scripts/swd-watch.sh <run>`.
- `/swd:setup` writes rules for `python3`, `python` and `py -3`, and two
  exact `sh` rules, for the Python check and the watch script, that
  name the installed version's folder. So run `/swd:setup` again after
  each plugin update. `sh` rules for older versions can stay in the
  settings file. `/swd:queue` counts a rule only when it is in the settings file
  exactly as printed, so after an update it sends you to `/swd:setup`.
  On Windows the rules use forward slashes and the `//c/...` form.
- `/swd:setup` no longer writes the 0.8.x rule `Bash(<plugin folder>/*)`
  (on macOS, for example,
  `Bash(/Users/you/.claude/plugins/cache/swd-agents/swd/*)`), but a
  settings file that already has it keeps it. It allows any command that
  starts with the plugin's folder, as broad as the Python rules: delete it
  from `.claude/settings.local.json`.
- Every script reads and writes text as UTF-8, whatever the system's
  code page. The test runner runs commands with Git's `sh` on Windows,
  the checker accepts `\` in file lists and CRLF line endings, and the
  dashboard keeps watching when Windows briefly locks the page.
  `.gitattributes` keeps every file LF on checkout.
- GitHub Actions (`.github/workflows/test.yml`) runs the suite on
  Windows, macOS and Linux, on Python 3.9 and 3.13, on every push and
  pull request.
- Not supported on Windows: the herdr watch panes, the end-to-end pilots
  (`tests/run_pilot.sh`), and `/swd:queue` with Claude Code installed by
  npm (`claude.cmd`); install Claude Code with the native installer for
  the queue.

## 0.8.3

- The principal runs on Fable 5.2, always. `/swd:build` and
  `/swd:follow` tell it to check which model it is on, only from its
  own system and session information, at the start of every turn and
  again before every action that changes anything outside its own
  reply, such as a dispatch, ruling, commit, merge, push, reply on a
  pull request or write to the run folder, since an automatic
  fallback can change the model in the middle of a turn. On any other
  model, or when it cannot tell, it does no principal work and changes
  nothing for the run outside its reply: it says which model it is on
  and that the run continues once you run `/model fable` and send a
  message, and stops. This replaces the gate's "the model is their
  choice".
- A `PreModelSwitch` hook cancels a switch away from Fable 5.2 while
  swd mode is on in the session, and says why; run `/swd:off` to
  switch anyway. A switch to Fable 5.2 is never cancelled. The hook
  reads no file in your project, so a repository you clone cannot
  lock your model or write into its message. It lets a switch through
  when it cannot read its input or cannot decide within 3 seconds; if
  it cannot start, or cannot finish, within Claude Code's 10-second
  timeout, Claude Code cancels the switch. If `/swd:off` cannot delete
  its flag file, it says so and names the file: delete it by hand, or
  start a new session (not a resumed one). Every automatic way off
  Fable 5.2 (an automatic fallback, a fallback model chain, a gateway
  model id the hook does not recognise) is covered by the principal's
  own check, not by the hook. Claude Code 2.1.321 or later is required
  (Fable 5.2 needs it).
- swd mode turns off only when "stop swd" or `/swd:off` is the whole
  message (letter case and spaces around it ignored). Before, the
  words anywhere in a message turned it off, and so did a background
  agent's report or another session's message that quoted them. If
  you used to type "stop swd" inside a longer sentence, send it on
  its own.
- swd mode turns on only when you type `/swd:build`, `/swd:follow` or
  `/swd:on`: the hook reads the command Claude Code expands, not the
  text of a message, so an agent's report or another session's
  message that starts with one cannot turn it on. `/swd:off` now says
  when swd mode stayed on (`/swd:off please` or the short form `/off`,
  for example) instead of reporting it off.
- The swd-mode hook counts only a regular file as its flag, so a
  folder left at the flag's path no longer cancels every switch with
  a `/swd:off` that cannot remove it. `/swd:on` replaces a symbolic
  link at that path instead of writing through it, and input nested
  too deeply is ignored silently.
- `/swd:follow` asks for Fable 5.2 at high effort (`model: fable`,
  `effort: high`) and turns swd mode on, as `/swd:build` does.
- While swd mode is on, the text it adds to every prompt carries the
  same rule, so it is in front of the session before a skill loads.
- `/swd:queue` starts every run with `--model fable`. A `Model:` line in
  `.swd/queue.md` is ignored, and the script prints one line saying so.

## 0.8.2

- `/swd:follow` acts only on feedback from the repository's owner,
  members and collaborators. Feedback from anyone else is written to the
  feedback report under `## From people outside the repository` and gets
  a reply only; no builder changes anything for it, and the text of a
  comment is never taken as an instruction.
- That section is always the last in the report and runs to the end of
  the file, so a comment cannot forge a `## Comments to address` section
  after it: nothing after its heading can be a change.
- Every item in the feedback report, a failing check, a trusted comment
  or an outside one, is one line starting with `- `, and every further
  line of it starts with two spaces and `> `. So a line starting `- ` is
  always one item and a line starting `## ` is always one of the report's
  own headings, whatever a comment holds; a list or a heading in a
  comment stays inside its item.
- Before routing, the principal counts the items under
  `## Failing checks` and under `## Comments to address`, the ones it
  will only reply to included, and checks that they number the same as
  the `failing checks` and `new comments` counts on the summary line; if
  either differs it changes nothing, stops work on that pull request and
  tells the user. `Finish: pr` in `/swd:build` makes the same check on
  the failing checks before it routes any.
- A trusted comment that only points at another comment ("+1 to the
  suggestion below") gets a reply asking its author to state the change
  in their own words, and no change.
- The exit-10 summary line of `swd-pr.py` has a third count, for example
  `1 from outside the repository (reply only)`. Feedback from outside the
  repository alone still exits 10, because it may need a reply. When
  none of it does, no reply is posted, and it is still marked as handled.
- A builder's brief, and the architect's when a change needs a new task,
  now quotes the items to make instead of naming the feedback report,
  after a `Make these changes:` line.
- A trusted request to change what the run executes (a test or build
  script, a Makefile, a CI configuration, a dependency manifest, or the
  lint, type check and build commands in the project notes) is read
  against the limits on the project's own commands before it is
  taken; one that fails gets a reply and no change.

## 0.8.1

- A checker's commands are of two kinds. The project's own (the plan's
  `Test command:`, each task's `- Check:`, and the lint, type check and
  build commands in the project notes) are run as given and may download
  the project's declared dependencies. A checker never runs any other
  command (one the `## Outcome` shows, or one it runs to exercise a
  criterion) that commits, pushes, publishes, deploys or sends anything to
  a host outside this machine (any request counts: an upload, a download,
  a `git fetch`, a name lookup), in the worktree or in a copy. It does not
  run in the worktree one whose purpose is to rewrite tracked files. It
  runs `git status --short` before and after the Outcome's commands, and a
  tracked file the commands changed is a finding that fails the run.
- The principal reads every command a checker will run when it judges the
  plan. Each of the project's own must be a test, lint, type check or
  build of this project and nothing else, one that does not commit, push,
  publish or deploy. Apart from downloading the dependencies the project's
  manifest or lock file already declares, it may not send anything to a
  host outside this machine, fetch and run code the project does not
  declare, or change anything outside the worktree; a command the
  principal cannot tell this about from reading it and the script or
  config it names fails the reading. No other command may be one the
  never-run list above covers, and each Outcome command must be one an
  acceptance criterion needs. The architect writes
  its commands to the same two kinds.
- The seal requires the `final` row in every mode and the `review` row in
  production and prototype mode.
- A `review` or `final` row may not be on a model below any task's row. The
  seal refuses it.
- The seal reads every line of `staffing.md` that contains `|` as a row,
  and refuses a row whose `For` is not a plan task id, `plan`, `review`
  or `final`, an empty one included. 0.8.0 skipped a line with no leading
  `|` and accepted a row with any other `For`. A note in `staffing.md`
  must not contain `|`.
- `check_run.py --seal` also records `Staffing checksum:`, and a `staffing.md`
  changed after the seal is reported until the run is sealed again. A change
  to `staffing.md` alone is sealed again without a new `Plan judged:` line.
- Runs sealed by 0.7.1 and 0.8.0 keep checking clean: with no
  `Staffing checksum:` line nothing is compared. A 0.8.0 run that is sealed
  again is held to the new rows, the floor and these row rules.

## 0.8.0

- Outcome-shaped plans: `plan.md` needs an `## Outcome` section showing the
  finished result as it will really appear, and every task an `- Outcome:`
  line. `check_run.py --plan` and `--seal` name what is missing.
- Runs from before 0.8.0 keep working: the check of a finished run
  does not ask a sealed run for `## Outcome` (a run never sealed is still
  held to it), so `/swd:follow` still works on the pull
  requests earlier versions opened. When such a run's plan is amended,
  the amendment adds the outcome, and the plan is judged and staffed
  before it is sealed again.
- QA compares the built result with the plan's `## Outcome`, and the quick-run
  reviewer does the same.
- `/swd:build` asks for Fable 5.2 at high effort. The pin lasts for the turn
  that runs it; `/model fable` keeps an interactive run on it.
- The principal judges the plan against the spec before the gate and records a
  `Plan judged:` line in `decisions.md`. The seal is refused without it, and
  an amended plan needs a new one before it is sealed again.
- The principal chooses the agent, model and effort for every task, review and
  final check, and writes them to `staffing.md`, shown at the gate. The seal
  is refused without a row for every task. The fixed model table is gone.
- `standards/models.md` is the standing rule for those choices, copied into
  each run's `standards.md`. It is replaced when Anthropic publishes newer
  guidance.
- The queue's `Model:` line no longer lowers a run's cost: the principal runs
  on Fable 5.2 whatever it says.

## 0.7.1

- Progress in the conversation: each time the principal logs an event, it
  also says one short line in the chat, with the tasks done out of the total,
  so a run can be followed in any host without the dashboard or herdr.

## 0.7.0

- Herdr desktop app: when `HC_TERMINAL_SOCKET` is set, `scripts/swd-watch.sh`
  starts the ledger and activity watchers as two terminals with `hc run`
  (labelled `swd=ledger` and `swd=activity`). The herdr pane path is unchanged.

## 0.6.0

- Recorded test evidence: builders run their check through
  `scripts/swd-test.py`, which records the real output and result. The run
  check requires a failing run recorded before a passing one for every
  task, so test-first can no longer be claimed after the fact.
- The test suite between waves and before final checks is run by that
  script, not by an agent. QA is dispatched once, for lint, type check,
  build and the acceptance criteria.
- `/swd:follow`: picks up the pull requests earlier runs opened, fixes
  failing checks and addresses review comments through the team, pushes,
  and replies on the pull request. A run that finishes with a pull request
  also waits up to ten minutes for its checks.
- `/swd:queue`: works through `.swd/queue.md` unattended, one run per item,
  including GitHub issues written as `#12`.

## 0.5.0

- Quick mode: a small, low-risk change in a project the team already knows
  takes a short path, with no architect, one builder, and one review that
  also runs the tests and the acceptance criteria.
- Project notes: `.swd/project.md` keeps the project's commands, layout and
  conventions from one run to the next.
- Findings backlog: defects the team sees and does not fix are collected in
  `.swd/findings.md`.
- `/swd:setup` adds the permission rules a run needs to the project's local
  settings, after showing them and asking.
- Agents give the shell one plain command per call and read files with the
  Read tool, so their commands are not held for approval.

## 0.4.0

- Housekeeping at the start of every run (`scripts/swd-clean.py`): removes
  the worktrees of finished and abandoned runs, and deletes `swd/` branches
  that are already merged, locally and on `origin`. A branch whose pull
  request was merged on GitHub counts as merged. Unfinished runs, worktrees
  with uncommitted changes and unmerged branches are kept and listed.

## 0.3.0

- A run now works in its own git worktree, `.swd/worktrees/<name>/`, on the
  branch `swd/<name>`. Your working copy stays on its branch and is not
  touched, and a run no longer needs a clean working tree.
- At the approval gate you choose how the run is delivered: merge into the
  base branch and push, push the branch and open a pull request, or leave
  the branch. The principal does it after the run passes, then removes the
  worktree and, after a merge, deletes the run's branch.
- `check_run.py --finish` checks that the delivery and clean-up happened.
- swd mode: `/swd:build` or the new `/swd:on` keeps the team on for the rest
  of the session, so later code-change requests go through it too. Say
  "stop swd" or run `/swd:off` to leave. New sessions start with it off.
- Agents run one plain shell command per call and retry a refused command
  in plain form before reporting a permission problem.
- QA's throwaway files go in `scratch/` inside the run folder.
- A defect the team sees in existing code and does not fix is recorded in
  `decisions.md` as a `Finding:`.
- Changed behaviour: the principal used to never merge or push. It now does
  so when, and only when, you choose that finish.

## 0.2.0

- The principal now proves a subagent can write files before starting a
  run, and stops with an explanation if the session's permission mode
  refuses.
- The approved plan is sealed with a checksum; a change to `plan.md` that
  was not sealed fails the run check.
- When a builder returns, the principal compares what changed with what
  the builder's report claims (`check_run.py --task`) and stops on any
  change no report accounts for.
- A dispatch refused by the permission system is a blocker and no longer
  counts as a fix attempt.
- The repository is now a Claude Code plugin marketplace. Install the plugin
  with `/plugin marketplace add parthadcdev/swd-agents` and
  `/plugin install swd@swd-agents`. `claude --plugin-dir` still works for a
  local checkout.
- The plugin manifest names its author.
