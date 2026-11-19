"""Tests for scripts/swd-test.py: it runs a run's test command and records what really happened."""
import errno
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
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


def parallel_env(value):
    """The environment for a child, with SWD_PARALLEL set to value, so the real one never decides a result."""
    return {**os.environ, "SWD_PARALLEL": value}


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

    parallel = "none"   # SWD_PARALLEL for the child; the capped subclass below runs every case again with a cap

    def run_label(self, label):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.run_dir), label],
                              capture_output=True, text=True, encoding="utf-8", env=parallel_env(self.parallel))

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


class CappedEvidenceTest(EvidenceTest):
    """Every case above again with a cap: output, evidence and exit codes are the same."""
    parallel = "1"


# Each test command writes its pid to pid-<label>, appends "start <label>" to the marks file, waits for the
# release file, appends "end <label>". A label that is not T1 does not wait, so a second run can finish while
# the first is held.
MARK = """import os, sys, time
label = sys.argv[1]
with open(os.path.join({pids!r}, "pid-" + label), "w") as f:
    f.write(str(os.getpid()))
def mark(word):
    with open({marks!r}, "a") as f:
        f.write(word + " " + label + "\\n")
mark("start")
deadline = time.time() + 20
while label == "T1" and not os.path.exists({release!r}) and time.time() < deadline:
    time.sleep(0.05)
mark("end")
"""
WAITING = "waiting for another test run of this project to end"
REFUSED = ("cannot use .swd/test.lock as the test lock: it is a link, not a regular file, or cannot be opened; "
           "remove it and run again\n")
NO_LOCK = "could not lock .swd/test.lock on this file system; running this test without the lock\n"

# Runs swd-test.py with the OS lock call replaced by one that fails as a file system without lock support does.
NO_LOCK_SUPPORT = """import errno, os, runpy, sys
def fail(*args):
    raise OSError(errno.EINVAL if os.name == "nt" else errno.ENOLCK, "no lock support")
if os.name == "nt":
    import msvcrt
    msvcrt.locking = fail
else:
    import fcntl
    fcntl.flock = fail
sys.argv = [{script!r}, {run_dir!r}, {label!r}]
runpy.run_path({script!r}, run_name="__main__")
"""


def remove_tree(path):
    """shutil.rmtree, retried for up to 10 s: on Windows a folder cannot go while a process still works in it."""
    deadline = time.time() + 10
    while True:
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if time.time() > deadline:
                raise
            time.sleep(0.1)


class LockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(remove_tree, self.tmp)   # first, so it runs last, after stop_all
        self.marks = self.tmp / "marks.txt"
        self.release = self.tmp / "release"
        self.procs = []
        self.addCleanup(self.stop_all)

    def stop_all(self):
        self.release.write_text("", encoding="utf-8")   # lets any command still waiting end
        for proc in self.procs:
            if proc.poll() is None:   # one a test left unfinished
                proc.kill()
                proc.communicate()

    def project(self, name):
        """A project with a run whose T1 and T2 both run mark.py, and its run folder."""
        work = self.tmp / name / "work"
        work.mkdir(parents=True)
        run_dir = self.tmp / name / "project" / ".swd" / "runs" / "2026-11-12-demo"
        run_dir.mkdir(parents=True)
        (work / "mark.py").write_text(MARK.format(marks=str(self.marks), release=str(self.release), pids=str(self.tmp)),
                                      encoding="utf-8")
        tasks = "".join(f"### {t}: Task\n- Role: generalist-engineer\n- Wave: 1\n- Files: a.py\n- Depends: none\n"
                        f"- Check: `{PYTHON} mark.py {t}`\n\n" for t in ("T1", "T2"))
        (run_dir / "plan.md").write_text(f"# Plan\n\nTest command: `true`\n\n{tasks}", encoding="utf-8")
        (run_dir / "decisions.md").write_text(f"Base commit: 0\nWorktree: {work}\n", encoding="utf-8")
        return run_dir

    def start(self, run_dir, label, parallel="1"):
        proc = subprocess.Popen([sys.executable, str(SCRIPT), str(run_dir), label], stdout=subprocess.PIPE,
                                text=True, encoding="utf-8", env=parallel_env(parallel))
        self.procs.append(proc)
        return proc

    def marked(self):
        return self.marks.read_text(encoding="utf-8").splitlines() if self.marks.exists() else []

    def wait_for(self, mark):
        deadline = time.time() + 20
        while mark not in self.marked():
            self.assertLess(time.time(), deadline, f"{mark!r} never appeared in {self.marked()}")
            time.sleep(0.05)

    def exit_of(self, run_dir, name):
        return (run_dir / "evidence" / name).read_text(encoding="utf-8").splitlines()[1]

    def test_two_runs_of_one_project_do_not_overlap(self):
        run_dir = self.project("p")
        first = self.start(run_dir, "T1")
        self.wait_for("start T1")
        second = self.start(run_dir, "T2")
        self.assertEqual(second.stdout.readline().rstrip("\n"), WAITING)   # it is waiting, and has said so
        self.assertEqual(self.marked(), ["start T1"])
        self.release.write_text("", encoding="utf-8")
        first_out, second_out = first.communicate()[0], second.communicate()[0]
        self.assertEqual(self.marked(), ["start T1", "end T1", "start T2", "end T2"])
        self.assertNotIn(WAITING, first_out)
        self.assertEqual(second_out.count(WAITING), 0)   # the one line was read above and printed once
        self.assertEqual((first.returncode, second.returncode), (0, 0))
        self.assertEqual((self.exit_of(run_dir, "T1-001.txt"), self.exit_of(run_dir, "T2-001.txt")), ("Exit: 0", "Exit: 0"))
        self.assertTrue((run_dir.parents[1] / "test.lock").is_file())

    def test_a_holder_that_dies_leaves_no_wait_even_while_its_command_runs(self):
        run_dir = self.project("p")
        first = self.start(run_dir, "T1")
        self.wait_for("start T1")
        first.kill()
        first.communicate()   # on POSIX the lock went with the holder's descriptors, before it could be reaped
        if os.name == "nt":
            self.wait_for_windows_release(run_dir.parents[1] / "test.lock")
        second = self.start(run_dir, "T2")
        out = second.communicate()[0]
        self.assertNotIn(WAITING, out)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(self.marked(), ["start T1", "start T2", "end T2"])   # the orphaned T1 command is still running
        self.release.write_text("", encoding="utf-8")
        self.wait_for("end T1")   # and it ends on its own
        # The test does not end while the orphan runs in the temporary folder. On Windows, where os.kill would
        # terminate it, the retrying cleanup is the wait: the folder cannot go while sh.exe or python works in it.
        if os.name != "nt":
            pid, deadline = int((self.tmp / "pid-T1").read_text(encoding="utf-8")), time.time() + 20
            while True:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                self.assertLess(time.time(), deadline, f"the orphaned test command {pid} never exited")
                time.sleep(0.05)

    def wait_for_windows_release(self, lock):
        """Windows releases a dead process's lock when resources allow: wait up to 10 s until it can be taken, then
        unlock it explicitly, so the next run never waits on this probe."""
        import msvcrt
        fd = os.open(lock, os.O_RDWR)
        try:
            deadline = time.time() + 10
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EDEADLOCK):   # held, as swd-test.py counts it
                        raise
                    self.assertLess(time.time(), deadline, "the killed holder's lock was never released")
                    time.sleep(0.1)
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)

    def run_once(self, run_dir, label, command=None):
        """One capped run to its end, standard output and standard error captured."""
        return subprocess.run(command or [sys.executable, str(SCRIPT), str(run_dir), label],
                              capture_output=True, text=True, encoding="utf-8", env=parallel_env("1"))

    def assertRefused(self, run_dir, result):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (2, "", REFUSED))
        self.assertFalse((run_dir / "evidence").exists())
        self.assertEqual(self.marked(), [])   # the test command never ran

    def test_a_link_planted_at_the_lock_is_refused_and_its_target_is_not_created(self):
        run_dir = self.project("p")
        target = self.tmp / "outside" / "made-by-the-lock"
        try:
            os.symlink(target, run_dir.parents[1] / "test.lock")
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"cannot make a symlink here: {error}")
        self.assertRefused(run_dir, self.run_once(run_dir, "T2"))
        self.assertFalse(target.exists())
        self.assertFalse(target.parent.exists())

    def test_a_folder_at_the_lock_is_refused(self):
        run_dir = self.project("p")
        (run_dir.parents[1] / "test.lock").mkdir()
        self.assertRefused(run_dir, self.run_once(run_dir, "T2"))

    def test_a_lock_the_file_system_cannot_take_still_runs_and_records_the_command(self):
        run_dir = self.project("p")
        with open(run_dir.parents[3] / "work" / "mark.py", "a", encoding="utf-8") as f:
            f.write("raise SystemExit(3)\n")   # so the exit code shown is the command's
        child = NO_LOCK_SUPPORT.format(script=str(SCRIPT), run_dir=str(run_dir), label="T2")
        result = self.run_once(run_dir, "T2", [sys.executable, "-c", child])
        self.assertEqual((result.returncode, result.stderr), (3, NO_LOCK))
        self.assertNotIn(WAITING, result.stdout)
        self.assertIn("exit 3; recorded in evidence/T2-001.txt", result.stdout)
        self.assertEqual(self.exit_of(run_dir, "T2-001.txt"), "Exit: 3")
        self.assertEqual(self.marked(), ["start T2", "end T2"])

    def test_two_projects_overlap(self):
        first_dir, second_dir = self.project("a"), self.project("b")
        first = self.start(first_dir, "T1")
        self.wait_for("start T1")
        second = self.start(second_dir, "T2")
        out = second.communicate()[0]
        self.assertNotIn(WAITING, out)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(self.marked(), ["start T1", "start T2", "end T2"])   # T2 ended while T1 was held
        self.release.write_text("", encoding="utf-8")
        self.assertEqual(first.communicate()[0].count(WAITING), 0)
        self.assertEqual(first.returncode, 0)

    def test_without_a_cap_two_runs_of_one_project_overlap_and_no_lock_is_made(self):
        run_dir = self.project("p")
        first = self.start(run_dir, "T1", "none")
        self.wait_for("start T1")
        second = self.start(run_dir, "T2", "none")
        out = second.communicate()[0]
        self.assertNotIn(WAITING, out)
        self.assertEqual(self.marked(), ["start T1", "start T2", "end T2"])
        self.release.write_text("", encoding="utf-8")
        self.assertNotIn(WAITING, first.communicate()[0])
        self.assertFalse((run_dir.parents[1] / "test.lock").exists())


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
