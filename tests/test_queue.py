"""Tests for scripts/swd-queue.py: work through .swd/queue.md, one headless run per item.

`claude` and `gh` are stubs. The stub claude plays a finished run that left its branch.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "swd-queue.py"

# Records its prompt; unless told to fail, creates a branch and a finished run folder for it.
CLAUDE_STUB = r"""#!/bin/sh
n=$(($(cat "$STUB_DIR/count" 2>/dev/null || echo 0) + 1)); echo $n > "$STUB_DIR/count"
for last; do :; done
printf '%s\n' "$last" > "$STUB_DIR/prompt-$n.txt"
if grep -q "$STUB_FAIL_ON" "$STUB_DIR/prompt-$n.txt" 2>/dev/null && [ -n "$STUB_FAIL_ON" ]; then exit 0; fi
git branch -q "swd/item-$n"
run=".swd/runs/2026-11-12-item-$n"; mkdir -p "$run"
printf 'Base commit: 0\nBase branch: main\nBranch: swd/item-%s\nWorktree: /nowhere/item-%s\nFinish: branch\n' $n $n > "$run/decisions.md"
printf '| Task | Role | Status | Attempts |\n|---|---|---|---|\n| T1 | generalist-engineer | done | 1 |\n' > "$run/ledger.md"
printf -- '- 10:00:00 dispatch T1 generalist-engineer\n- 10:05:00 done\n' > "$run/activity.md"
"""

GH_STUB = r"""#!/bin/sh
[ "$1 $2" = "issue view" ] && echo '{"title": "Carts lose items", "body": "Steps: add two, see one."}' && exit 0
exit 1
"""

QUEUE = """# Queue

Finish: branch

- [ ] Add item_count to the cart
- [x] Already done earlier
- [ ] #12
- [ ] Add a changelog
"""


class QueueTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name).resolve()
        self.project = tmp / "project"
        (self.project / ".swd").mkdir(parents=True)
        run = lambda *a: subprocess.run(["git", "-C", str(self.project), "-c", "user.name=t", "-c", "user.email=t@e.x",
                                         *a], check=True, capture_output=True)
        run("init", "-q", "-b", "main")
        run("commit", "-q", "--allow-empty", "-m", "Initial commit")
        self.queue = self.project / ".swd" / "queue.md"
        self.queue.write_text(QUEUE)
        self.stub = tmp / "stub"
        self.stub.mkdir()
        (tmp / "bin").mkdir()
        for name, body in (("claude", CLAUDE_STUB), ("gh", GH_STUB)):
            (tmp / "bin" / name).write_text(body)
            (tmp / "bin" / name).chmod(0o755)
        self.env = {**os.environ, "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "STUB_DIR": str(self.stub),
                    "STUB_FAIL_ON": ""}

    def work(self, *args, **env):
        result = subprocess.run([sys.executable, str(SCRIPT), *args, str(self.project)], capture_output=True, text=True,
                                env={**self.env, **env})
        self.assertNotIn("Traceback", result.stderr)
        return result

    def prompts(self):
        return [p.read_text() for p in sorted(self.stub.glob("prompt-*.txt"))]

    def test_dry_run_lists_open_items_and_starts_nothing(self):
        result = self.work("--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Add item_count to the cart", result.stdout)
        self.assertIn("#12", result.stdout)
        self.assertNotIn("Already done earlier", result.stdout)
        self.assertEqual(self.prompts(), [])

    def test_each_open_item_becomes_one_pre_approved_run_and_is_ticked_off(self):
        self.assertEqual(self.work().returncode, 0)
        prompts = self.prompts()
        self.assertEqual(len(prompts), 3)
        for prompt in prompts:
            self.assertTrue(prompt.startswith("/swd:build "))
            self.assertIn("I pre-approve the spec and plan", prompt)
            self.assertIn("leave the branch", prompt)             # the queue's Finish: branch
        text = self.queue.read_text()
        self.assertIn("- [x] Add item_count to the cart — swd/item-1", text)
        self.assertIn("- [x] Add a changelog — swd/item-3", text)
        self.assertNotIn("- [ ]", text)
        self.assertIn("3 done", (self.project / ".swd" / "queue-report.md").read_text())

    def test_an_issue_item_carries_the_issue_text_and_asks_for_a_closing_reference(self):
        self.work()
        issue = self.prompts()[1]
        self.assertIn("Carts lose items", issue)
        self.assertIn("Steps: add two, see one.", issue)
        self.assertIn("Closes #12", issue)

    def test_a_run_that_does_not_finish_is_marked_blocked_and_the_queue_moves_on(self):
        self.work(STUB_FAIL_ON="item_count")
        text = self.queue.read_text()
        self.assertRegex(text, r"- \[!\] Add item_count to the cart — blocked")
        self.assertIn("- [x] Add a changelog", text)

    def test_two_failures_in_a_row_stop_the_queue(self):
        # Something systemic is wrong, such as permissions; do not burn through the rest.
        self.queue.write_text("- [ ] bad one\n- [ ] bad two\n- [ ] never started\n")
        result = self.work(STUB_FAIL_ON="bad")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(self.prompts()), 2)
        self.assertIn("- [ ] never started", self.queue.read_text())

    def test_max_limits_how_many_items_run(self):
        self.work("--max", "1")
        self.assertEqual(len(self.prompts()), 1)
        self.assertIn("- [ ] Add a changelog", self.queue.read_text())

    def test_no_queue_file_is_an_error(self):
        self.queue.unlink()
        self.assertEqual(self.work().returncode, 1)


if __name__ == "__main__":
    unittest.main()
