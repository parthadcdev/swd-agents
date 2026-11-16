#!/usr/bin/env python3
"""Append one line to a run's activity.md, stamped from the local clock.

    <python> swd-log.py <run_dir> <event> [detail...]

Writes `- HH:MM:SS <event> <detail>`. The event must be one check_run.py accepts. One command with
no shell substitution, so it is easy to allow in a permission list, and it runs wherever Python does.
"""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_run import EVENTS  # noqa: E402


def main(argv):
    if len(argv) < 3:
        print("usage: swd-log.py <run_dir> <event> <detail...>", file=sys.stderr)
        return 1
    run_dir, event = Path(argv[1]), argv[2]
    if event not in EVENTS:
        print(f"unknown event: {event}", file=sys.stderr)
        return 1
    if not run_dir.is_dir():
        print(f"not a run folder: {run_dir}", file=sys.stderr)
        return 1
    # Split and rejoin, so a detail holding a line break cannot add a timeline line of its own.
    detail = " ".join(" ".join(argv[3:]).split())
    line = f"- {datetime.datetime.now():%H:%M:%S} {event} {detail}".rstrip()
    with open(run_dir / "activity.md", "a", encoding="utf-8", newline="\n") as f:   # LF on Windows too
        f.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
