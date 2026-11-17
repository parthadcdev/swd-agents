"""Tests for scripts/swd-queue.py: work through .swd/queue.md, one headless run per item.

`claude` and `gh` are stubs. The stub claude plays a finished run that left its branch.
HOME and USERPROFILE are a temporary folder in every run, so no test reads or writes the real
~/.claude; the conductor setting is stored there by the real hook, as a typed /swd:conductor would.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "swd-queue.py"
HOOK = ROOT / "hooks" / "swd-mode.py"

# Records its prompt; unless told to fail, creates a branch and a finished run folder for it.
CLAUDE_STUB = r"""#!/bin/sh
n=$(($(cat "$STUB_DIR/count" 2>/dev/null || echo 0) + 1)); echo $n > "$STUB_DIR/count"
for last; do :; done
printf '%s\n' "$last" > "$STUB_DIR/prompt-$n.txt"
printf '%s\n' "$*" > "$STUB_DIR/args-$n.txt"
printf '%s\n' "${SWD_UNATTENDED-unset}" > "$STUB_DIR/unattended-$n.txt"
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

# A dry run starts nothing, so those tests run everywhere; a real run needs the stub claude.
NO_STUBS = "the stub is a shell script, and Windows starts only .exe programs by name"
stubbed = unittest.skipIf(os.name == "nt", NO_STUBS)

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
        self.queue.write_text(QUEUE, encoding="utf-8")
        self.stub = tmp / "stub"
        self.stub.mkdir()
        (tmp / "bin").mkdir()
        for name, body in (("claude", CLAUDE_STUB), ("gh", GH_STUB)):
            (tmp / "bin" / name).write_text(body, encoding="utf-8")
            (tmp / "bin" / name).chmod(0o755)
        self.home = tmp / "home"
        self.home.mkdir()
        self.env = {**os.environ, "PATH": f"{tmp / 'bin'}{os.pathsep}{os.environ['PATH']}", "STUB_DIR": str(self.stub),
                    "STUB_FAIL_ON": "", "HOME": str(self.home), "USERPROFILE": str(self.home)}

    def set_conductor(self, value, project=None):
        """Store the setting through the hook, as a typed /swd:conductor in the project would."""
        event = {"hook_event_name": "UserPromptExpansion", "session_id": "s1", "cwd": str(project or self.project),
                 "expansion_type": "slash_command", "command_name": "swd:conductor", "command_args": value,
                 "prompt": f"/swd:conductor {value}"}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True,
                                env=self.env, encoding="utf-8")
        self.assertTrue(result.stdout.startswith(f"swd conductor: set to {value}\n"), result.stdout + result.stderr)

    def real_runs_need_the_stubs(self):
        if os.name == "nt":
            self.skipTest(NO_STUBS)

    def work(self, *args, **env):
        result = subprocess.run([sys.executable, str(SCRIPT), *args, str(self.project)], capture_output=True, text=True,
                                env={**self.env, **env}, encoding="utf-8")
        self.assertNotIn("Traceback", result.stderr)
        return result

    def prompts(self):
        return [p.read_text(encoding="utf-8") for p in sorted(self.stub.glob("prompt-*.txt"))]

    def test_dry_run_lists_open_items_and_starts_nothing(self):
        result = self.work("--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Add item_count to the cart", result.stdout)
        self.assertIn("#12", result.stdout)
        self.assertNotIn("Already done earlier", result.stdout)
        self.assertIn("finish: branch, model: fable", result.stdout)
        self.assertNotIn("ignoring", result.stdout)
        self.assertEqual(self.prompts(), [])

    @stubbed
    def test_each_open_item_becomes_one_pre_approved_run_and_is_ticked_off(self):
        self.assertEqual(self.work().returncode, 0)
        prompts = self.prompts()
        self.assertEqual(len(prompts), 3)
        for prompt in prompts:
            self.assertTrue(prompt.startswith("/swd:build "))
            self.assertIn("I pre-approve the spec and plan", prompt)
            self.assertIn("leave the branch", prompt)             # the queue's Finish: branch
        text = self.queue.read_text(encoding="utf-8")
        self.assertIn("- [x] Add item_count to the cart — swd/item-1", text)
        self.assertIn("- [x] Add a changelog — swd/item-3", text)
        self.assertNotIn("- [ ]", text)
        self.assertIn("3 done", (self.project / ".swd" / "queue-report.md").read_text(encoding="utf-8"))

    def unattended(self):
        return [p.read_text(encoding="utf-8") for p in sorted(self.stub.glob("unattended-*.txt"))]

    @stubbed
    def test_every_run_is_marked_unattended_with_its_model(self):
        self.env.pop("SWD_UNATTENDED", None)
        self.assertEqual(self.work().returncode, 0)
        self.assertEqual(self.unattended(), ["fable\n"] * 3)

    @stubbed
    def test_under_opus_every_run_is_marked_unattended_on_opus(self):
        self.env.pop("SWD_UNATTENDED", None)
        self.set_conductor("opus")
        self.assertEqual(self.work().returncode, 0)
        self.assertEqual(self.unattended(), ["opus\n"] * 3)
        self.assertEqual(len(self.runs_args()), 3)
        for line in self.runs_args():
            self.assertIn("--model opus", line)   # the same value as --model

    @stubbed
    def test_the_mark_is_the_queues_model_whatever_the_caller_set(self):
        for setting, caller in (("fable", "0"), ("fable", ""), ("fable", "opus"), ("opus", "fable"), ("opus", "1")):
            with self.subTest(setting=setting, caller=caller):
                self.set_conductor(setting)
                self.queue.write_text(QUEUE, encoding="utf-8")
                for old in self.stub.glob("unattended-*.txt"):
                    old.unlink()
                self.assertEqual(self.work(SWD_UNATTENDED=caller).returncode, 0)
                self.assertEqual(self.unattended(), [f"{setting}\n"] * 3)

    def test_dry_run_starts_nothing_unattended(self):
        self.assertEqual(self.work("--dry-run").returncode, 0)
        self.assertEqual(self.unattended(), [])

    def test_docstring_says_runs_are_marked_unattended_with_their_model(self):
        doc = " ".join(SCRIPT.read_text(encoding="utf-8").split('"""')[1].split())
        self.assertIn("SWD_UNATTENDED set to that model", doc)
        self.assertIn("check_run.py", doc)
        self.assertNotIn("SWD_UNATTENDED=1", doc)

    @stubbed
    def test_an_issue_item_carries_the_issue_text_and_asks_for_a_closing_reference(self):
        self.work()
        issue = self.prompts()[1]
        self.assertIn("Carts lose items", issue)
        self.assertIn("Steps: add two, see one.", issue)
        self.assertIn("Closes #12", issue)

    @stubbed
    def test_a_run_that_does_not_finish_is_marked_blocked_and_the_queue_moves_on(self):
        self.work(STUB_FAIL_ON="item_count")
        text = self.queue.read_text(encoding="utf-8")
        self.assertRegex(text, r"- \[!\] Add item_count to the cart — blocked")
        self.assertIn("- [x] Add a changelog", text)

    @stubbed
    def test_two_failures_in_a_row_stop_the_queue(self):
        # Something systemic is wrong, such as permissions; do not burn through the rest.
        self.queue.write_text("- [ ] bad one\n- [ ] bad two\n- [ ] never started\n", encoding="utf-8")
        result = self.work(STUB_FAIL_ON="bad")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(self.prompts()), 2)
        self.assertIn("- [ ] never started", self.queue.read_text(encoding="utf-8"))

    IGNORED = "ignoring 'Model: sonnet' in .swd/queue.md: every run starts with --model fable"

    @stubbed
    def test_every_run_starts_on_fable_without_a_model_line(self):
        result = self.work()
        self.assertNotIn("ignoring", result.stdout)
        args = [p.read_text(encoding="utf-8") for p in sorted(self.stub.glob("args-*.txt"))]
        self.assertEqual(len(args), 3)
        for line in args:
            self.assertIn("--model fable", line)
        self.assertEqual(result.stdout.splitlines(), [
            "starting with --model fable: Add item_count to the cart", "- [x] Add item_count to the cart — swd/item-1",
            "starting with --model fable: #12", "- [x] #12 — swd/item-2",
            "starting with --model fable: Add a changelog", "- [x] Add a changelog — swd/item-3"])

    @stubbed
    def test_under_opus_every_run_starts_with_model_opus_and_says_so_before_it_starts(self):
        self.set_conductor("opus")
        result = self.work()
        self.assertEqual(result.returncode, 0)
        args = self.runs_args()
        self.assertEqual(len(args), 3)
        for line in args:
            self.assertIn("--model opus", line)
            self.assertNotIn("fable", line)
        self.assertEqual(result.stdout.splitlines(), [
            "starting with --model opus: Add item_count to the cart", "- [x] Add item_count to the cart — swd/item-1",
            "starting with --model opus: #12", "- [x] #12 — swd/item-2",
            "starting with --model opus: Add a changelog", "- [x] Add a changelog — swd/item-3"])

    def test_dry_run_under_opus_names_opus(self):
        self.set_conductor("opus")
        result = self.work("--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[0], "3 open items, finish: branch, model: opus")
        self.assertEqual(self.prompts(), [])

    def test_setting_fable_again_gives_fable(self):
        self.set_conductor("opus")
        self.set_conductor("fable")
        self.assertIn("finish: branch, model: fable", self.work("--dry-run").stdout)

    def test_another_project_under_the_same_home_stays_on_fable(self):
        other = self.project.parent / "other"
        (other / ".swd").mkdir(parents=True)
        (other / ".swd" / "queue.md").write_text("- [ ] one\n", encoding="utf-8")
        self.set_conductor("opus", other)
        self.assertIn("finish: branch, model: fable", self.work("--dry-run").stdout)
        other_run = subprocess.run([sys.executable, str(SCRIPT), "--dry-run", str(other)], capture_output=True, text=True,
                                   env=self.env, encoding="utf-8")
        self.assertIn("finish: pr, model: opus", other_run.stdout, other_run.stderr)

    def test_a_model_line_under_opus_is_ignored_naming_opus(self):
        self.set_conductor("opus")
        self.queue.write_text("Model: sonnet\n\n- [ ] one\n", encoding="utf-8")
        for args in (("--dry-run",), ()):
            if not args:
                self.real_runs_need_the_stubs()   # the dry run above has been checked by now
            with self.subTest(args=args):
                stdout = self.work(*args).stdout
                self.assertTrue(stdout.startswith(
                    "ignoring 'Model: sonnet' in .swd/queue.md: every run starts with --model opus\n"), stdout)
        for line in self.runs_args():
            self.assertIn("--model opus", line)
            self.assertNotIn("sonnet", line)

    def test_the_queue_leaves_no_compiled_copy_of_the_hook(self):
        # Setup denies running the hook by name; a .pyc beside it would be a way round that.
        plugin = self.project.parent / "plugin"
        for part in ("scripts/swd-queue.py", "scripts/check_run.py", "hooks/swd-mode.py"):
            (plugin / part).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / part, plugin / part)
        self.set_conductor("opus")
        env = {k: v for k, v in self.env.items() if k != "PYTHONDONTWRITEBYTECODE"}
        result = subprocess.run([sys.executable, str(plugin / "scripts" / "swd-queue.py"), "--dry-run", str(self.project)],
                                capture_output=True, text=True, env=env, encoding="utf-8")
        self.assertIn("model: opus", result.stdout, result.stderr)   # the copy did load the hook
        self.assertTrue((plugin / "scripts" / "__pycache__").is_dir())   # bytecode was on for everything else
        self.assertFalse((plugin / "hooks" / "__pycache__").exists())

    def test_the_setting_is_read_for_the_resolved_folder_the_runs_start_in(self):
        # The setting is stored under the resolved folder; `.` or a `..` path must still find it.
        self.set_conductor("opus")
        for given, cwd in ((".", self.project), (str(self.project / ".." / "project"), None)):
            with self.subTest(given=given):
                result = subprocess.run([sys.executable, str(SCRIPT), "--dry-run", given], cwd=cwd, capture_output=True,
                                        text=True, env=self.env, encoding="utf-8")
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(result.stdout.splitlines()[0], "3 open items, finish: branch, model: opus")

    def test_a_hook_that_cannot_be_loaded_stops_the_queue_before_anything_else(self):
        # Never a silent fall back to fable: that would ignore the stored opus without a word.
        plugin = self.project.parent / "plugin"
        for part in ("scripts/swd-queue.py", "scripts/check_run.py"):
            (plugin / part).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / part, plugin / part)
        self.set_conductor("opus")
        self.queue.write_text("Model: sonnet\n\n- [ ] one\n", encoding="utf-8")
        before = self.queue.read_bytes()
        for broken in (None, "def conductor_setting(\n"):
            if broken:
                (plugin / "hooks").mkdir()
                (plugin / "hooks" / "swd-mode.py").write_text(broken, encoding="utf-8")
            for args in (("--dry-run",), ()):
                with self.subTest(hook=broken, args=args):
                    result = subprocess.run([sys.executable, str(plugin / "scripts" / "swd-queue.py"), *args,
                                             str(self.project)], capture_output=True, text=True, env=self.env,
                                            encoding="utf-8")
                    self.assertEqual(result.returncode, 1)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
                    self.assertIn("could not read the conductor setting: ", result.stderr)
                    self.assertIn("swd-mode.py", result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(self.prompts(), [])
                    self.assertEqual(self.runs_args(), [])
                    self.assertEqual(self.queue.read_bytes(), before)
                    self.assertFalse((self.project / ".swd" / "queue-report.md").exists())

    @stubbed
    def test_a_model_line_is_ignored_and_said_once_before_anything_else(self):
        # The project's conductor setting decides the model, never the queue file.
        self.queue.write_text("Model: sonnet\n\n- [ ] one\n- [ ] two\n", encoding="utf-8")
        result = self.work()
        self.assertEqual(result.stdout.count(self.IGNORED), 1)
        self.assertTrue(result.stdout.startswith(self.IGNORED + "\n"))
        args = [p.read_text(encoding="utf-8") for p in sorted(self.stub.glob("args-*.txt"))]
        self.assertEqual(len(args), 2)
        for line in args:
            self.assertIn("--model fable", line)
            self.assertNotIn("sonnet", line)

    def test_dry_run_says_a_model_line_is_ignored_and_names_fable(self):
        self.queue.write_text("Model: sonnet\n\n- [ ] one\n- [ ] two\n", encoding="utf-8")
        result = self.work("--dry-run")
        self.assertEqual(result.stdout.splitlines()[:2],
                         [self.IGNORED, "2 open items, finish: pr, model: fable"])
        self.assertEqual(result.stdout.count(self.IGNORED), 1)
        self.assertEqual(self.prompts(), [])

    def runs_args(self):
        return [p.read_text(encoding="utf-8") for p in sorted(self.stub.glob("args-*.txt"))]

    def test_two_model_lines_give_one_notice_naming_the_first(self):
        self.queue.write_text("Model: sonnet\nModel: haiku\n\n- [ ] one\n- [ ] two\n", encoding="utf-8")
        for args in (("--dry-run",), ()):
            if not args:
                self.real_runs_need_the_stubs()   # the dry run above has been checked by now
            with self.subTest(args=args):
                stdout = self.work(*args).stdout
                self.assertEqual([line for line in stdout.splitlines() if line.startswith("ignoring")],
                                 [self.IGNORED])
                self.assertNotIn("haiku", stdout)
        args = self.runs_args()
        self.assertEqual(len(args), 2)
        for line in args:
            self.assertIn("--model fable", line)

    def test_an_empty_model_line_gives_no_notice(self):
        for args in (("--dry-run",), ()):
            if not args:
                self.real_runs_need_the_stubs()   # the dry runs above have been checked by now
            for queue in ("Model: \n\n- [ ] one\n", "Model:\n\n- [ ] one\n"):
                self.queue.write_text(queue, encoding="utf-8")
                with self.subTest(queue=queue, args=args):
                    self.assertNotIn("ignoring", self.work(*args).stdout)
        args = self.runs_args()
        self.assertEqual(len(args), 2)
        for line in args:
            self.assertIn("--model fable", line)

    def test_the_ignored_value_is_printed_with_control_characters_escaped(self):
        # A crafted line must not clear the screen, set the window title or recolour the output.
        self.queue.write_text("Model: a\x1b]0;x\x07\x1b[2J\x9bb\n\n- [ ] one\n", encoding="utf-8")
        for args in (("--dry-run",), ()):
            if not args:
                self.real_runs_need_the_stubs()   # the dry run above has been checked by now
            with self.subTest(args=args):
                stdout = self.work(*args).stdout
                self.assertTrue(stdout.startswith(
                    r"ignoring 'Model: a\x1b]0;x\x07\x1b[2J\x9bb' in .swd/queue.md: every run starts with --model fable"
                    "\n"))
                self.assertFalse([c for c in stdout if not c.isprintable() and c != "\n"])

    @stubbed
    def test_max_limits_how_many_items_run(self):
        self.work("--max", "1")
        self.assertEqual(len(self.prompts()), 1)
        self.assertIn("- [ ] Add a changelog", self.queue.read_text(encoding="utf-8"))

    def test_no_queue_file_is_an_error(self):
        self.queue.unlink()
        self.assertEqual(self.work().returncode, 1)


if __name__ == "__main__":
    unittest.main()
