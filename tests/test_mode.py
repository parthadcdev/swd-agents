"""Tests for hooks/swd-mode.py: the UserPromptExpansion hook that turns swd mode on from a typed
command and stores the conductor setting from a typed /swd:conductor, the UserPromptSubmit hook that
keeps a session in swd mode, and the PreModelSwitch hook that keeps a session in swd mode on the
models the project's conductor setting accepts.

Every subprocess gets an environment built from scratch and temporary folders for HOME and its
working directory: this suite runs inside a project whose own .swd/runs holds real runs, which the
hook must never read. No test calls the hook's functions in the test process, where Path.home() is
the real home folder.
"""
import ast
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "swd-mode.py"
HOOKS_JSON = ROOT / "hooks" / "hooks.json"
SH = shutil.which("sh")  # found before any test replaces PATH

HOOK_COMMAND = 'sh "${CLAUDE_PLUGIN_ROOT}/scripts/swd-python.sh" run "${CLAUDE_PLUGIN_ROOT}/hooks/swd-mode.py"'
NOTICE = ("swd: the swd plugin needs Python 3.9 or later and found none (tried python3, python and py -3). "
          "Run /swd:setup: it can install Python on Windows, or tell you the command for this system.\n")


def clean_env(home, path=os.pathsep.join(["/usr/bin", "/bin"]), **extra):
    """An environment built from scratch: Path.home() reads USERPROFILE on Windows, HOME elsewhere."""
    env = {"HOME": str(home), "USERPROFILE": str(home), "PATH": path}
    if "SYSTEMROOT" in os.environ:  # Python on Windows cannot start without it
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    env.update(extra)
    return env


