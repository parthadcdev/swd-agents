#!/usr/bin/env python3
"""Copy a run's findings into the project's backlog, .swd/findings.md.

    python3 swd-findings.py <run_dir>

A `Finding:` line in the run's decisions.md is a defect the team saw and did not fix. Left in
one run's folder it is forgotten; in the backlog the user and later runs can see it. Each
finding becomes an open item, `- [ ] <text> (<run>)`. Tick an item off by hand, or let a run
that fixes it do so. Running this twice adds nothing.
"""
import re
import sys
from pathlib import Path

HEADER = """# Findings

Defects the swd team noticed and did not fix, newest last. Tick one off when it is fixed.
To have the team fix one, give it to /swd:build as the requirement.

"""


def main(argv):
    run_dir = Path(argv[1]).resolve() if len(argv) == 2 else None
    if run_dir is None or run_dir.parent.name != "runs" or not (run_dir / "decisions.md").is_file():
        print("usage: swd-findings.py <run_dir>", file=sys.stderr)
        return 1
    findings = re.findall(r"^Finding: (.+?)\s*$", (run_dir / "decisions.md").read_text(), re.M)
    backlog = run_dir.parent.parent / "findings.md"
    text = backlog.read_text() if backlog.exists() else ""
    new = [f for f in dict.fromkeys(findings) if f not in text]
    if new:
        text = (text or HEADER).rstrip("\n") + "\n" + "".join(f"- [ ] {f} ({run_dir.name})\n" for f in new)
        backlog.write_text(text)
    print(f"findings: {len(new)} added to {backlog}" if new else "findings: nothing new")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
