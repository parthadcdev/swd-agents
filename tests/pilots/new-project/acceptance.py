"""Acceptance check for the new-project pilot. Run from the project root."""
import subprocess
import sys
from pathlib import Path

Path("sample.txt").write_text("one two\nthree four five\n")
ok = subprocess.run([sys.executable, "wc_lite.py", "sample.txt"], capture_output=True, text=True)
assert ok.returncode == 0, ok.stderr
assert ok.stdout.split() == ["2", "5", "24", "sample.txt"], ok.stdout

missing = subprocess.run([sys.executable, "wc_lite.py", "nope.txt"], capture_output=True, text=True)
assert missing.returncode == 1, missing.returncode
assert missing.stderr.strip(), "expected an error message on stderr"

mode = "".join(p.read_text() for p in Path(".swd/runs").glob("*/spec.md"))
assert "Mode: prototype" in mode, "the principal did not choose prototype mode"
# The light path: a small prototype with nothing risky in it gets one review at the end.
per_task = [str(p) for p in Path(".swd/runs").glob("*/reports/T*-code-reviewer.md")]
assert not per_task, f"prototype mode reviewed tasks one by one: {per_task}"
print("acceptance: pass")
