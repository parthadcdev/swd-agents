"""Acceptance check for the existing-repo pilot. Run from the project root."""
import sys

sys.path.insert(0, ".")
from shop.cart import apply_discount, total

assert apply_discount(200, 10) == 180, "the planted bug in apply_discount is still there"
assert total([(100, 2)]) == 200
assert total([(100, 2)], discount_percent=10) == 180
assert total([(100, 2)], discount_percent=10, tax_percent=5) == 189
assert total([]) == 0
print("acceptance: pass")
