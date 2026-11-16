---
name: queue
description: Work through a list of requirements unattended, one swd run each, leaving a pull request or branch for every item. Use when the user runs /swd:queue, or asks the team to work through a backlog or a set of GitHub issues on its own.
---

# Queue

The queue is a file, `.swd/queue.md` in the user's project. Each open item
is run as its own swd run, in its own process and with a fresh context, one
after another, with nobody at the approval gate. It is for handing the team
a backlog and coming back to finished pull requests.

`<plugin>` means `${CLAUDE_PLUGIN_ROOT}`, the plugin root, two directories
above this skill's base directory. `<python>` is the command `check`
printed: the text between `python: ` and ` (Python`. `<project>` is the
user's project folder. Run every command with the Bash tool, and write
paths with forward slashes.

## The queue file

```markdown
# Queue

Finish: pr

- [ ] Add CSV export to the report page
- [ ] #42
- [ ] Fix the open finding about apply_discount
```

- `- [ ] <text>` is an open item, and the text is the requirement.
- `- [ ] #42` means GitHub issue 42: its title and body become the
  requirement, and the pull request says `Closes #42`.
- `Finish:` is `pr` (the default), `merge-push` or `branch`, for every item.
- A `Model:` line, which earlier versions read, is ignored: every run
  starts with `--model fable`, because the principal does no work off
  Fable 5.2. The script prints one line when it ignores one.
- When an item's run finishes it becomes `- [x] <item> — <link or branch>`.
  When it does not, `- [!] <item> — blocked: <run folder>`.

## Steps

1. If `.swd/queue.md` does not exist, create it from what the user asked
   for, in the form above, and show it to them. If they gave no items,
   explain the format and stop.
2. Find Python, which every script below runs with. Run this exact
   command, with nothing added:

   ```bash
   sh <plugin>/scripts/swd-python.sh check
   ```

   Exit 0 prints `python: <command> (Python <version>)`; that command is
   `<python>` from here on. Exit 3 means Python is missing: follow "When
   Python is missing" in `<plugin>/skills/setup/SKILL.md`, then run
   `check` again. An unattended run stops there, reports what `check`
   printed, and never installs Python. If its `python:` line shows a
   quoted full path, Python is not on this terminal's PATH (it was just
   installed, or its installer left it off PATH): tell the user to open a new terminal and start
   Claude Code again, as the setup skill says, and stop.

   Then check that unattended runs can work here. Nobody can answer a
   permission prompt during the queue, so the project needs its rules in
   place:

   ```bash
   <python> <plugin>/scripts/swd-setup.py --print <project>
   ```

   Every rule it printed must be in `.claude/settings.local.json` exactly
   as printed, character for character. A rule that names another version
   folder of the plugin does not count, so after a plugin update this
   check sends the user to `/swd:setup`. If any printed rule is missing,
   tell the user to run `/swd:setup` first, and stop.
3. Show what will run, starting nothing:

   ```bash
   <python> <plugin>/scripts/swd-queue.py --dry-run <project>
   ```

4. Ask the user to confirm. Say plainly what they are agreeing to: each
   item is a full run that spends tokens with nobody watching; the finish
   shown is carried out for every item without asking again, so `pr` opens
   pull requests and `merge-push` merges and pushes; and two failures in a
   row stop the queue. Offer `--max <n>` to try a few items first. Do not
   start without a yes in this conversation.
5. Start it as a background command, so the session stays free:

   ```bash
   <python> <plugin>/scripts/swd-queue.py <project>
   ```

   Tell the user where to watch: `.swd/queue.md` is ticked off item by
   item, each run has its own `dashboard.html` in its run folder, and
   `.swd/queue-report.md` is written at the end.
6. When the background command finishes, read `.swd/queue-report.md` and
   report: what is done, with the link or branch for each; what is blocked,
   with its run folder; and what was not started. For pull requests,
   mention `/swd:follow` for failing checks and review comments.

## Never

- Never run the items yourself in this session. The script starts each one
  in its own process so each has a fresh context.
- Never start the queue without the user's yes.
- Never edit an item's text. Only the script changes the marks.