def unencoded_text_io(source):
    """Lines of calls that read or write text in the platform's encoding instead of UTF-8."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        keywords = {k.arg: k.value for k in node.keywords}
        if "encoding" in keywords:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        if isinstance(func, ast.Attribute) and name in ("read_text", "write_text"):
            found.append(node.lineno)
        elif isinstance(func, ast.Name) and name == "open":  # the builtin; os.open is an Attribute
            mode = node.args[1] if len(node.args) > 1 else keywords.get("mode")
            if not (isinstance(mode, ast.Constant) and "b" in str(mode.value)):
                found.append(node.lineno)
        elif name in ("run", "Popen", "check_output", "call") and any(
                isinstance(keywords.get(k), ast.Constant) and keywords[k].value
                for k in ("text", "universal_newlines")):
            found.append(node.lineno)
    return found

FABLE = "claude-fable-5-2"
OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"

MESSAGE = ("swd: this session stays on Fable 5.2, because the principal runs on it and swd mode is on in "
           "this session. To switch anyway, run /swd:off.")
OPUS_MESSAGE = ("swd: this session stays on Fable 5.2 or Opus 5.5, because the principal of this project runs "
                "on them and swd mode is on in this session. To switch anyway, run /swd:off.")

ON_SENTENCE = (
    "The principal of an swd run runs on Fable 5.2. Check which model you are running on, only from your "
    "own system and session information, at the start of every turn and again before every action that "
    "changes anything outside your own reply, such as a dispatch, ruling, commit, merge, push, reply on a "
    "pull request or write to the run folder; if you cannot tell, it is not Fable 5.2; if it is not Fable "
    "5.2, do no principal work and change nothing for the run outside your own reply: say which model you "
    "are on and that the run continues once the user runs /model fable and sends a message, and stop.")

ON_OPUS_SENTENCE = (
    "The principal of an swd run in this project runs on Fable 5.2 or Opus 5.5 (conductor setting: opus). "
    "Check which model you are running on, only from your own system and session information, at the start "
    "of every turn and again before every action that changes anything outside your own reply, such as a "
    "dispatch, ruling, commit, merge, push, reply on a pull request or write to the run folder; if you cannot "
    "tell, it is neither; if it is neither Fable 5.2 nor Opus 5.5, do no principal work and change nothing for "
    "the run outside your own reply: say which model you are on and that the run continues once the user runs "
    "/model fable or /model opus and sends a message, and stop. On Opus 5.5, dispatch the Fable judge where "
    "the build playbook says.")

NOT_TOLD = "The hook was not told this session's folder, so only Fable 5.2 may conduct here."
REFUSED = "The value must be fable or opus; nothing was stored. "
MISSING = object()  # an event without the field at all


def where(key, setting):
    models = "Fable 5.2 or Opus 5.5" if setting == "opus" else "Fable 5.2"
    return f"{models} may conduct swd runs in {key}, its .swd/worktrees included."

OFF = ("swd mode: off\n"
       "swd mode has been turned off for this session. Handle requests normally from here on; the\n"
       "swd team is used again only when the user runs /swd:build, /swd:follow or /swd:on.\n")


def off_failed(flag):
    return ("swd mode: still on\n"
            "The swd-mode hook could not delete its flag file, so swd mode is still on and switches away "
            "from the principal's models are still cancelled. Tell the user to delete this file by hand, or to start a "
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
if how == "regular":  # stands in for an entry swapped after its lstat: the hook takes anything for a regular file
    class AlwaysRegular:
        S_ISREG = staticmethod(lambda mode: True)
    module.stat = AlwaysRegular
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
        with open(sys.argv[4], "w", encoding="utf-8") as out:
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
        return clean_env(self.home)

    def run_hook(self, payload):
        result = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True,
                                encoding="utf-8", env=self.env(), cwd=self.elsewhere)
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

    @unittest.skipIf(os.name == "nt", "Windows has no os.geteuid, and a read-only folder does not stop a "
                                      "file in it being deleted")
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
                                        text=True, encoding="utf-8", env=self.env(), cwd=self.elsewhere)
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

    @unittest.skipIf(os.name == "nt", "creating a symlink on Windows needs Developer Mode or admin rights")
    def test_on_replaces_a_link_and_leaves_its_target_alone(self):
        target = Path(self.home) / "precious.txt"
        target.write_text("precious data", encoding="utf-8")
        self.flag().parent.mkdir(parents=True)
        self.flag().symlink_to(target)
        self.expand("swd:on")  # the link counts as on, so the text is not repeated here
        self.assertEqual(target.read_text(encoding="utf-8"), "precious data")
        self.assertTrue(self.flag().is_file())
        self.assertFalse(self.flag().is_symlink())
        self.assertTrue(self.prompt("hello").startswith("swd mode: on"))

    @unittest.skipIf(os.name == "nt", "creating a symlink on Windows needs Developer Mode or admin rights")
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
            self.flag(session).write_text("", encoding="utf-8")
        eight_days_ago = time.time() - 8 * 24 * 60 * 60
        os.utime(self.flag("s2"), (eight_days_ago, eight_days_ago))
        self.expand("swd:on")
        self.assertFalse(self.flag("s2").exists())
        self.assertTrue(self.flag("s3").is_file())

    def test_the_source_checks_the_flag_as_a_regular_file_and_never_writes_through_it(self):
        source = HOOK.read_text(encoding="utf-8")
        for needle in (".exists()", "write_text"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, source)

    def test_a_prompt_in_utf8_is_read_whatever_the_platform_encoding(self):
        # On Windows Python reads stdin as cp1252, where the UTF-8 bytes of a curly quote do not decode.
        self.expand("swd:on")
        payload = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "s1",
                              "prompt": "rename the “foo” button"}, ensure_ascii=False)
        result = subprocess.run([sys.executable, str(HOOK)], input=payload.encode("utf-8"), capture_output=True,
                                env=clean_env(self.home, PYTHONIOENCODING="cp1252"), cwd=self.elsewhere)
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        self.assertTrue(result.stdout.decode("utf-8").startswith("swd mode: on"), result.stdout)

    def test_the_hook_reads_and_writes_text_only_as_utf8(self):
        self.assertEqual(unencoded_text_io(HOOK.read_text(encoding="utf-8")), [])
        bad = ("open('a')\nopen('a', 'w')\nopen('a', mode='r')\np.read_text()\np.write_text('x')\n"
               "subprocess.run(c, text=True)\nsubprocess.check_output(c, universal_newlines=True)\n"
               "subprocess.Popen(c, text=True)\nsubprocess.call(c, text=True)\n"
               "open('a', 'rb')\nos.open('a', 0)\np.read_text(encoding='utf-8')\n"
               "subprocess.run(c, text=True, encoding='utf-8')\nsubprocess.run(c)\n")
        self.assertEqual(unencoded_text_io(bad), list(range(1, 10)))  # the guard catches each kind

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
        (flags / session).write_text("", encoding="utf-8")

    def unfinished_run(self):
        """A run the build playbook's Preflight counts as unfinished: a todo row, no Abandoned: line."""
        run = self.project / ".swd" / "runs" / "2026-11-15-x"
        run.mkdir(parents=True)
        (run / "ledger.md").write_text("| Task | Role | Status | Attempts |\n|---|---|---|---|\n"
                                       "| T1 | generalist-engineer | todo | 1 |\n", encoding="utf-8")
        (run / "decisions.md").write_text("Base commit: abc123\nBase branch: main\n", encoding="utf-8")

    def event(self, from_model=FABLE, to_model=SONNET, session="s1", **extra):
        event = {"session_id": session, "hook_event_name": "PreModelSwitch", "cwd": str(self.elsewhere),
                 "from_model": from_model, "to_model": to_model, "requested_model": "sonnet",
                 "source": "command"}
        event.update(extra)
        return json.dumps(event)

    def env(self, project=None):
        env = clean_env(self.home)
        if project is not None:
            env["CLAUDE_PROJECT_DIR"] = str(project)
        return env

    def switch(self, payload=None, project=None, command=None, timeout=10):
        payload = self.event() if payload is None else payload
        command = command or [sys.executable, str(HOOK)]
        return subprocess.run(command, input=payload, capture_output=True, text=True, encoding="utf-8",
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
        seen = json.loads(record.read_text(encoding="utf-8"))
        project = self.project.resolve()
        inside = [p for p in seen["paths"] if Path(p).resolve() == project or project in Path(p).resolve().parents]
        self.assertEqual(inside, [])
        self.assertFalse(seen["check_run"])
        self.assertBlocked(result)

    def test_a_project_set_to_opus_is_decided_without_opening_anything_in_it(self):
        # The project holds a worktree folder and a settings file; only HOME's conductor entry may be read.
        tests = self.project / ".swd" / "worktrees" / "x" / "tests"
        tests.mkdir(parents=True)
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "settings.json").write_text('{"env": {"HOME": "/elsewhere"}}', encoding="utf-8")
        stored = subprocess.run(
            [sys.executable, str(HOOK)], capture_output=True, text=True, encoding="utf-8", env=self.env(),
            cwd=self.elsewhere, input=json.dumps({
                "hook_event_name": "UserPromptExpansion", "session_id": "s1", "cwd": str(self.project),
                "expansion_type": "slash_command", "command_name": "swd:conductor", "command_args": "opus",
                "prompt": "/swd:conductor opus"}))
        self.assertEqual((stored.returncode, stored.stdout.splitlines()[0]), (0, "swd conductor: set to opus"))
        self.mode_on()
        digest = hashlib.sha256(os.path.normcase(str(self.project)).encode("utf-8", "surrogatepass")).hexdigest()
        entry = str(self.home / ".claude" / "swd-conductor" / digest)
        project = self.project.resolve()
        cases = [
            ("prompt", json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": str(tests),
                                   "prompt": "carry on"})),
            ("to opus", self.event(to_model=OPUS, cwd=str(tests))),
            ("to sonnet", self.event(to_model=SONNET, cwd=str(tests))),
        ]
        for name, payload in cases:
            with self.subTest(event=name):
                record = self.elsewhere / f"audit-{name}.json"
                result = self.switch(payload, project=self.project, command=self.wrapped(3, "audit", str(record)))
                seen = json.loads(record.read_text(encoding="utf-8"))
                inside = [p for p in seen["paths"]
                          if Path(p).resolve() == project or project in Path(p).resolve().parents]
                self.assertEqual(inside, [])
                self.assertIn(entry, seen["paths"])
                self.assertFalse(seen["check_run"])
                if name == "prompt":
                    self.assertEqual((result.returncode, result.stderr), (0, ""))
                    self.assertEqual(result.stdout.strip().splitlines()[-1], ON_OPUS_SENTENCE)
                elif name == "to opus":
                    self.assertAllowed(result)
                else:
                    self.assertEqual((result.returncode, result.stdout, result.stderr.strip()), (2, "", OPUS_MESSAGE))

    def test_the_source_names_no_project_file_and_resolves_no_path(self):
        source = HOOK.read_text(encoding="utf-8")
        for needle in ("check_run", "CLAUDE_PROJECT_DIR", "resolve(", "realpath"):
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
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PreModelSwitch"]
        timeouts = [h["timeout"] for group in hooks for h in group["hooks"]]
        self.assertEqual(len(timeouts), 1)
        self.assertEqual(module.LIMIT_SECONDS, 3)
        self.assertLessEqual(module.LIMIT_SECONDS, timeouts[0] / 2)


