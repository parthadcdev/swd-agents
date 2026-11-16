# Changelog

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
  when it cannot read its input or cannot decide within 3 seconds, so
  a hung home folder never locks your model. Claude Code 2.1.321 or
  later is required (Fable 5.2 needs it).
- swd mode turns off only when "stop swd" or `/swd:off` is the whole
  message (letter case and spaces around it ignored). Before, the
  words anywhere in a message turned it off, and so did a background
  agent's report or another session's message that quoted them. If
  you used to type "stop swd" inside a longer sentence, send it on
  its own.
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
