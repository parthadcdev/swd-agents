#!/usr/bin/env python3
"""Work through a project's queue, .swd/queue.md: one unattended swd run per open item.

    python3 swd-queue.py --dry-run <project>    list what would run
    python3 swd-queue.py <project>              run every open item, one at a time
    python3 swd-queue.py --max 3 <project>      stop after three items

The queue is a markdown list. `- [ ] <requirement>` is an open item; `- [ ] #12` means GitHub
issue 12. An optional line `Finish: pr`, `Finish: merge-push` or `Finish: branch` says how
every run is delivered (default: pr). Every run starts with `--model fable`, because the
principal does no work off Fable 5.2; a `Model:` line, which earlier versions read, is ignored
and the script says so once. Each item is run as its own `claude -p "/swd:build ..."`,
pre-approved, so each starts with a fresh context. When a run finishes the item becomes
`- [x] <item> — <where the work is>`; when it does not, `- [!] <item> — blocked: <run folder>`.
Two failures in a row stop the queue: that usually means something systemic, such as missing
permissions (run /swd:setup first). A summary is written to .swd/queue-report.md.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_run import check_finish, decision, parse_ledger, read  # noqa: E402

FINISH_WORDS = {
    "pr": "push the branch and open a pull request",
    "merge-push": "merge it into the base branch and push",
    "branch": "leave the branch and push nothing",
}
OPEN_RE = re.compile(r"^- \[ \] (.+?)\s*$")


def requirement(project, item):
    """The text handed to /swd:build for one queue item."""
    issue = re.fullmatch(r"#(\d+)", item)
    if not issue:
        return item
    number = issue.group(1)
    try:
        reply = subprocess.run(["gh", "issue", "view", number, "--json", "title,body"],
                               cwd=project, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
        data = json.loads(reply.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    if reply.returncode != 0:
        return None
    return (f"GitHub issue #{number}: {data.get('title', '')}\n\n{data.get('body', '')}\n\n"
            f"Write 'Closes #{number}' in the pull request description.")


def run_item(project, text, finish):
    """Run one requirement to the end. Returns (finished, where): the run's branch or pull request, or its folder."""
    runs = project / ".swd" / "runs"
    before = set(runs.iterdir()) if runs.is_dir() else set()
    prompt = (f"/swd:build {text}\n\nI pre-approve the spec and plan; do not wait for me, and ask no questions: "
              f"record your assumptions instead. When the run passes, {FINISH_WORDS[finish]}.")
    # Each run sees this plugin and the project's own settings (where /swd:setup put its rules), and
    # nothing from the user's global setup: a personal hook that rewrites shell commands would stop
    # them matching the project's permission rules, with nobody there to approve them.
    plugin = str(Path(__file__).resolve().parent.parent)
    try:
        subprocess.run(["claude", "-p", "--plugin-dir", plugin, "--setting-sources", "project,local",
                        "--model", "fable", "--output-format", "json", "--", prompt], cwd=project,
                       capture_output=True, text=True, env={**os.environ, "SWD_NO_BROWSER": "1"}, encoding="utf-8", errors="replace")
    except OSError as error:
        return False, f"could not start claude: {error}"
    new = sorted(set(runs.iterdir()) - before) if runs.is_dir() else []
    if not new:
        return False, "no run was started"
    run = new[-1]
    rows, _ = parse_ledger(read(run / "ledger.md") or "")
    timeline = (read(run / "activity.md") or "").rstrip().splitlines()
    finished = (bool(rows) and all(row["status"] == "done" for row in rows.values())
                and bool(timeline) and re.match(r"- \S+ done\b", timeline[-1]) is not None
                and not check_finish(run, project))
    if not finished:
        return False, f".swd/runs/{run.name}"
    where = decision(run, "Branch") or run.name
    if decision(run, "Finish") == "pr":
        try:
            link = subprocess.run(["gh", "pr", "view", where, "--json", "url", "-q", ".url"], cwd=project,
                                  capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace").stdout.strip()
            where = link or where
        except (OSError, subprocess.TimeoutExpired):
            pass
    return True, where


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="list the open items and start nothing")
    parser.add_argument("--max", type=int, default=None, metavar="N", help="run at most N items")
    parser.add_argument("project", type=Path)
    args = parser.parse_args(argv)

    project = args.project.resolve()
    queue = project / ".swd" / "queue.md"
    if not queue.is_file():
        print(f"no queue: write the requirements as '- [ ] ...' lines in {queue}", file=sys.stderr)
        return 1
    finish = (re.search(r"^Finish: (\S+)", queue.read_text(encoding="utf-8"), re.M) or [None, "pr"])[1]
    if finish not in FINISH_WORDS:
        print(f"{queue}: Finish must be one of {', '.join(FINISH_WORDS)}", file=sys.stderr)
        return 1

    model = re.search(r"^Model: (\S+)", queue.read_text(encoding="utf-8"), re.M)
    if model:
        # Escape what the terminal would act on, so a crafted line cannot clear the screen or set the title.
        shown = "".join(c if c.isprintable() else c.encode("unicode_escape").decode() for c in model[1])
        print(f"ignoring 'Model: {shown}' in .swd/queue.md: every run starts with --model fable", flush=True)
    open_items = [m.group(1) for m in map(OPEN_RE.match, queue.read_text(encoding="utf-8").splitlines()) if m]
    if args.dry_run:
        print(f"{len(open_items)} open items, finish: {finish}, model: fable")
        for item in open_items:
            print(f"- {item}")
        return 0

    results, failures_in_a_row = [], 0
    for item in open_items[:args.max]:
        text = requirement(project, item)
        finished, where = run_item(project, text, finish) if text else (False, "could not read the issue with gh")
        mark = f"- [x] {item} — {where}" if finished else f"- [!] {item} — blocked: {where}"
        # Re-read the file each time: the user may be editing the queue while it runs.
        lines = queue.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if line.rstrip() == f"- [ ] {item}":
                lines[index] = mark
                break
        queue.write_text("\n".join(lines) + "\n", encoding="utf-8")
        results.append(mark)
        print(mark, flush=True)
        failures_in_a_row = 0 if finished else failures_in_a_row + 1
        if failures_in_a_row == 2:
            print("two items in a row did not finish; stopping. Check permissions (/swd:setup) and the blocked runs.")
            break

    done = sum(1 for mark in results if mark.startswith("- [x]"))
    when = datetime.datetime.now().isoformat(timespec="minutes")
    report = project / ".swd" / "queue-report.md"
    report.write_text(f"# Queue report, {when}\n\n{done} done, {len(results) - done} blocked, "
                      f"{len(open_items) - len(results)} not started.\n\n" + "\n".join(results) + "\n", encoding="utf-8")
    return 1 if failures_in_a_row == 2 else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
