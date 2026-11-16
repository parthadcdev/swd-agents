---
name: queue
description: Work through a list of requirements unattended, one swd run each, leaving a pull request or branch for every item. Use when the user runs /swd:queue, or asks the team to work through a backlog or a set of GitHub issues on its own.
---

# Queue

The queue is a file, `.swd/queue.md` in the user's project. Each open item
is run as its own swd run, in its own process and with a fresh context, one
after another, with nobody at the approval gate. It is for handing the team
a backlog and coming back to finished pull requests.

The plugin root is two directories above this skill's base directory;
`<plugin>` means that path. `<project>` is the user's project folder.

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
- `Model:` is optional, for example `Model: sonnet`. It sets the model each
  run's session starts on. `/swd:build` asks for Fable 5.2 for the turn
  that runs it, and an unattended run is one turn, so the principal
  conducts on Fable 5.2 whatever this line says, and names the model and
  effort of every agent it dispatches. The line no longer lowers a run's
  cost; it takes effect only where Fable 5.2 is not available to the
  session.
- When an item's run finishes it becomes `- [x] <item> — <link or branch>`.
  When it does not, `- [!] <item> — blocked: <run folder>`.

## Steps

1. If `.swd/queue.md` does not exist, create it from what the user asked
   for, in the form above, and show it to them. If they gave no items,
   explain the format and stop.
2. Check that unattended runs can work here. Nobody can answer a permission
   prompt during the queue, so the project needs its rules in place:

   ```bash
   python3 <plugin>/scripts/swd-setup.py --print <project>
   ```

   If `.claude/settings.local.json` does not already contain those rules,
   tell the user to run `/swd:setup` first, and stop.
3. Show what will run, starting nothing:

   ```bash
   python3 <plugin>/scripts/swd-queue.py --dry-run <project>
   ```

4. Ask the user to confirm. Say plainly what they are agreeing to: each
   item is a full run that spends tokens with nobody watching; the finish
   shown is carried out for every item without asking again, so `pr` opens
   pull requests and `merge-push` merges and pushes; and two failures in a
   row stop the queue. Offer `--max <n>` to try a few items first. Do not
   start without a yes in this conversation.
5. Start it as a background command, so the session stays free:

   ```bash
   python3 <plugin>/scripts/swd-queue.py <project>
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