class ConductorTest(unittest.TestCase):
    """/swd:conductor stores a per-project setting under HOME; the reminder and the switch rule follow it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.home = base / "home"
        self.elsewhere = base / "elsewhere"  # the hook process's working directory
        for folder in (self.home, self.elsewhere):
            folder.mkdir()
        # Path text only, built on the temporary folder so it is absolute on every platform. The hook never
        # looks at these folders, so they are not created.
        self.p = str(base / "demo" / "p")
        self.q = str(base / "demo" / "q")
        self.worktree = str(Path(self.p, ".swd", "worktrees", "x"))

    # Running the hook

    def run_hook(self, event, command=None):
        return subprocess.run(command or [sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True,
                              text=True, encoding="utf-8", env=clean_env(self.home), cwd=self.elsewhere, timeout=30)

    def ok(self, event, command=None):
        """Runs a prompt or command event, which must exit 0 with nothing on stderr."""
        result = self.run_hook(event, command)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return result.stdout

    def conductor(self, cwd, args="", session="s1", name="swd:conductor", command=None):
        event = {"hook_event_name": "UserPromptExpansion", "session_id": session, "expansion_type": "slash_command",
                 "command_name": name, "command_args": args, "command_source": "plugin",
                 "prompt": "/swd:conductor" + (" " + args if args else "")}
        if cwd is not MISSING:
            event["cwd"] = cwd
        if session is MISSING:
            del event["session_id"]
        return self.ok(event, command)

    def on(self, cwd):
        return self.ok({"hook_event_name": "UserPromptExpansion", "session_id": "s1", "cwd": cwd,
                        "expansion_type": "slash_command", "command_name": "swd:on", "command_args": "",
                        "command_source": "plugin", "prompt": "/swd:on"})

    def prompt(self, cwd, text="carry on", command=None):
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": text}
        if cwd is not MISSING:
            event["cwd"] = cwd
        return self.ok(event, command)

    def switch(self, cwd, from_model, to_model, command=None):
        event = {"hook_event_name": "PreModelSwitch", "session_id": "s1", "from_model": from_model,
                 "to_model": to_model, "requested_model": "x", "source": "command"}
        if cwd is not MISSING:
            event["cwd"] = cwd
        return self.run_hook(event, command)

    def mode_on(self):
        flags = self.home / ".claude" / "swd-mode"
        flags.mkdir(parents=True, exist_ok=True)
        (flags / "s1").write_bytes(b"")

    def flag(self):
        return self.home / ".claude" / "swd-mode" / "s1"

    def entry(self, key):
        """Where C1 keeps a project's setting, computed here so no test imports the hook under the real HOME."""
        digest = hashlib.sha256(os.path.normcase(key).encode("utf-8", "surrogatepass")).hexdigest()
        return self.home / ".claude" / "swd-conductor" / digest

    def setting(self, cwd):
        return self.conductor(cwd).splitlines()[0]

    def assertAllowed(self, result):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def assertBlocked(self, result, message):
        self.assertEqual((result.returncode, result.stdout, result.stderr.strip()), (2, "", message))

    # The command

    def test_no_value_with_nothing_stored_reads_fable(self):
        self.assertEqual(self.conductor(self.p), f"swd conductor: fable\n{where(self.p, 'fable')}\n")
        self.assertFalse((self.home / ".claude").exists())  # reading creates nothing

    def test_set_opus_then_fable_and_read_each_back(self):
        self.assertEqual(self.conductor(self.p, "opus"), f"swd conductor: set to opus\n{where(self.p, 'opus')}\n")
        self.assertEqual(self.entry(self.p).read_bytes().strip(), b"opus")
        if os.name != "nt":
            self.assertEqual(self.entry(self.p).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.conductor(self.p), f"swd conductor: opus\n{where(self.p, 'opus')}\n")
        self.assertEqual(self.conductor(self.p, "fable"),
                         f"swd conductor: set to fable\n{where(self.p, 'fable')}\n")
        self.assertEqual(self.conductor(self.p), f"swd conductor: fable\n{where(self.p, 'fable')}\n")

    def test_the_value_is_trimmed_and_case_folded(self):
        self.assertEqual(self.setting_after(self.p, "  OPUS  "), "swd conductor: set to opus")
        self.assertEqual(self.setting(self.p), "swd conductor: opus")

    def setting_after(self, cwd, args):
        return self.conductor(cwd, args).splitlines()[0]

    def test_another_value_is_refused_stores_nothing_and_is_not_echoed(self):
        for value in ("sonnet", "zzz-secret-value", "opus extra", "fable,opus", "OPUS5"):
            with self.subTest(value=value, stored="nothing"):
                out = self.conductor(self.p, value)
                self.assertEqual(out, f"swd conductor: refused, still fable\n{REFUSED}{where(self.p, 'fable')}\n")
                self.assertNotIn(value, out)
                self.assertFalse(self.entry(self.p).exists())
        self.conductor(self.p, "opus")
        for value in ("sonnet", "zzz-secret-value"):
            with self.subTest(value=value, stored="opus"):
                out = self.conductor(self.p, value)
                self.assertEqual(out, f"swd conductor: refused, still opus\n{REFUSED}{where(self.p, 'opus')}\n")
                self.assertNotIn(value, out)
                self.assertEqual(self.entry(self.p).read_bytes().strip(), b"opus")

    def test_a_value_that_is_not_text_is_refused(self):
        event = {"hook_event_name": "UserPromptExpansion", "session_id": "s1", "cwd": self.p,
                 "expansion_type": "slash_command", "command_name": "swd:conductor", "prompt": "/swd:conductor"}
        for args in (["opus"], 5, {"opus": 1}):
            with self.subTest(args=args):
                self.assertEqual(self.ok({**event, "command_args": args}),
                                 f"swd conductor: refused, still fable\n{REFUSED}{where(self.p, 'fable')}\n")
        for args in (None, ""):  # no value: a read
            with self.subTest(args=args):
                self.assertEqual(self.ok({**event, "command_args": args}),
                                 f"swd conductor: fable\n{where(self.p, 'fable')}\n")
        self.assertFalse((self.home / ".claude").exists())

    def test_without_a_usable_folder_nothing_is_stored(self):
        for cwd in (MISSING, 5, [], None, "", "rel/x"):
            with self.subTest(cwd=cwd):
                self.assertEqual(self.conductor(cwd), f"swd conductor: fable\n{NOT_TOLD}\n")
                self.assertEqual(self.conductor(cwd, "opus"), f"swd conductor: not stored, still fable\n{NOT_TOLD}\n")
                self.assertEqual(self.conductor(cwd, "sonnet"), f"swd conductor: refused, still fable\n{REFUSED}{NOT_TOLD}\n")
                self.assertFalse((self.home / ".claude").exists())

    def test_a_folder_at_the_entry_is_not_stored_and_says_why(self):
        entry = self.entry(self.p)
        entry.mkdir(parents=True)
        lines = self.conductor(self.p, "opus").splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertEqual(lines[0], "swd conductor: not stored, still fable")
        self.assertTrue(lines[1].startswith(f"The hook could not write {entry}: "), lines[1])
        self.assertTrue(lines[1].endswith(". " + where(self.p, "fable")), lines[1])
        self.assertTrue(entry.is_dir())

    def test_the_command_needs_no_session_and_leaves_swd_mode_alone(self):
        for session in ("", "../x", MISSING, "s1"):
            with self.subTest(session=session):
                self.assertEqual(self.setting_after(self.p, "opus"), "swd conductor: set to opus")
                self.assertEqual(self.setting_after(self.p, "fable"), "swd conductor: set to fable")
                self.assertFalse((self.home / ".claude" / "swd-mode").exists())
        self.assertEqual(self.prompt(self.p), "")  # swd mode stayed off

    def test_the_command_does_not_turn_swd_mode_off_or_repeat_the_reminder(self):
        self.mode_on()
        self.assertEqual(self.conductor(self.p, "opus"), f"swd conductor: set to opus\n{where(self.p, 'opus')}\n")
        self.assertTrue(self.flag().is_file())

    # Where the setting applies

    def test_two_projects_have_their_own_setting(self):
        self.conductor(self.p, "opus")
        self.mode_on()
        self.assertEqual(self.conductor(self.q), f"swd conductor: fable\n{where(self.q, 'fable')}\n")
        self.assertEqual(self.prompt(self.q).strip().splitlines()[-1], ON_SENTENCE)
        self.assertBlocked(self.switch(self.q, FABLE, OPUS), MESSAGE)
        self.assertEqual(self.prompt(self.p).strip().splitlines()[-1], ON_OPUS_SENTENCE)
        self.assertAllowed(self.switch(self.p, FABLE, OPUS))

    def test_a_worktree_and_the_folders_below_it_have_the_projects_setting(self):
        self.conductor(self.p, "opus")
        for cwd in (self.worktree, str(Path(self.worktree, "tests")), str(Path(self.worktree, "a", "b"))):
            with self.subTest(cwd=cwd):
                self.assertEqual(self.conductor(cwd), f"swd conductor: opus\n{where(self.p, 'opus')}\n")
        # Set from inside a worktree, it is the project's setting.
        self.assertEqual(self.conductor(self.worktree, "fable"),
                         f"swd conductor: set to fable\n{where(self.p, 'fable')}\n")
        self.assertEqual(self.setting(self.p), "swd conductor: fable")

    def test_other_folders_of_the_project_are_other_keys(self):
        self.conductor(self.p, "opus")
        src = str(Path(self.p, "src"))
        for cwd in (src, str(Path(self.p, ".swd")), str(Path(self.p, ".swd", "worktrees")),
                    str(Path(self.p, ".swd", "runs", "x")), str(Path(self.p, "worktrees", "x"))):
            with self.subTest(cwd=cwd):
                self.assertEqual(self.conductor(cwd), f"swd conductor: fable\n{where(cwd, 'fable')}\n")

    # Only a typed command stores (criterion 5)

    def test_a_prompt_with_the_commands_text_stores_nothing(self):
        self.mode_on()
        for text in ("/swd:conductor opus", "/swd:conductor  opus", "please run /swd:conductor opus"):
            with self.subTest(text=text):
                self.assertEqual(self.prompt(self.p, text).strip().splitlines()[-1], ON_SENTENCE)
                self.assertFalse((self.home / ".claude" / "swd-conductor").exists())
        self.assertEqual(self.setting(self.p), "swd conductor: fable")

    def test_an_expansion_for_another_command_stores_nothing(self):
        for name in ("swd:conductorx", "conductor", "other:conductor", "SWD:CONDUCTOR", "swd:conductor ",
                     "swd:build", None, 5, ["swd:conductor"]):
            with self.subTest(command_name=name):
                event = {"hook_event_name": "UserPromptExpansion", "session_id": "x" + str(len(str(name))),
                         "cwd": self.p, "expansion_type": "slash_command", "command_name": name,
                         "command_args": "opus", "command_source": "plugin", "prompt": "/swd:conductor opus"}
                self.assertFalse(self.ok(event).startswith("swd conductor"))
                self.assertFalse((self.home / ".claude" / "swd-conductor").exists())

    # A stored entry the hook cannot use is fable (criterion 6)

    def assertReadsFable(self, cwd):
        self.assertEqual(self.setting(cwd), "swd conductor: fable")
        self.assertEqual(self.prompt(cwd).strip().splitlines()[-1], ON_SENTENCE)
        self.assertBlocked(self.switch(cwd, FABLE, OPUS), MESSAGE)

    def test_an_entry_holding_anything_but_opus_reads_fable(self):
        self.mode_on()
        for content in (b"", b"OPUS\n", b"opus extra\n", b"fable\n", b"opusopus", b"x" * 100 + b"opus"):
            with self.subTest(content=content):
                self.entry(self.p).parent.mkdir(parents=True, exist_ok=True)
                self.entry(self.p).write_bytes(content)
                self.assertReadsFable(self.p)

    def test_an_entry_that_is_a_folder_reads_fable(self):
        self.mode_on()
        self.entry(self.p).mkdir(parents=True)
        self.assertReadsFable(self.p)

    @unittest.skipIf(os.name == "nt", "creating a symlink on Windows needs Developer Mode or admin rights")
    def test_an_entry_that_is_a_link_to_opus_reads_fable(self):
        self.mode_on()
        target = self.home / "opus.txt"
        target.write_bytes(b"opus\n")
        self.entry(self.p).parent.mkdir(parents=True)
        self.entry(self.p).symlink_to(target)
        self.assertReadsFable(self.p)

    @unittest.skipIf(os.name == "nt", "Windows has no os.geteuid, and chmod does not stop a read there")
    def test_an_unreadable_entry_reads_fable(self):
        if os.geteuid() == 0:
            self.skipTest("root can read a file whatever its mode")
        self.mode_on()
        self.conductor(self.p, "opus")
        self.entry(self.p).chmod(0)
        self.assertReadsFable(self.p)

    @unittest.skipIf(os.name == "nt", "creating a symlink on Windows needs Developer Mode or admin rights")
    def test_storing_over_a_link_replaces_the_link_and_leaves_its_target_alone(self):
        for name, content in (("precious.txt", b"precious data"), ("nothing-here", None)):
            with self.subTest(target=name):
                target = self.home / name
                if content is not None:
                    target.write_bytes(content)
                entry = self.entry(self.p)
                entry.parent.mkdir(parents=True, exist_ok=True)
                entry.unlink(missing_ok=True)
                entry.symlink_to(target)
                self.assertEqual(self.setting_after(self.p, "opus"), "swd conductor: set to opus")
                self.assertFalse(entry.is_symlink())
                self.assertEqual(entry.read_bytes().strip(), b"opus")
                if content is None:
                    self.assertFalse(os.path.lexists(target))
                else:
                    self.assertEqual(target.read_bytes(), content)

    # The reminder

    def test_the_reminder_names_both_models_under_opus(self):
        self.conductor(self.p, "opus")
        fable = self.on(self.q)
        self.assertEqual(fable.strip().splitlines()[-1], ON_SENTENCE)
        self.assertEqual(self.prompt(self.q), fable)  # the expansion's reminder is the prompt's
        for cwd in (self.p, self.worktree, str(Path(self.worktree, "tests"))):
            with self.subTest(cwd=cwd):
                opus = self.prompt(cwd)
                self.assertEqual(opus.strip().splitlines()[-1], ON_OPUS_SENTENCE)
                self.assertEqual(opus.splitlines()[:-1], fable.splitlines()[:-1])  # only the last line differs
        self.assertEqual(self.prompt(str(Path(self.p, "src"))), fable)

    def test_turning_swd_mode_on_in_a_project_set_to_opus_prints_its_reminder(self):
        self.conductor(self.p, "opus")
        out = self.on(str(Path(self.worktree, "tests")))
        self.assertTrue(out.startswith("swd mode: on\n"), out)
        self.assertEqual(out.strip().splitlines()[-1], ON_OPUS_SENTENCE)

    # The switch rule

    def test_under_opus_a_switch_between_fable_and_opus_is_allowed_both_ways(self):
        self.conductor(self.p, "opus")
        self.mode_on()
        fables = (FABLE, "claude-fable-5-2[1m]", "us.anthropic.claude-fable-5-2-v1:0", "Claude-Fable-5-2")
        opuses = (OPUS, "claude-opus-5-5[1m]", "us.anthropic.claude-opus-5-5-v1:0", "Claude-Opus-5-5")
        for cwd in (self.p, self.worktree):
            for fable in fables:
                for opus in opuses:
                    with self.subTest(cwd=cwd, fable=fable, opus=opus):
                        self.assertAllowed(self.switch(cwd, fable, opus))
                        self.assertAllowed(self.switch(cwd, opus, fable))

    def test_under_opus_a_switch_from_either_to_another_model_is_cancelled(self):
        self.conductor(self.p, "opus")
        self.mode_on()
        for from_model in (FABLE, OPUS, "claude-opus-5-5[1m]", "us.anthropic.claude-opus-5-5-v1:0",
                           "claude-fable-5-2[1m]"):
            for to_model in (SONNET, HAIKU, "claude-opus-5-50", "claude-fable-5-21", "claude-opus-5-4"):
                with self.subTest(from_model=from_model, to_model=to_model):
                    self.assertBlocked(self.switch(self.worktree, from_model, to_model), OPUS_MESSAGE)

    def test_under_opus_a_switch_from_another_model_or_with_mode_off_is_allowed(self):
        self.conductor(self.p, "opus")
        self.assertAllowed(self.switch(self.p, OPUS, SONNET))  # swd mode off
        self.mode_on()
        for from_model in ("claude-opus-5-50", SONNET, HAIKU, "claude-opus-5-4"):
            with self.subTest(from_model=from_model):
                self.assertAllowed(self.switch(self.p, from_model, SONNET))

    def test_under_fable_the_switch_rule_is_as_in_0_9_0(self):
        self.mode_on()
        for stored in (None, "fable"):
            if stored:
                self.conductor(self.p, stored)
            with self.subTest(stored=stored):
                for to_model in (OPUS, "claude-opus-5-5[1m]", "us.anthropic.claude-opus-5-5-v1:0", SONNET, HAIKU):
                    self.assertBlocked(self.switch(self.p, FABLE, to_model), MESSAGE)
                for to_model in (SONNET, HAIKU, FABLE):
                    self.assertAllowed(self.switch(self.p, OPUS, to_model))  # not from the principal's model

    # A bad cwd never raises and never turns a cancel into an allow

    def test_a_bad_cwd_changes_nothing(self):
        self.mode_on()
        surrogate = str(Path(self.p, "\ud800"))
        for cwd in (MISSING, 5, [], None, "", "rel/x", surrogate):
            with self.subTest(cwd=repr(cwd)):
                self.assertBlocked(self.switch(cwd, FABLE, SONNET), MESSAGE)
                self.assertTrue(self.prompt(cwd).startswith("swd mode: on\n"))
                self.conductor(cwd)  # exits 0, checked by ok()
                self.conductor(cwd, "opus")
                self.conductor(cwd, "zzz")
        # The surrogate is an absolute path, so it was stored: Fable to Sonnet is still cancelled there.
        self.assertBlocked(self.switch(surrogate, FABLE, SONNET), OPUS_MESSAGE)

    # Fixes after the T1 security review

    @unittest.skipIf(not hasattr(os, "mkfifo"), "this platform has no FIFOs")
    def test_an_entry_swapped_for_a_fifo_after_its_check_reads_fable_at_once(self):
        self.mode_on()
        self.conductor(self.p, "opus")
        self.entry(self.p).unlink()
        os.mkfifo(self.entry(self.p))
        swapped = [sys.executable, "-c", WRAPPER, str(HOOK), "3", "regular"]  # the lstat race, lost for certain
        started = time.monotonic()
        result = self.switch(self.p, FABLE, SONNET, command=swapped)
        elapsed = time.monotonic() - started
        self.assertBlocked(result, MESSAGE)  # a stalled open would end in the watchdog's allow
        self.assertLess(elapsed, 1.5)
        self.assertEqual(self.prompt(self.p, command=swapped).strip().splitlines()[-1], ON_SENTENCE)
        self.assertEqual(self.conductor(self.p, command=swapped), f"swd conductor: fable\n{where(self.p, 'fable')}\n")

    def test_a_cwd_that_climbs_with_dot_dot_reads_fable(self):
        self.conductor(self.q, "opus")
        self.mode_on()
        climbed = str(Path(self.q, ".swd", "worktrees", "x", "..", "..", "..", "..", "p"))
        self.assertEqual(self.conductor(climbed), f"swd conductor: fable\n{NOT_TOLD}\n")
        self.assertReadsFable(climbed)
        self.assertEqual(self.conductor(climbed, "opus"), f"swd conductor: not stored, still fable\n{NOT_TOLD}\n")
        self.assertEqual(os.listdir(self.entry(self.q).parent), [self.entry(self.q).name])
        self.assertEqual(self.entry(self.q).read_bytes().strip(), b"opus")

    def test_a_folder_name_cannot_add_a_line_to_the_reply(self):
        demo = Path(self.p).parent
        breaks = ("\n", "\x0b", "\x0c", "\r", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")
        self.assertEqual(breaks, tuple(c for c in map(chr, range(0x110000)) if len(f"a{c}b".splitlines()) == 2))
        for char in breaks:
            with self.subTest(char=repr(char)):
                cwd = str(demo / ("a" + char + "b"))
                key = str(demo / "a?b")
                for args, first, setting in (("", "swd conductor: fable", "fable"),
                                             ("opus", "swd conductor: set to opus", "opus"),
                                             ("", "swd conductor: opus", "opus")):
                    out = self.conductor(cwd, args)
                    self.assertEqual(len(out.splitlines()), 2, out)
                    self.assertEqual(out, f"{first}\n{where(key, setting)}\n")
                out = self.conductor(cwd, "sonnet")
                self.assertEqual(out, f"swd conductor: refused, still opus\n{REFUSED}{where(key, 'opus')}\n")
                self.assertTrue(self.entry(cwd).is_file())  # stored under the folder's own text
                self.assertFalse(self.entry(key).exists())

    @unittest.skipIf(os.name == "nt", "Windows does not allow a line break in a folder name")
    def test_the_could_not_write_line_shows_the_entry_without_a_line_break(self):
        self.home = self.home.parent / "ho\nme"
        self.home.mkdir()
        demo = Path(self.p).parent
        cwd, key = str(demo / "a\nb"), str(demo / "a?b")
        entry = self.entry(cwd)
        entry.mkdir(parents=True)
        lines = self.conductor(cwd, "opus").splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertEqual(lines[0], "swd conductor: not stored, still fable")
        self.assertTrue(lines[1].startswith(f"The hook could not write {str(entry).replace(chr(10), '?')}: "), lines[1])
        self.assertTrue(lines[1].endswith(". " + where(key, "fable")), lines[1])


class HooksJsonTest(unittest.TestCase):
    """The command hooks.json registers, run as Claude Code runs it: `sh -c`, which is Git Bash on Windows."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home"
        self.bin = Path(tmp.name) / "bin"  # the whole PATH: no Python but the stubs written here
        for folder in (self.home, self.bin):
            folder.mkdir()
        if SH is None:
            self.fail("no sh on PATH: the plugin's hooks need it")
        self.stub("sh", f'exec {shlex.quote(SH.replace(os.sep, "/"))} "$@"')
        self.stub("uname", "echo Linux")
        if os.name == "nt":
            self.stub("cygpath", f'exec {shlex.quote(shutil.which("cygpath").replace(os.sep, "/"))} "$@"')

    def stub(self, name, body):
        path = self.bin / name
        path.write_bytes(f"#!/bin/sh\n{body}\n".encode("utf-8"))  # LF, also on Windows
        path.chmod(0o755)

    def store_stub(self, name):
        self.stub(name, "echo 'Python was not found; run without arguments to install from the Microsoft "
                        "Store' >&2\nexit 49")

    def hook(self, event):
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
        command = hooks[event["hook_event_name"]][0]["hooks"][0]["command"]
        command = command.replace("${CLAUDE_PLUGIN_ROOT}", ROOT.as_posix())
        return subprocess.run([SH, "-c", command], input=json.dumps(event).encode("utf-8"), capture_output=True,
                              env=clean_env(self.home, path=str(self.bin)), cwd=self.home, timeout=30)

    def test_the_hook_is_registered_for_all_three_events(self):
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(set(hooks), {"UserPromptSubmit", "UserPromptExpansion", "PreModelSwitch"})
        for event in hooks:
            with self.subTest(event=event):
                commands = [h for group in hooks[event] for h in group["hooks"]]
                self.assertEqual(len(commands), 1)
                self.assertEqual(commands[0]["type"], "command")
                self.assertEqual(commands[0]["command"], HOOK_COMMAND)
                self.assertEqual(commands[0]["timeout"], 10)
                self.assertNotIn("matcher", hooks[event][0])

    def test_the_hook_command_runs_with_only_python_on_path(self):
        self.store_stub("python3")
        self.stub("python", f'exec {shlex.quote(sys.executable.replace(os.sep, "/"))} "$@"')
        on = self.hook({"hook_event_name": "UserPromptExpansion", "session_id": "s1", "command_name": "swd:on",
                        "expansion_type": "slash_command", "command_args": "", "prompt": "/swd:on"})
        self.assertEqual((on.returncode, on.stderr), (0, b""))
        self.assertTrue(on.stdout.decode("utf-8").startswith("swd mode: on"), on.stdout)
        switch = self.hook({"hook_event_name": "PreModelSwitch", "session_id": "s1", "from_model": FABLE,
                            "to_model": SONNET})
        self.assertEqual((switch.returncode, switch.stdout, switch.stderr.decode("utf-8").strip()), (2, b"", MESSAGE))

    def test_the_hook_command_without_python_blocks_nothing(self):
        for name in ("python3", "python"):
            self.store_stub(name)
        (self.home / ".claude" / "swd-mode").mkdir(parents=True)
        (self.home / ".claude" / "swd-mode" / "s1").write_bytes(b"")  # mode on: a hook that ran would cancel
        for event in ({"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "/swd:off"},
                      {"hook_event_name": "UserPromptExpansion", "session_id": "s1", "command_name": "swd:on"},
                      {"hook_event_name": "PreModelSwitch", "session_id": "s1", "from_model": FABLE,
                       "to_model": SONNET}):
            with self.subTest(event=event["hook_event_name"]):
                result = self.hook(event)
                self.assertEqual((result.returncode, result.stdout.decode("utf-8"), result.stderr),
                                 (0, NOTICE, b""))
        self.assertTrue((self.home / ".claude" / "swd-mode" / "s1").is_file())  # the off prompt never reached it


if __name__ == "__main__":
    unittest.main()
