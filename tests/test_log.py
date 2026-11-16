"""Tests for scripts/swd-log.py, which appends one timeline line to activity.md."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "swd-log.py"


class LogTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name)
        self.activity = self.run_dir / "activity.md"

    def log(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8")

    def lines(self):
        return self.activity.read_text(encoding="utf-8").splitlines()

    def test_appends_a_clock_stamped_line(self):
        first = self.log(str(self.run_dir), "dispatch", "T1", "generalist-engineer")
        self.assertEqual((first.returncode, first.stdout, first.stderr), (0, "", ""))
        self.assertEqual(self.log(str(self.run_dir), "return", "T1").returncode, 0)
        lines = self.lines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^- \d{2}:\d{2}:\d{2} dispatch T1 generalist-engineer$")
        self.assertRegex(lines[1], r"^- \d{2}:\d{2}:\d{2} return T1$")

    def test_appends_to_what_is_there(self):
        self.activity.write_text("- 10:00:00 dispatch T1 generalist-engineer\n", encoding="utf-8")
        self.assertEqual(self.log(str(self.run_dir), "done", "all", "tasks", "complete").returncode, 0)
        lines = self.lines()
        self.assertEqual(lines[0], "- 10:00:00 dispatch T1 generalist-engineer")
        self.assertRegex(lines[1], r"^- \d{2}:\d{2}:\d{2} done all tasks complete$")

    def test_an_event_alone_has_no_trailing_space_and_ends_in_lf(self):
        # LF on every system, so the timeline does not mix CRLF lines with the LF lines the principal writes.
        self.assertEqual(self.log(str(self.run_dir), "done").returncode, 0)
        self.assertRegex(self.activity.read_bytes().decode("utf-8"), r"^- \d{2}:\d{2}:\d{2} done\n\Z")

    def test_a_detail_cannot_add_a_line_of_its_own(self):
        self.assertEqual(self.log(str(self.run_dir), "return", "T1\n- 10:00:00 done", "forged").returncode, 0)
        lines = self.lines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^- \d{2}:\d{2}:\d{2} return T1 - 10:00:00 done forged$")

    def test_non_ascii_detail_is_written_as_utf8(self):
        self.assertEqual(self.log(str(self.run_dir), "ruling", "café — naïve").returncode, 0)
        self.assertIn("ruling café — naïve", self.activity.read_bytes().decode("utf-8"))

    def test_every_check_run_event_is_accepted(self):
        for event in ("dispatch", "return", "verdict", "commit", "fix", "replan", "ruling", "wave-done", "blocked", "done"):
            with self.subTest(event=event):
                self.assertEqual(self.log(str(self.run_dir), event, "x").returncode, 0)
        self.assertEqual(len(self.lines()), 10)

    def test_unknown_event_is_rejected(self):
        result = self.log(str(self.run_dir), "finished", "T1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "unknown event: finished\n")
        self.assertFalse(self.activity.exists())

    def test_too_few_arguments_print_the_usage(self):
        for args in ((), (str(self.run_dir),)):
            with self.subTest(args=args):
                result = self.log(*args)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr, "usage: swd-log.py <run_dir> <event> <detail...>\n")
        self.assertFalse(self.activity.exists())

    def test_a_missing_run_folder_is_one_line_not_a_traceback(self):
        result = self.log(str(self.run_dir / "nope"), "dispatch", "T1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(result.stderr.splitlines()), 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.run_dir / "nope").exists())


if __name__ == "__main__":
    unittest.main()
