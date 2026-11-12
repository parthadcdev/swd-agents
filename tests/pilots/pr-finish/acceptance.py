"""Acceptance check for the pr-finish pilot. Run from the project root, on the run's branch.

Needs a real GitHub remote: run it through
    SWD_PILOT_REMOTE=https://github.com/<owner>/<sandbox-repo>.git tests/run_pilot.sh pr-finish
"""
import json
import subprocess
import sys

sys.path.insert(0, ".")
from shop.cart import total

assert total([(100, 2)], discount_percent=10, tax_percent=5) == 189


def out(*command):
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()


branch = out("git", "branch", "--show-current")
assert branch.startswith("swd/"), f"expected to be on the run's branch, on {branch!r}"
assert out("git", "rev-parse", "HEAD") == out("git", "rev-parse", f"origin/{branch}"), "the run's branch is not pushed"

prs = json.loads(out("gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url,baseRefName,title,body"))
assert len(prs) == 1, f"expected one open pull request for {branch}, found {len(prs)}"
assert prs[0]["baseRefName"].startswith("pilot-"), f"pull request targets {prs[0]['baseRefName']!r}, not the run's base branch"
assert prs[0]["body"].strip(), "the pull request has no description"
print("pull request:", prs[0]["url"])
print("acceptance: pass")
