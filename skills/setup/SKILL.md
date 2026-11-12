---
name: setup
description: Set up a project's permission rules so swd runs are not held for approval, by adding allow rules to the project's local Claude Code settings. Use when the user runs /swd:setup, or after a run was blocked by refused writes or commands.
---

# swd setup

Agents in an swd run work in the background, where nobody can answer a
permission prompt. If the project does not already allow what they need,
their file writes and shell commands are refused and the run stalls. This
skill adds the rules that prevent that.

The plugin root is two directories above this skill's base directory;
`<plugin>` means that path. `<project>` is the user's project folder.

1. Find the commands the team will need to run in this project: its test
   command, and its lint, type check and build commands if it has them.
   `.swd/project.md` records them once a run has happened; before that,
   look in the README, the package manifest, the Makefile and the CI
   configuration. Pass each one with `--command`.

   Also pass the command that runs the project's own code, such as
   `python3`, `node` or `go run`. QA and the reviewers have to run the
   software to check each acceptance criterion, and a rule for the test
   command alone does not cover that; without it a run stops at its final
   checks. This is the broadest rule in the set: it lets agents run any
   program with that interpreter in this project. Say so when you list the
   rules.
2. Show what would be added, changing nothing:

   ```bash
   python3 <plugin>/scripts/swd-setup.py --print --command "<test command>" --command "<interpreter>" <project>
   ```

3. Tell the user, in a short list, what the rules allow in this project:
   the plugin's own scripts; all `git` commands, including push; `gh pr`
   commands; the project's test command, if `.swd/project.md` records one;
   a few read-only commands; and edits inside `.swd/`, which is where the
   run folder and the run's worktree live. Say that the rules go in
   `.claude/settings.local.json`, the user's own settings for this project,
   and that existing settings are kept.
4. Ask whether to add them. Changing permission settings is the user's
   decision, so do not continue without a yes in this conversation.
5. On yes, run it again without `--print`, with the same `--command`
   arguments:

   ```bash
   python3 <plugin>/scripts/swd-setup.py --command "<test command>" --command "<interpreter>" <project>
   ```

   Report what it printed. Tell the user the rules apply from the next
   session or after the settings are reloaded, and that running
   `/swd:setup` again after the first run adds the project's test command
   if it was not known yet.

Do not edit the settings file yourself, and do not add rules beyond what
the script writes.
