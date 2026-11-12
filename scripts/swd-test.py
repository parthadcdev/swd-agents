#!/usr/bin/env python3
"""Run a run's test command and record what really happened.

    python3 swd-test.py <run_dir> T1        the task's Check command from plan.md
    python3 swd-test.py <run_dir> wave-1    the plan's Test command, after a wave
    python3 swd-test.py <run_dir> final     the plan's Test command, before the run is checked

The command runs in the run's worktree. Its output and exit code are written to
<run_dir>/evidence/<label>-<n>.txt, numbered in the order they happened, and the exit code is
passed on. Because the script writes the record, a failing run recorded before a passing one
is proof the test was written first; nobody can fill it in afterwards.
"""
import datetime
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_run import parse_plan, read, work_dir  # noqa: E402

KEEP_LINES = 300        # of the output, in the record
SHOW_LINES = 40         # of the output, printed back to whoever ran this
TIMEOUT_SECONDS = 30 * 60


def command_for(run_dir, label):
    plan = read(run_dir / "plan.md") or ""
    if re.fullmatch(r"wave-\d+|final", label):
        match = re.search(r"^Test command: `(.+?)`", plan, re.M)
        return match.group(1) if match else None
    tasks, _ = parse_plan(plan)
    for task in tasks:
        if task["id"] == label:
            return task["check"].strip().strip("`") or None
    return None


def main(argv):
    if len(argv) != 3:
        print("usage: swd-test.py <run_dir> <T<n> | wave-<n> | final>", file=sys.stderr)
        return 2
    run_dir, label = Path(argv[1]).resolve(), argv[2]
    command = command_for(run_dir, label)
    if not command:
        print(f"no command for '{label}' in {run_dir / 'plan.md'}", file=sys.stderr)
        return 2

    try:
        # shell=True: the command is the project's own test command, exactly as the plan states it.
        done = subprocess.run(command, shell=True, cwd=work_dir(run_dir, run_dir.parents[2]),
                              capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
        code, output = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as error:
        code, output = 124, f"{error.stdout or ''}{error.stderr or ''}\ntimed out after {TIMEOUT_SECONDS} seconds"
    lines = output.splitlines()

    folder = run_dir / "evidence"
    folder.mkdir(exist_ok=True)
    number = len(list(folder.glob(f"{label}-*.txt"))) + 1
    record = folder / f"{label}-{number:03d}.txt"
    when = datetime.datetime.now().isoformat(timespec="seconds")
    record.write_text(
        f"Command: {command}\nExit: {code}\nWhen: {when}\n---\n" + "\n".join(lines[-KEEP_LINES:]) + "\n")

    print("\n".join(lines[-SHOW_LINES:]))
    print(f"exit {code}; recorded in evidence/{record.name}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
