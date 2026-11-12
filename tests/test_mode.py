"""Tests for hooks/swd-mode.py, the UserPromptSubmit hook that keeps a session in swd mode."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "swd-mode.py"


class ModeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = self._tmp.name

    def prompt(self, text, session="s1", raw=None):
        payload = raw if raw is not None else json.dumps(
            {"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": text})
        result = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True,
                                env={"HOME": self.home, "PATH": "/usr/bin:/bin"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result.stdout

    def test_off_by_default(self):
        self.assertEqual(self.prompt("add a login page"), "")

    def test_build_turns_it_on_and_it_stays_on(self):
        self.assertIn("swd mode: on", self.prompt("/swd:build add a login page"))
        later = self.prompt("now add a logout button")
        self.assertIn("swd mode: on", later)
        self.assertIn("swd:build", later)          # how to route a change
        self.assertIn("stop swd", later)           # how to leave

    def test_on_command_turns_it_on(self):
        self.assertIn("swd mode: on", self.prompt("/swd:on"))
        self.assertIn("swd mode: on", self.prompt("fix the typo in the README"))

    def test_other_sessions_are_not_affected(self):
        self.prompt("/swd:on", session="s1")
        self.assertEqual(self.prompt("add a login page", session="s2"), "")

    def test_stop_phrase_and_off_command_turn_it_off(self):
        for stop in ("stop swd", "Please STOP SWD now", "/swd:off"):
            with self.subTest(stop=stop):
                self.prompt("/swd:on")
                self.assertIn("swd mode: off", self.prompt(stop))
                self.assertEqual(self.prompt("add a login page"), "")

    def test_mentioning_swd_does_not_turn_it_on(self):
        self.assertEqual(self.prompt("how does /swd:build work?"), "")
        self.assertEqual(self.prompt("what is swd mode: on?"), "")

    def test_bad_input_is_ignored(self):
        self.assertEqual(self.prompt("", raw="not json"), "")
        self.assertEqual(self.prompt("", raw=json.dumps({"prompt": "/swd:on"})), "")  # no session id

    def test_session_id_cannot_escape_the_state_folder(self):
        self.prompt("/swd:on", session="../../escaped")
        self.assertFalse((Path(self.home) / "escaped").exists())
        self.assertFalse((Path(self.home) / ".claude" / "escaped").exists())


if __name__ == "__main__":
    unittest.main()
