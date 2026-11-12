"""Tests for scripts/swd-test.py: it runs a run's test command and records what really happened."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "swd-test.py"

PLAN = """# Plan

Test command: `python3 suite.py`

### T1: First thing
- Role: generalist-engineer
- Wave: 1
- Files: a.py
- Depends: none
- Check: `python3 check_a.py`
"""


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name).resolve()
        self.work = tmp / "work"
        self.work.mkdir()
        self.run_dir = tmp / "project" / ".swd" / "runs" / "2026-11-12-demo"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "plan.md").write_text(PLAN)
        (self.run_dir / "decisions.md").write_text(f"Base commit: 0\nWorktree: {self.work}\n")
        self.script("check_a.py", "import sys; print('a is missing'); sys.exit(1)")
        self.script("suite.py", "print('Ran 3 tests'); print('OK')")

    def script(self, name, body):
        (self.work / name).write_text(body + "\n")

    def run_label(self, label):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.run_dir), label], capture_output=True, text=True)

    def evidence(self):
        return sorted(p.name for p in (self.run_dir / "evidence").glob("*.txt"))

    def test_a_failing_then_passing_check_is_recorded_in_order(self):
        failing = self.run_label("T1")
        self.assertEqual(failing.returncode, 1)
        self.assertIn("a is missing", failing.stdout)
        self.script("check_a.py", "print('a works')")
        passing = self.run_label("T1")
        self.assertEqual(passing.returncode, 0)
        self.assertEqual(self.evidence(), ["T1-001.txt", "T1-002.txt"])
        first = (self.run_dir / "evidence" / "T1-001.txt").read_text()
        self.assertIn("Command: python3 check_a.py", first)
        self.assertIn("Exit: 1", first)
        self.assertIn("a is missing", first)
        self.assertIn("Exit: 0", (self.run_dir / "evidence" / "T1-002.txt").read_text())

    def test_wave_and_final_labels_run_the_whole_test_command_in_the_worktree(self):
        for label in ("wave-1", "final"):
            with self.subTest(label=label):
                result = self.run_label(label)
                self.assertEqual(result.returncode, 0)
                self.assertIn("Ran 3 tests", result.stdout)
                self.assertIn("Command: python3 suite.py", (self.run_dir / "evidence" / f"{label}-001.txt").read_text())

    def test_long_output_keeps_its_end(self):
        self.script("suite.py", "for i in range(5000): print('line', i)\nprint('FAILED (failures=2)')\nraise SystemExit(1)")
        result = self.run_label("final")
        self.assertEqual(result.returncode, 1)
        recorded = (self.run_dir / "evidence" / "final-001.txt").read_text()
        self.assertIn("FAILED (failures=2)", recorded)
        self.assertLess(len(recorded.splitlines()), 400)

    def test_unknown_label_or_task_is_an_error_and_records_nothing(self):
        for label in ("T9", "nonsense"):
            with self.subTest(label=label):
                result = self.run_label(label)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.run_dir / "evidence").exists())


if __name__ == "__main__":
    unittest.main()
