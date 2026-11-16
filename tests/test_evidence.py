"""Tests for scripts/swd-test.py: it runs a run's test command and records what really happened."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "swd-test.py"

# The plan's commands are written for sh (Git Bash on Windows), so this Python is named the way sh reads it there too.
PYTHON = '"%s"' % Path(sys.executable).as_posix()

PLAN = f"""# Plan

Test command: `{PYTHON} suite.py`

### T1: First thing
- Role: generalist-engineer
- Wave: 1
- Files: a.py
- Depends: none
- Check: `{PYTHON} check_a.py`

### T2: Shell syntax
- Role: generalist-engineer
- Wave: 1
- Files: b.py
- Depends: none
- Check: `echo one; echo two`
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
        (self.run_dir / "plan.md").write_text(PLAN, encoding="utf-8")
        (self.run_dir / "decisions.md").write_text(f"Base commit: 0\nWorktree: {self.work}\n", encoding="utf-8")
        self.script("check_a.py", "import sys; print('a is missing'); sys.exit(1)")
        self.script("suite.py", "print('Ran 3 tests'); print('OK')")

    def script(self, name, body):
        (self.work / name).write_text(body + "\n", encoding="utf-8")

    def run_label(self, label):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.run_dir), label],
                              capture_output=True, text=True, encoding="utf-8")

    def record(self, name):
        return (self.run_dir / "evidence" / name).read_text(encoding="utf-8")

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
        first = self.record("T1-001.txt")
        self.assertIn(f"Command: {PYTHON} check_a.py", first)
        self.assertIn("Exit: 1", first)
        self.assertIn("a is missing", first)
        self.assertIn("Exit: 0", self.record("T1-002.txt"))

    def test_wave_and_final_labels_run_the_whole_test_command_in_the_worktree(self):
        for label in ("wave-1", "final"):
            with self.subTest(label=label):
                result = self.run_label(label)
                self.assertEqual(result.returncode, 0)
                self.assertIn("Ran 3 tests", result.stdout)
                self.assertIn(f"Command: {PYTHON} suite.py", self.record(f"{label}-001.txt"))

    def test_the_command_runs_in_sh_on_every_system(self):
        # cmd.exe, what shell=True means on Windows, would print "one; echo two" as one line.
        result = self.run_label("T2")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.splitlines()[:2], ["one", "two"])
        self.assertEqual(self.record("T2-001.txt").split("\n---\n", 1)[1], "one\ntwo\n")

    def test_non_ascii_output_is_recorded_and_printed_as_utf8(self):
        self.script("suite.py", "import sys; sys.stdout.buffer.write('caf\\u00e9 \\u2014 done\\n'.encode('utf-8'))")
        result = self.run_label("final")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("café — done", result.stdout)
        self.assertIn("café — done", self.record("final-001.txt"))

    def test_long_output_keeps_its_end(self):
        self.script("suite.py", "for i in range(5000): print('line', i)\nprint('FAILED (failures=2)')\nraise SystemExit(1)")
        result = self.run_label("final")
        self.assertEqual(result.returncode, 1)
        recorded = self.record("final-001.txt")
        self.assertIn("FAILED (failures=2)", recorded)
        self.assertLess(len(recorded.splitlines()), 400)

    def test_unknown_label_or_task_is_an_error_and_records_nothing(self):
        for label in ("T9", "nonsense"):
            with self.subTest(label=label):
                result = self.run_label(label)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.run_dir / "evidence").exists())


class WindowsShTest(unittest.TestCase):
    """On Windows the command runs in the first sh.exe on an absolute PATH entry, never one from the project."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.addCleanup(os.chdir, os.getcwd())   # runs before the cleanup above, so Windows can delete the folder
        self.project = self.folder("project", "sh.exe")
        os.chdir(self.project)
        spec = importlib.util.spec_from_file_location("swd_test", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def folder(self, name, *files):
        path = self.tmp / name
        path.mkdir()
        for file in files:
            (path / file).write_text("", encoding="utf-8")
        return path

    def windows_sh(self, *entries):
        with mock.patch.dict(os.environ, {"PATH": os.pathsep.join(str(entry) for entry in entries)}):
            return self.module.windows_sh()

    def test_the_first_absolute_entry_holding_sh_exe_wins(self):
        git = self.folder("git", "sh.exe")
        later = self.folder("later", "sh.exe")
        self.assertEqual(self.windows_sh("", ".", self.project, git, later), os.path.join(str(git), "sh.exe"))

    def test_the_current_folder_empty_and_relative_entries_and_other_shells_are_never_taken(self):
        self.folder("relative", "sh.exe")
        scripts = self.folder("scripts", "sh.bat", "sh.cmd", "sh")
        self.assertIsNone(self.windows_sh("", ".", os.path.join("..", "relative"), self.project, scripts))
        self.assertIsNone(self.windows_sh())


if __name__ == "__main__":
    unittest.main()
