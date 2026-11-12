"""Tests for scripts/swd-findings.py: a run's findings are copied to the project's backlog."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "swd-findings.py"


class FindingsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name) / ".swd" / "runs" / "2026-11-12-cart-total"
        self.run_dir.mkdir(parents=True)
        self.backlog = Path(self._tmp.name) / ".swd" / "findings.md"
        (self.run_dir / "decisions.md").write_text(
            "Base commit: 0\nRuling: something else.\n"
            "Finding: apply_discount subtracts the percent as an amount.\n"
            "Finding: total() raises TypeError for a string percent.\n")

    def sync(self, run_dir=None):
        result = subprocess.run([sys.executable, str(SCRIPT), str(run_dir or self.run_dir)], capture_output=True, text=True)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def test_findings_are_added_as_open_items_naming_the_run(self):
        self.assertEqual(self.sync().returncode, 0)
        lines = [l for l in self.backlog.read_text().splitlines() if l.startswith("- [")]
        self.assertEqual(lines, [
            "- [ ] apply_discount subtracts the percent as an amount. (2026-11-12-cart-total)",
            "- [ ] total() raises TypeError for a string percent. (2026-11-12-cart-total)",
        ])

    def test_running_it_twice_adds_nothing(self):
        self.sync()
        before = self.backlog.read_text()
        self.sync()
        self.assertEqual(self.backlog.read_text(), before)

    def test_an_item_the_user_ticked_off_stays_ticked_and_is_not_added_again(self):
        self.sync()
        self.backlog.write_text(self.backlog.read_text().replace("- [ ] apply_discount", "- [x] apply_discount"))
        self.sync()
        text = self.backlog.read_text()
        self.assertEqual(text.count("apply_discount subtracts"), 1)
        self.assertIn("- [x] apply_discount", text)

    def test_a_run_with_no_findings_leaves_no_file(self):
        (self.run_dir / "decisions.md").write_text("Base commit: 0\n")
        self.assertEqual(self.sync().returncode, 0)
        self.assertFalse(self.backlog.exists())

    def test_not_a_run_folder_is_an_error(self):
        self.assertEqual(self.sync(Path(self._tmp.name)).returncode, 1)


if __name__ == "__main__":
    unittest.main()
