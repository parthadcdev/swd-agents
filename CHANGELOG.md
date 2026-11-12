# Changelog

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
