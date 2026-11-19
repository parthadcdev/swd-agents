#!/usr/bin/env python3
"""Run a run's test command and record what really happened.

    python3 swd-test.py <run_dir> T1        the task's Check command from plan.md
    python3 swd-test.py <run_dir> wave-1    the plan's Test command, after a wave
    python3 swd-test.py <run_dir> final     the plan's Test command, before the run is checked

The command runs in the run's worktree. Its output and exit code are written to
<run_dir>/evidence/<label>-<n>.txt, numbered in the order they happened, and the exit code is
passed on. Because the script writes the record, a failing run recorded before a passing one
is proof the test was written first; nobody can fill it in afterwards.

When check_run.py --cap gives a number, one run at a time per project takes <project>/.swd/test.lock
and the others wait for it ("waiting for another test run of this project to end").
"""
import datetime
import errno
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_run import parallel_cap, parse_plan, read, work_dir  # noqa: E402

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


def windows_sh():
    """The first sh.exe on an absolute PATH entry other than the current folder, or None.
    Not shutil.which: on Windows it searches the current folder first, which is the project."""
    here = os.path.normcase(os.getcwd())
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(folder, "sh.exe")
        if (folder and os.path.isabs(folder) and os.path.normcase(os.path.abspath(folder)) != here
                and os.path.isfile(candidate)):
            return candidate
    return None


def open_lock(path):
    """A descriptor on path as a regular file, never through a link (.swd/ can come in a commit), or None."""
    fd = None
    try:
        if os.name == "nt":
            # shortcut: lstat then open leaves a short race on Windows, which has no O_NOFOLLOW; upgrade if Windows gains one
            try:
                if not stat.S_ISREG(os.lstat(path).st_mode):
                    return None
            except FileNotFoundError:
                pass
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        if stat.S_ISREG(os.fstat(fd).st_mode):
            return fd
    except OSError:
        pass
    if fd is not None:
        os.close(fd)
    return None


def take_lock(project):
    """Wait for, then hold until this process exits, the project's test lock. The OS drops it when the holder dies.
    False when the lock file is refused; a file system that cannot lock runs the test without it."""
    folder = project / ".swd"
    folder.mkdir(exist_ok=True)
    fd = open_lock(folder / "test.lock")  # never closed or deleted once locked; not inherited by the command
    if fd is None:
        print("cannot use .swd/test.lock as the test lock: it is a link, not a regular file, or cannot be opened; "
              "remove it and run again", file=sys.stderr)
        return False
    waiting = "waiting for another test run of this project to end"
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, 0)
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # not LK_LOCK: it gives up after about 10 seconds
                    return True
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EDEADLOCK):  # not held by another run
                        raise
                    if waiting:
                        print(waiting, flush=True)
                        waiting = None
                    time.sleep(1)
        import fcntl
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(waiting, flush=True)
            fcntl.flock(fd, fcntl.LOCK_EX)
    except OSError:  # losing the evidence record is worse than two suites overlapping
        print("could not lock .swd/test.lock on this file system; running this test without the lock", file=sys.stderr)
    return True


def main(argv):
    if len(argv) != 3:
        print("usage: swd-test.py <run_dir> <T<n> | wave-<n> | final>", file=sys.stderr)
        return 2
    run_dir, label = Path(argv[1]).resolve(), argv[2]
    command = command_for(run_dir, label)
    if not command:
        print(f"no command for '{label}' in {run_dir / 'plan.md'}", file=sys.stderr)
        return 2
    # A capped machine runs one test suite at a time per project.
    if parallel_cap(os.environ)[0] is not None and not take_lock(run_dir.parents[2]):
        return 2

    # The command is the project's own test command, exactly as the plan states it, written for sh.
    # On Windows shell=True would mean cmd.exe, so it runs in Git's sh there, as the team's Bash tool does.
    sh = windows_sh() if os.name == "nt" else None
    try:
        done = subprocess.run([sh, "-c", command] if sh else command, shell=not sh,
                              cwd=work_dir(run_dir, run_dir.parents[2]), capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS, encoding="utf-8", errors="replace")
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
        f"Command: {command}\nExit: {code}\nWhen: {when}\n---\n" + "\n".join(lines[-KEEP_LINES:]) + "\n", encoding="utf-8")

    print("\n".join(lines[-SHOW_LINES:]))
    print(f"exit {code}; recorded in evidence/{record.name}")
    return code


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
