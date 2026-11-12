"""Tests for scripts/swd-log.sh, which appends one timeline line to activity.md."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "swd-log.sh"


class LogTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name)

    def log(self, *args):
        return subprocess.run(["bash", str(SCRIPT), str(self.run_dir), *args], capture_output=True, text=True)

    def test_appends_a_clock_stamped_line(self):
        self.assertEqual(self.log("dispatch", "T1", "generalist-engineer").returncode, 0)
        self.assertEqual(self.log("return", "T1").returncode, 0)
        lines = (self.run_dir / "activity.md").read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^- \d{2}:\d{2}:\d{2} dispatch T1 generalist-engineer$")
        self.assertRegex(lines[1], r"^- \d{2}:\d{2}:\d{2} return T1$")

    def test_unknown_event_is_rejected(self):
        result = self.log("finished", "T1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown event", result.stderr)
        self.assertFalse((self.run_dir / "activity.md").exists())


if __name__ == "__main__":
    unittest.main()
