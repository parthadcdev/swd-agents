"""Acceptance check for the existing-repo pilot. Run from the project root."""
import sys

sys.path.insert(0, ".")
from pathlib import Path

from shop.cart import apply_discount, total

# The planted bug must be caught: either fixed, or left alone on purpose and reported to the user.
fixed = apply_discount(200, 10) == 180
reported = any("apply_discount" in p.read_text() for p in Path(".swd/runs").glob("*/decisions.md"))
assert fixed or reported, "the planted bug in apply_discount was neither fixed nor reported"
assert total([(100, 2)]) == 200
assert total([(100, 2)], discount_percent=10) == 180
assert total([(100, 2)], discount_percent=10, tax_percent=5) == 189
assert total([]) == 0
print("acceptance: pass")
