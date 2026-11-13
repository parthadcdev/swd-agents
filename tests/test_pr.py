"""Tests for scripts/swd-pr.py: what a run's pull request needs next, read through a stub `gh`."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "swd-pr.py"

# gh pr view ... -> view.json ; gh api .../comments -> inline.json. Missing file: gh fails.
# view-once.json, when present, answers one `gh pr view` and is then gone.
GH_STUB = """#!/bin/sh
if [ "$1 $2" = "pr view" ] && [ -f "$GH_STUB_DIR/view-once.json" ]; then
  cat "$GH_STUB_DIR/view-once.json"; rm "$GH_STUB_DIR/view-once.json"; exit 0
fi
case "$1 $2" in
  "pr view") f="$GH_STUB_DIR/view.json" ;;
  "api "*)   f="$GH_STUB_DIR/inline.json" ;;
  *) exit 1 ;;
esac
[ -f "$f" ] || { echo "no pull requests found" >&2; exit 1; }
cat "$f"
"""

OK_CHECK = {"name": "tests", "status": "COMPLETED", "conclusion": "SUCCESS", "detailsUrl": "https://ci/1"}
BAD_CHECK = {"name": "lint", "status": "COMPLETED", "conclusion": "FAILURE", "detailsUrl": "https://ci/2"}
RUNNING = {"name": "tests", "status": "IN_PROGRESS", "conclusion": None, "detailsUrl": "https://ci/3"}


class PrTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.run_dir = tmp / "project" / ".swd" / "runs" / "2026-11-12-demo"
        (self.run_dir / "reports").mkdir(parents=True)
        (self.run_dir / "decisions.md").write_text("Base commit: 0\nBranch: swd/demo\nFinish: pr\n")
        self.stub = tmp / "stub"
        (tmp / "bin").mkdir()
        self.stub.mkdir()
        gh = tmp / "bin" / "gh"
        gh.write_text(GH_STUB)
        gh.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "GH_STUB_DIR": str(self.stub)}
        self.pr(checks=[OK_CHECK])

    def pr(self, state="OPEN", checks=(), comments=(), reviews=(), inline=()):
        (self.stub / "view.json").write_text(json.dumps({
            "number": 7, "url": "https://github.com/o/r/pull/7", "state": state,
            "statusCheckRollup": list(checks), "comments": list(comments), "reviews": list(reviews)}))
        (self.stub / "inline.json").write_text(json.dumps(list(inline)))

    def check(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), *args, str(self.run_dir)],
                                capture_output=True, text=True, env=self.env)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def test_waiting_gives_a_check_time_to_appear_after_a_push(self):
        # Just after a push the pull request has no checks yet; the failing one shows up seconds later.
        self.pr(checks=[BAD_CHECK])
        view = json.loads((self.stub / "view.json").read_text())
        (self.stub / "view-once.json").write_text(json.dumps({**view, "statusCheckRollup": []}))
        self.assertEqual(self.check("--wait", "60").returncode, 10)

    def test_green_with_no_feedback_needs_nothing(self):
        result = self.check()
        self.assertEqual(result.returncode, 0)
        self.assertIn("https://github.com/o/r/pull/7", result.stdout)
        self.assertEqual(list((self.run_dir / "reports").glob("pr-feedback-*.md")), [])

    def test_failing_check_needs_action_and_is_written_up_for_the_builder(self):
        self.pr(checks=[OK_CHECK, BAD_CHECK])
        result = self.check()
        self.assertEqual(result.returncode, 10)
        report = (self.run_dir / "reports" / "pr-feedback-1.md").read_text()
        self.assertIn("lint", report)
        self.assertIn("https://ci/2", report)
        self.assertNotIn("https://ci/1", report)   # passing checks are not feedback

    def test_checks_still_running_are_reported_as_pending(self):
        self.pr(checks=[RUNNING])
        self.assertEqual(self.check("--wait", "0").returncode, 20)

    def test_review_comment_needs_action_once(self):
        inline = [{"id": 11, "user": {"login": "rev"}, "path": "shop/cart.py", "line": 12, "body": "Rename this to qty."}]
        self.pr(checks=[OK_CHECK], inline=inline)
        first = self.check()
        self.assertEqual(first.returncode, 10)
        report = (self.run_dir / "reports" / "pr-feedback-1.md").read_text()
        self.assertIn("shop/cart.py:12", report)
        self.assertIn("Rename this to qty.", report)

        self.assertEqual(self.check("--mark-handled").returncode, 0)
        self.assertEqual(self.check().returncode, 0)             # dealt with: not raised again

        inline.append({"id": 12, "user": {"login": "rev"}, "path": "README.md", "line": 3, "body": "Typo."})
        self.pr(checks=[OK_CHECK], inline=inline)
        again = self.check()
        self.assertEqual(again.returncode, 10)
        second = (self.run_dir / "reports" / "pr-feedback-2.md").read_text()
        self.assertIn("Typo.", second)
        self.assertNotIn("Rename this to qty.", second)

    def test_conversation_comments_and_change_requests_count(self):
        self.pr(checks=[OK_CHECK],
                comments=[{"id": "c1", "author": {"login": "rev"}, "body": "Please also handle None."}],
                reviews=[{"id": "r1", "author": {"login": "rev"}, "state": "CHANGES_REQUESTED", "body": "See comments."},
                         {"id": "r2", "author": {"login": "rev"}, "state": "APPROVED", "body": ""}])
        result = self.check()
        self.assertEqual(result.returncode, 10)
        report = (self.run_dir / "reports" / "pr-feedback-1.md").read_text()
        self.assertIn("Please also handle None.", report)
        self.assertIn("See comments.", report)

    def test_the_teams_own_replies_are_not_feedback(self):
        self.pr(checks=[OK_CHECK], comments=[{"id": "c1", "author": {"login": "me"}, "body": "[swd] Renamed to qty in 1a2b3c."}])
        self.assertEqual(self.check().returncode, 0)

    def test_merged_pull_request_needs_nothing(self):
        self.pr(state="MERGED", checks=[BAD_CHECK])
        result = self.check()
        self.assertEqual(result.returncode, 0)
        self.assertIn("MERGED", result.stdout)

    def test_no_pull_request_is_an_error(self):
        (self.stub / "view.json").unlink()
        self.assertEqual(self.check().returncode, 1)

    def test_a_run_that_did_not_finish_with_a_pull_request_is_an_error(self):
        (self.run_dir / "decisions.md").write_text("Base commit: 0\nBranch: swd/demo\nFinish: branch\n")
        self.assertEqual(self.check().returncode, 1)


if __name__ == "__main__":
    unittest.main()
