"""Acceptance check for the existing-repo pilot. Run from the project root."""
import sys

sys.path.insert(0, ".")
import re
from pathlib import Path

from shop.cart import apply_discount, total

# The planted bug must be caught: either fixed, or left alone on purpose and reported to the user.
fixed = apply_discount(200, 10) == 180
# "Reported" means a decision entry about it ("- ...", "Ruling: ...", "Finding: ..."), not a passing mention.
reported = any(
    re.search(r"^(- |\w+: ).*apply_discount", p.read_text(), re.M) for p in Path(".swd/runs").glob("*/decisions.md")
)
assert fixed or reported, "the planted bug in apply_discount was neither fixed nor reported"
assert total([(100, 2)]) == 200
assert total([(100, 2)], discount_percent=10) == 180
assert total([(100, 2)], discount_percent=10, tax_percent=5) == 189
assert total([]) == 0
# This pilot asks for the run to be merged: the work is on the base branch and the run's branch is gone.
import subprocess
branches = subprocess.run(["git", "branch", "--list", "swd/*"], capture_output=True, text=True).stdout.strip()
assert not branches, f"the merged run branch was not deleted: {branches}"
print("acceptance: pass")
