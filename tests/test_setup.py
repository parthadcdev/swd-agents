"""Tests for scripts/swd-setup.py: the permission rules a project needs so swd runs are not held for approval."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "swd-setup.py"
sys.path.insert(0, str(ROOT / "scripts"))


class SetupTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name)
        self.settings = self.project / ".claude" / "settings.local.json"

    def setup(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), *args, str(self.project)], capture_output=True, text=True)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def allow(self):
        return json.loads(self.settings.read_text())["permissions"]["allow"]

    def test_print_shows_the_rules_and_writes_nothing(self):
        result = self.setup("--print")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Bash(git *)", result.stdout)
        self.assertFalse(self.settings.exists())

    def test_writes_rules_for_the_plugin_git_the_run_folder_and_the_test_command(self):
        (self.project / ".swd").mkdir()
        (self.project / ".swd" / "project.md").write_text("## Commands\nTest command: `npm test`\n")
        self.assertEqual(self.setup().returncode, 0)
        allow = self.allow()
        for rule in ("Bash(git *)", "Bash(gh pr *)", "Bash(npm test)", "Bash(npm test *)", "Edit(/.swd/**)", "Bash(pwd)"):
            with self.subTest(rule=rule):
                self.assertIn(rule, allow)
        self.assertTrue(any(r.startswith("Bash(python3 ") and "swd" in r for r in allow))  # the plugin's scripts

    def test_commands_can_be_named_before_the_project_notes_exist(self):
        # On a first run nothing has recorded the test command yet.
        self.assertEqual(self.setup("--command", "python3 -m unittest", "--command", "ruff check").returncode, 0)
        allow = self.allow()
        for rule in ("Bash(python3 -m unittest)", "Bash(python3 -m unittest *)", "Bash(ruff check)", "Bash(ruff check *)"):
            with self.subTest(rule=rule):
                self.assertIn(rule, allow)

    def test_existing_settings_are_kept_and_rules_are_not_duplicated(self):
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({"permissions": {"allow": ["Bash(make *)", "Bash(git *)"], "deny": ["Bash(rm *)"]},
                                             "env": {"X": "1"}}))
        self.setup()
        self.setup()
        data = json.loads(self.settings.read_text())
        self.assertEqual(data["env"], {"X": "1"})
        self.assertEqual(data["permissions"]["deny"], ["Bash(rm *)"])
        allow = data["permissions"]["allow"]
        self.assertEqual(allow[:2], ["Bash(make *)", "Bash(git *)"])
        self.assertEqual(len(allow), len(set(allow)))

    def test_unreadable_settings_are_not_overwritten(self):
        self.settings.parent.mkdir()
        self.settings.write_text("{ not json")
        result = self.setup()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.settings.read_text(), "{ not json")

    def test_an_installed_plugin_gets_a_rule_that_survives_updates(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("swd_setup", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        installed = Path.home() / ".claude" / "plugins" / "cache" / "swd-agents" / "swd" / "0.5.0"
        self.assertEqual(module.plugin_prefix(installed), str(installed.parent) + "/")   # no version in it
        self.assertEqual(module.plugin_prefix(Path("/work/swd-agents")), "/work/swd-agents/")


if __name__ == "__main__":
    unittest.main()
