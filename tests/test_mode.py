"""Tests for hooks/swd-mode.py: the UserPromptExpansion hook that turns swd mode on from a typed
command, the UserPromptSubmit hook that keeps a session in swd mode, and the PreModelSwitch hook
that keeps a session in swd mode on Fable 5.2.

Every subprocess gets an environment built from scratch and temporary folders for HOME and its
working directory: this suite runs inside a project whose own .swd/runs holds real runs, which the
hook must never read.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "swd-mode.py"
HOOKS_JSON = ROOT / "hooks" / "hooks.json"

FABLE = "claude-fable-5-2"
SONNET = "claude-sonnet-5-5"

MESSAGE = ("swd: this session stays on Fable 5.2, because the principal runs on it and swd mode is on in "
           "this session. To switch anyway, run /swd:off.")

ON_SENTENCE = (
    "The principal of an swd run runs on Fable 5.2. Check which model you are running on, only from your "
    "own system and session information, at the start of every turn and again before every action that "
    "changes anything outside your own reply, such as a dispatch, ruling, commit, merge, push, reply on a "
    "pull request or write to the run folder; if you cannot tell, it is not Fable 5.2; if it is not Fable "
    "5.2, do no principal work and change nothing for the run outside your own reply: say which model you "
    "are on and that the run continues once the user runs /model fable and sends a message, and stop.")

OFF = ("swd mode: off\n"
       "swd mode has been turned off for this session. Handle requests normally from here on; the\n"
       "swd team is used again only when the user runs /swd:build, /swd:follow or /swd:on.\n")


def off_failed(flag):
    return ("swd mode: still on\n"
            "The swd-mode hook could not delete its flag file, so swd mode is still on and switches away "
            "from Fable 5.2 are still cancelled. Tell the user to delete this file by hand, or to start a "
            f"new session (not a resumed one): {flag}\n")

# Loads the hook as a module, sets its own time limit, optionally slows flag_for or records every
# file the hook opens or lists, and runs it as the command line would.
WRAPPER = """
import importlib.util, json, os, sys, time
spec = importlib.util.spec_from_file_location("swd_mode", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.LIMIT_SECONDS = float(sys.argv[2])
how = sys.argv[3] if len(sys.argv) > 3 else ""
if how == "slow":  # stands in for a hung home folder
    real_flag_for = module.flag_for
    def flag_for(event):
        time.sleep(30)
        return real_flag_for(event)
    module.flag_for = flag_for
paths = []
if how == "audit":
    def record(event, args):
        if event in ("open", "os.listdir", "os.scandir") and args and isinstance(args[0], (str, bytes, os.PathLike)):
            paths.append(os.path.abspath(os.fsdecode(args[0])))
    sys.addaudithook(record)
try:
    module.main()
finally:
    if how == "audit":
        seen = {"paths": list(paths), "check_run": "check_run" in sys.modules}
        with open(sys.argv[4], "w") as out:
            json.dump(seen, out)
"""


class ModeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = self._tmp.name
        self.elsewhere = Path(self._tmp.name) / "elsewhere"  # the hook process's working directory
        self.elsewhere.mkdir()

    def env(self):
        return {"HOME": self.home, "PATH": "/usr/bin:/bin"}

    def run_hook(self, payload):
        result = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True,
                                env=self.env(), cwd=self.elsewhere)
        self.assertEqual(result.returncode, 0, result.stderr)  # exit 2 would block the user's command
        self.assertNotIn("Traceback", result.stderr)
        return result.stdout

    def prompt(self, text, session="s1", raw=None):
        payload = raw if raw is not None else json.dumps(
            {"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": text})
        return self.run_hook(payload)

    def expand(self, command_name, session="s1", args=""):
        """The event Claude Code sends when the user types a command and it expands."""
        return self.run_hook(json.dumps({
            "hook_event_name": "UserPromptExpansion", "session_id": session, "expansion_type": "slash_command",
            "command_name": command_name, "command_args": args, "command_source": "plugin",
            "prompt": "/" + command_name + (" " + args if args else "")}))

    def test_off_by_default(self):
        self.assertEqual(self.prompt("add a login page"), "")

    def test_build_turns_it_on_and_it_stays_on(self):
        self.assertTrue(self.expand("swd:build", args="x").startswith("swd mode: on"))
        self.assertTrue(self.flag().is_file())
        later = self.prompt("now add a logout button")
        self.assertIn("swd mode: on", later)
        self.assertIn("swd:build", later)          # how to route a change
        self.assertIn("stop swd", later)           # how to leave

    def test_follow_turns_it_on_and_it_stays_on(self):
        self.assertTrue(self.expand("swd:follow").startswith("swd mode: on"))
        self.assertTrue(self.flag().is_file())
        self.assertIn("swd mode: on", self.prompt("reply to the review"))

    def test_on_command_turns_it_on(self):
        self.assertTrue(self.expand("swd:on").startswith("swd mode: on"))
        self.assertTrue(self.flag().is_file())
        self.assertIn("swd mode: on", self.prompt("fix the typo in the README"))

    def test_a_command_typed_while_on_adds_the_text_only_once(self):
        self.expand("swd:on")
        self.assertEqual(self.expand("swd:build", args="x"), "")  # UserPromptSubmit printed it already
        self.assertTrue(self.flag().is_file())

    def test_no_other_command_turns_it_on(self):
        for name in ("swd:off", "other:build", "build", "swd:buildx", "swd:on2", ""):
            with self.subTest(command_name=name):
                self.assertEqual(self.expand(name), "")
                self.assertFalse(self.flag().exists())

    def test_an_expansion_without_a_usable_command_name_turns_nothing_on(self):
        # The prompt field reads /swd:on, so only command_name can keep these off.
        base = {"hook_event_name": "UserPromptExpansion", "session_id": "s1", "expansion_type": "slash_command",
                "command_args": "", "command_source": "plugin", "prompt": "/swd:on"}
        for name in (["swd:on"], None, 5, "missing"):
            event = dict(base) if name == "missing" else {**base, "command_name": name}
            with self.subTest(command_name=name):
                self.assertEqual(self.run_hook(json.dumps(event)), "")
                self.assertFalse(self.flag().exists())

    def test_an_expansion_with_a_bad_session_turns_nothing_on(self):
        self.assertEqual(self.expand("swd:on", session=""), "")
        self.assertEqual(self.expand("swd:on", session="../escaped"), "")
        self.assertFalse((Path(self.home) / ".claude").exists())

    def test_a_prompt_that_starts_with_an_on_command_does_not_turn_it_on(self):
        # UserPromptSubmit also carries text the user did not type, such as an agent's report.
        for text in ("/swd:build x", "/swd:follow", "/swd:on"):
            with self.subTest(text=text):
                self.assertEqual(self.prompt(text), "")
                self.assertFalse(self.flag().exists())

    def test_mode_text_names_the_principals_model_and_the_stop(self):
        text = self.expand("swd:on")
        last = text.strip().splitlines()[-1]
        self.assertEqual(last, ON_SENTENCE)
        self.assertTrue(last.startswith("The principal of an swd run runs on Fable 5.2."), last)
        for needle in ("if it is not Fable 5.2, do no principal work",
                       "only from your own system and session information",
                       "at the start of every turn and again before every action that changes anything "
                       "outside your own reply, such as a dispatch, ruling, commit, merge, push, reply on a "
                       "pull request or write to the run folder",
                       "do no principal work and change nothing for the run outside your own reply",
                       "if you cannot tell, it is not Fable 5.2",
                       "/model fable and sends a message, and stop."):
            with self.subTest(needle=needle):
                self.assertIn(needle, last)
        self.assertIn('by sending "stop swd" or /swd:off as a message on its own', " ".join(text.split()))
        for absent in ("message again", "before every dispatch", "no judging"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, text)

    def test_other_sessions_are_not_affected(self):
        self.expand("swd:on", session="s1")
        self.assertEqual(self.prompt("add a login page", session="s2"), "")

    def flag(self, session="s1"):
        return Path(self.home) / ".claude" / "swd-mode" / session

    def test_stop_phrase_and_off_command_turn_it_off_as_the_whole_message(self):
        for stop in ("stop swd", "  Stop SWD  ", "/swd:off", "/SWD:OFF"):
            with self.subTest(stop=stop):
                self.expand("swd:on")
                self.assertEqual(self.prompt(stop), OFF)
                self.assertFalse(self.flag().exists())
                self.assertEqual(self.prompt("add a login page"), "")

    def test_off_names_every_command_that_turns_it_on(self):
        self.expand("swd:on")
        out = self.prompt("/swd:off")
        self.assertEqual(out, OFF)
        self.assertIn("/swd:build, /swd:follow or /swd:on", out)

    def test_off_says_so_when_it_cannot_delete_the_flag(self):
        if os.geteuid() == 0:
            self.skipTest("root can delete the flag from a read-only folder")
        flag = f"{self.home}/.claude/swd-mode/s1"  # Path.home() is HOME as given, unresolved
        for stop in ("/swd:off", "stop swd"):
            with self.subTest(stop=stop):
                self.expand("swd:on")
                folder = self.flag().parent
                folder.chmod(0o500)
                self.addCleanup(folder.chmod, 0o700)  # runs before the temporary folder is removed
                self.assertEqual(self.prompt(stop), off_failed(flag))  # exits 0, checked by run_hook
                self.assertTrue(self.flag().is_file())
                switch = json.dumps({"hook_event_name": "PreModelSwitch", "session_id": "s1",
                                     "from_model": FABLE, "to_model": SONNET})
                result = subprocess.run([sys.executable, str(HOOK)], input=switch, capture_output=True,
                                        text=True, env=self.env(), cwd=self.elsewhere)
                self.assertEqual((result.returncode, result.stdout, result.stderr.strip()), (2, "", MESSAGE))
                folder.chmod(0o700)

    def test_the_off_words_inside_a_longer_message_leave_it_on(self):
        report = "Review of T1 done.\nThe ON text says:\nstop swd\nAll tests pass."  # as a report would quote it
        for text in ("please stop swd now", "don't stop swd yet", "stop swd.", "/swd:off please", report):
            with self.subTest(text=text):
                self.expand("swd:on")
                self.assertTrue(self.prompt(text).startswith("swd mode: on"))
                self.assertTrue(self.flag().is_file())

    def test_mentioning_swd_does_not_turn_it_on(self):
        for text in ("how does /swd:build work?", "how does /swd:follow work?", "what is swd mode: on?",
                     "please run /swd:follow", "text\n/swd:build x"):
            with self.subTest(text=text):
                self.assertEqual(self.prompt(text), "")

    def test_bad_input_is_ignored(self):
        self.assertEqual(self.prompt("", raw="not json"), "")
        self.assertEqual(self.prompt("", raw=json.dumps({"prompt": "/swd:on"})), "")  # no session id
        self.assertEqual(self.prompt("", raw="[" * 100000), "")  # too deeply nested for json.load

    # The flag is a regular file, and /swd:on never writes through a link

    def test_a_folder_at_the_flag_path_is_not_mode_on(self):
        self.flag().mkdir(parents=True)
        self.assertEqual(self.prompt("add a login page"), "")
        self.assertEqual(self.expand("swd:on"), "")  # its unlink raises into except OSError: stays off
        self.assertTrue(self.flag().is_dir())

    def test_on_replaces_a_link_and_leaves_its_target_alone(self):
        target = Path(self.home) / "precious.txt"
        target.write_text("precious data")
        self.flag().parent.mkdir(parents=True)
        self.flag().symlink_to(target)
        self.expand("swd:on")  # the link counts as on, so the text is not repeated here
        self.assertEqual(target.read_text(), "precious data")
        self.assertTrue(self.flag().is_file())
        self.assertFalse(self.flag().is_symlink())
        self.assertTrue(self.prompt("hello").startswith("swd mode: on"))

    def test_on_replaces_a_dangling_link_without_creating_its_target(self):
        target = Path(self.home) / "nothing-here"
        self.flag().parent.mkdir(parents=True)
        self.flag().symlink_to(target)
        self.assertTrue(self.expand("swd:on").startswith("swd mode: on"))
        self.assertFalse(target.exists())
        self.assertTrue(self.flag().is_file())
        self.assertFalse(self.flag().is_symlink())

    def test_on_keeps_a_stale_flag(self):
        self.expand("swd:on")
        eight_days_ago = time.time() - 8 * 24 * 60 * 60
        os.utime(self.flag(), (eight_days_ago, eight_days_ago))
        self.assertEqual(self.expand("swd:on"), "")  # already on: the text is not repeated
        self.assertTrue(self.flag().is_file())  # recreated, so the stale sweep did not take it
        self.assertIn("swd mode: on", self.prompt("add a login page"))

    def test_on_sweeps_other_sessions_stale_flags(self):
        self.flag().parent.mkdir(parents=True)
        for session in ("s2", "s3"):
            self.flag(session).write_text("")
        eight_days_ago = time.time() - 8 * 24 * 60 * 60
        os.utime(self.flag("s2"), (eight_days_ago, eight_days_ago))
        self.expand("swd:on")
        self.assertFalse(self.flag("s2").exists())
        self.assertTrue(self.flag("s3").is_file())

    def test_the_source_checks_the_flag_as_a_regular_file_and_never_writes_through_it(self):
        source = HOOK.read_text()
        for needle in (".exists()", "write_text"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, source)

    def test_session_id_cannot_escape_the_state_folder(self):
        self.expand("swd:on", session="../../escaped")
        self.assertFalse((Path(self.home) / "escaped").exists())
        self.assertFalse((Path(self.home) / ".claude" / "escaped").exists())

    def test_a_prompt_event_with_model_fields_is_still_a_prompt(self):
        self.expand("swd:on")
        payload = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "hi",
                              "from_model": FABLE, "to_model": SONNET})
        self.assertIn("swd mode: on", self.prompt("", raw=payload))  # exits 0, checked by prompt()


class SwitchTest(unittest.TestCase):
    """PreModelSwitch: cancel a switch away from Fable 5.2 only while swd mode is on."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.home = base / "home"
        self.project = base / "project"
        self.elsewhere = base / "elsewhere"  # the hook process's working directory
        for folder in (self.home, self.project, self.elsewhere):
            folder.mkdir()

    def mode_on(self, session="s1"):
        flags = self.home / ".claude" / "swd-mode"
        flags.mkdir(parents=True, exist_ok=True)
        (flags / session).write_text("")

    def unfinished_run(self):
        """A run the build playbook's Preflight counts as unfinished: a todo row, no Abandoned: line."""
        run = self.project / ".swd" / "runs" / "2026-11-15-x"
        run.mkdir(parents=True)
        (run / "ledger.md").write_text("| Task | Role | Status | Attempts |\n|---|---|---|---|\n"
                                       "| T1 | generalist-engineer | todo | 1 |\n")
        (run / "decisions.md").write_text("Base commit: abc123\nBase branch: main\n")

    def event(self, from_model=FABLE, to_model=SONNET, session="s1", **extra):
        event = {"session_id": session, "hook_event_name": "PreModelSwitch", "cwd": str(self.elsewhere),
                 "from_model": from_model, "to_model": to_model, "requested_model": "sonnet",
                 "source": "command"}
        event.update(extra)
        return json.dumps(event)

    def env(self, project=None):
        env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin"}
        if project is not None:
            env["CLAUDE_PROJECT_DIR"] = str(project)
        return env

    def switch(self, payload=None, project=None, command=None, timeout=10):
        payload = self.event() if payload is None else payload
        command = command or [sys.executable, str(HOOK)]
        return subprocess.run(command, input=payload, capture_output=True, text=True,
                              env=self.env(project), cwd=self.elsewhere, timeout=timeout)

    def assertAllowed(self, result):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def assertBlocked(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), MESSAGE)

    # Cancelled

    def test_mode_on_cancels_a_switch_away(self):
        self.mode_on()
        self.assertBlocked(self.switch())

    def test_a_long_fable_id_is_still_fable(self):
        self.mode_on()
        for from_model in ("claude-fable-5-2[1m]", "us.anthropic.claude-fable-5-2-v1:0", "Claude-Fable-5-2"):
            with self.subTest(from_model=from_model):
                self.assertBlocked(self.switch(self.event(from_model=from_model)))

    # Allowed

    def test_allowed_with_mode_off(self):
        self.assertAllowed(self.switch())

    def test_mode_in_another_session_does_not_cancel(self):
        self.mode_on("s2")
        self.assertAllowed(self.switch())

    def test_a_switch_to_fable_is_always_allowed(self):
        self.mode_on()
        for to_model in (FABLE, "claude-fable-5-2[1m]", "us.anthropic.claude-fable-5-2-v1:0"):
            with self.subTest(to_model=to_model):
                self.assertAllowed(self.switch(self.event(to_model=to_model)))

    def test_a_switch_from_another_model_is_allowed(self):
        self.mode_on()
        for from_model in (SONNET, "claude-fable-5-1", "claude-fable-5-21", "claude-opus-5-5"):
            with self.subTest(from_model=from_model):
                self.assertAllowed(self.switch(self.event(from_model=from_model)))

    def test_bad_input_lets_the_switch_through(self):
        self.mode_on()  # so only the input check can allow these
        bad = [
            "", "not json", "[1, 2]", json.dumps("PreModelSwitch"), "{\"hook_event_name\": \"PreModelSwitch\"",
            json.dumps({"session_id": "s1", "hook_event_name": "PreModelSwitch", "to_model": SONNET}),
            json.dumps({"session_id": "s1", "hook_event_name": "PreModelSwitch", "from_model": FABLE}),
            self.event(from_model=None), self.event(to_model=None),
            self.event(from_model=["claude-fable-5-2"]), self.event(to_model=5),
            self.event(to_model=""), self.event(to_model="  "), self.event(from_model=""),
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                self.assertAllowed(self.switch(payload))

    def test_deeply_nested_input_lets_the_switch_through(self):
        self.mode_on()
        self.assertAllowed(self.switch("[" * 100000))

    def test_a_folder_at_the_flag_path_lets_the_switch_through(self):
        (self.home / ".claude" / "swd-mode" / "s1").mkdir(parents=True)
        self.assertAllowed(self.switch())

    def test_a_bad_session_id_is_not_mode_on(self):
        self.mode_on("s1")
        self.assertAllowed(self.switch(self.event(session="../swd-mode/s1")))

    # The project is never read

    def test_an_unfinished_run_in_the_project_changes_nothing(self):
        self.unfinished_run()
        payload = self.event(cwd=str(self.project))
        self.assertAllowed(self.switch(payload, project=self.project))
        self.mode_on()
        self.assertBlocked(self.switch(payload, project=self.project))  # no run named

    def test_no_file_under_the_project_is_opened_or_listed(self):
        self.unfinished_run()
        self.mode_on()
        record = self.elsewhere / "audit.json"
        result = self.switch(self.event(cwd=str(self.project)), project=self.project,
                             command=self.wrapped(3, "audit", str(record)))
        seen = json.loads(record.read_text())
        project = self.project.resolve()
        inside = [p for p in seen["paths"] if Path(p).resolve() == project or project in Path(p).resolve().parents]
        self.assertEqual(inside, [])
        self.assertFalse(seen["check_run"])
        self.assertBlocked(result)

    def test_the_source_names_no_project_file(self):
        source = HOOK.read_text()
        for needle in ("check_run", "CLAUDE_PROJECT_DIR", ".swd", '"cwd"'):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, source)

    # Its own time limit

    def wrapped(self, limit, *how):
        return [sys.executable, "-c", WRAPPER, str(HOOK), str(limit), *how]

    def test_the_wrapper_runs_the_shipped_path(self):
        self.mode_on()
        plain = self.switch()
        wrapped = self.switch(command=self.wrapped(3))
        self.assertBlocked(wrapped)
        self.assertEqual((wrapped.returncode, wrapped.stdout, wrapped.stderr),
                         (plain.returncode, plain.stdout, plain.stderr))

    def test_it_gives_up_and_allows_when_it_cannot_decide_in_time(self):
        self.mode_on()  # without the give-up, the slow lookup ends in a cancel
        started = time.monotonic()
        result = self.switch(command=self.wrapped(0.2, "slow"), timeout=5)
        elapsed = time.monotonic() - started
        self.assertAllowed(result)
        self.assertGreaterEqual(elapsed, 0.2)
        self.assertLess(elapsed, 3)

    def test_the_limit_is_at_most_half_the_hook_timeout(self):
        spec = importlib.util.spec_from_file_location("swd_mode_limit", HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]["PreModelSwitch"]
        timeouts = [h["timeout"] for group in hooks for h in group["hooks"]]
        self.assertEqual(len(timeouts), 1)
        self.assertEqual(module.LIMIT_SECONDS, 3)
        self.assertLessEqual(module.LIMIT_SECONDS, timeouts[0] / 2)


class HooksJsonTest(unittest.TestCase):
    def test_the_hook_is_registered_for_all_three_events(self):
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
        self.assertEqual(set(hooks), {"UserPromptSubmit", "UserPromptExpansion", "PreModelSwitch"})
        for event in hooks:
            with self.subTest(event=event):
                commands = [h for group in hooks[event] for h in group["hooks"]]
                self.assertEqual(len(commands), 1)
                self.assertEqual(commands[0]["type"], "command")
                self.assertIn("swd-mode.py", commands[0]["command"])
                self.assertIn("CLAUDE_PLUGIN_ROOT", commands[0]["command"])
                self.assertEqual(commands[0]["timeout"], 10)
                self.assertNotIn("matcher", hooks[event][0])


if __name__ == "__main__":
    unittest.main()
