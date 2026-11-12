"""Acceptance check for the fast-lane pilot: two runs in one project. Run from the project root.

The first run is a full production run, which leaves the project notes behind. The second is
a small change, which should take the quick path: no architect, one review.

    SWD_PILOT_SETUP=1 tests/run_pilot.sh fast-lane
"""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from shop.cart import item_count, total

assert total([(100, 2)], discount_percent=10, tax_percent=5) == 189
assert item_count([(10, 2), (5, 3)]) == 5
assert item_count([]) == 0

swd = Path(".swd")
notes = swd / "project.md"
assert notes.is_file() and "Test command:" in notes.read_text(), "the first run left no project notes"

runs = sorted(p for p in (swd / "runs").iterdir() if p.is_dir())
assert len(runs) == 2, f"expected two runs, found {[r.name for r in runs]}"
quick = [r for r in runs if "Mode: quick" in (r / "spec.md").read_text()]
assert len(quick) == 1, "the small second change did not take the quick path"
activity = (quick[0] / "activity.md").read_text()
assert "architect" not in activity, "the quick run dispatched the architect"
assert "qa-engineer" not in activity, "the quick run dispatched QA"
print("quick run:", quick[0].name, "-", len(activity.splitlines()), "timeline events")
print("acceptance: pass")
