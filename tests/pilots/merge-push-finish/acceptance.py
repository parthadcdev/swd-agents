"""Acceptance check for the merge-push-finish pilot. Run from the project root.

Needs a real GitHub remote: run it through
    SWD_PILOT_REMOTE=https://github.com/<owner>/<sandbox-repo>.git tests/run_pilot.sh merge-push-finish
"""
import subprocess
import sys

sys.path.insert(0, ".")
from shop.cart import total

assert total([(100, 2)], discount_percent=10, tax_percent=5) == 189


def out(*command):
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()


base = out("git", "branch", "--show-current")
assert base.startswith("pilot-"), f"expected to be on the run's base branch, on {base!r}"
assert not out("git", "branch", "--list", "swd/*"), "the merged run branch was not deleted"
subprocess.run(["git", "fetch", "-q", "origin"], check=True)  # ask GitHub, not the local record of the push
assert out("git", "rev-parse", "HEAD") == out("git", "rev-parse", f"origin/{base}"), "the base branch is not pushed"
assert "T1" in out("git", "log", "--format=%s", f"origin/{base}"), "the run's commits are not on the remote base branch"
print("pushed:", base, out("git", "rev-parse", "--short", "HEAD"))
print("acceptance: pass")
