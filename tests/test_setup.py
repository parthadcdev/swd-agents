"""Tests for scripts/swd-setup.py: the permission rules a project needs so swd runs are not held for approval."""
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath

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
        result = subprocess.run([sys.executable, str(SCRIPT), *args, str(self.project)], capture_output=True, text=True, encoding="utf-8")
        self.assertNotIn("Traceback", result.stderr)
        return result

    def allow(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))["permissions"]["allow"]

    def test_print_shows_the_rules_and_writes_nothing(self):
        result = self.setup("--print")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Bash(git *)", result.stdout)
        self.assertFalse(self.settings.exists())

    def test_writes_rules_for_the_plugin_git_the_run_folder_and_the_test_command(self):
        (self.project / ".swd").mkdir()
        (self.project / ".swd" / "project.md").write_text("## Commands\nTest command: `npm test`\n", encoding="utf-8")
        self.assertEqual(self.setup().returncode, 0)
        allow = self.allow()
        for rule in ("Bash(git *)", "Bash(gh pr *)", "Bash(npm test)", "Bash(npm test *)", "Edit(/.swd/**)", "Bash(pwd)",
                     "Bash(echo *)", "Bash(cat *)", "Bash(mkdir *)", "Bash(touch *)"):   # the principal's own chained commands use these
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
                                             "env": {"X": "1"}}), encoding="utf-8")
        self.setup()
        self.setup()
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["env"], {"X": "1"})
        self.assertEqual(data["permissions"]["deny"], ["Bash(rm *)"])
        allow = data["permissions"]["allow"]
        self.assertEqual(allow[:2], ["Bash(make *)", "Bash(git *)"])
        self.assertEqual(len(allow), len(set(allow)))

    def test_unreadable_settings_are_not_overwritten(self):
        self.settings.parent.mkdir()
        self.settings.write_text("{ not json", encoding="utf-8")
        result = self.setup()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{ not json")

    def module(self):
        spec = importlib.util.spec_from_file_location("swd_setup", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_an_installed_plugin_gets_a_rule_that_survives_updates(self):
        module = self.module()
        installed = Path.home() / ".claude" / "plugins" / "cache" / "swd-agents" / "swd" / "0.5.0"
        self.assertEqual(module.plugin_prefix(installed), installed.parent.as_posix() + "/")   # no version in it
        self.assertEqual(module.plugin_prefix(Path("/work/swd-agents")), "/work/swd-agents/")

    def test_print_lists_the_rules_for_a_posix_plugin_root(self):
        result = self.setup("--print", "--plugin-root", "/work/swd-agents")
        self.assertEqual(result.returncode, 0, result.stderr)
        listed = [line.strip() for line in result.stdout.splitlines()[1:]]
        self.assertEqual(listed[:10], [
            "Bash(python3 /work/swd-agents/*)",
            "Bash(python /work/swd-agents/*)",
            "Bash(py -3 /work/swd-agents/*)",
            "Bash(sh /work/swd-agents/scripts/swd-python.sh check)",
            "Bash(sh /work/swd-agents/scripts/swd-watch.sh *)",
            "Read(//work/swd-agents/**)",
            "Bash(git *)",
            "Bash(gh pr *)",
            "Edit(/.swd/**)",
            "Read(/.swd/**)",
        ])
        self.assertIn("Bash(pwd)", listed)
        self.assertNotIn("Bash(/work/swd-agents/*)", listed)   # nothing runs a plugin file directly
        self.assertFalse([rule for rule in listed if "swd-python.sh run" in rule or "install" in rule])

    def test_rules_for_a_windows_plugin_root_use_forward_slashes_and_the_c_drive_form(self):
        module = self.module()
        rules = module.rules(self.project, PureWindowsPath(r"C:\work\swd-agents"))
        self.assertEqual(rules[:10], [
            "Bash(python3 C:/work/swd-agents/*)",
            "Bash(python C:/work/swd-agents/*)",
            "Bash(py -3 C:/work/swd-agents/*)",
            "Bash(sh C:/work/swd-agents/scripts/swd-python.sh check)",
            "Bash(sh C:/work/swd-agents/scripts/swd-watch.sh *)",
            "Read(//c/work/swd-agents/**)",
            "Bash(git *)",
            "Bash(gh pr *)",
            "Edit(/.swd/**)",
            "Read(/.swd/**)",
        ])
        self.assertFalse([rule for rule in rules if "\\" in rule])

    def test_an_installed_windows_plugin_is_read_through_its_version_free_folder(self):
        module = self.module()
        installed = PureWindowsPath(r"C:\Users\you\.claude\plugins\cache\swd-agents\swd\0.9.0")
        self.assertEqual(module.plugin_prefix(installed), "C:/Users/you/.claude/plugins/cache/swd-agents/swd/")
        self.assertIn("Read(//c/Users/you/.claude/plugins/cache/swd-agents/swd/**)", module.rules(self.project, installed))

    ROOTS = {
        "installed": PurePosixPath("/Users/you/.claude/plugins/cache/swd-agents/swd/0.9.0"),
        "installed on Windows": PureWindowsPath(r"C:\Users\you\.claude\plugins\cache\swd-agents\swd\0.9.0"),
        "checkout": PurePosixPath("/work/swd-agents"),
    }

    def test_each_sh_rule_matches_the_command_the_skills_run(self):
        # The skills run `sh <plugin>/scripts/...`, where <plugin> is ${CLAUDE_PLUGIN_ROOT}: for an installed
        # plugin that is the folder named for its version, and the two sh rules name that folder exactly.
        module = self.module()
        for name, root in self.ROOTS.items():
            rules = module.rules(self.project, root)
            plugin = root.as_posix()
            with self.subTest(root=name, rules="sh rules have no wildcard in the path"):
                check, watch = [r for r in rules if r.startswith("Bash(sh ")]
                self.assertEqual(check, f"Bash(sh {plugin}/scripts/swd-python.sh check)")
                self.assertEqual(watch, f"Bash(sh {plugin}/scripts/swd-watch.sh *)")
                self.assertFalse(set("*?[") & set(check), check)
                self.assertEqual((watch.count("*"), watch[:-1].endswith(" *")), (1, True), watch)
            for command in (f"sh {plugin}/scripts/swd-python.sh check",
                            f"sh {plugin}/scripts/swd-watch.sh .swd/runs/2026-11-16-demo"):
                with self.subTest(root=name, command=command):
                    self.assertTrue([rule for rule in rules if allows(rule, command)], rules)
            prefix = module.plugin_prefix(root)
            launcher = f"sh {plugin}/scripts/swd-python.sh"
            for command in (f"{launcher} run {plugin}/scripts/check_run.py",
                            f"{launcher} install --yes",
                            # stretched to end in a rule's tail (found by the T2 security review)
                            f"{launcher} run payload.py scripts/swd-python.sh check",
                            f"{launcher} run payload.py #scripts/swd-python.sh check",
                            f"{launcher} install --yes scripts/swd-python.sh check",
                            f"{launcher} install --yes #scripts/swd-python.sh check",
                            f"{launcher} run payload.py scripts/swd-watch.sh y",
                            f"sh {prefix}../../../payload.sh scripts/swd-python.sh check",
                            f"sh {prefix}../../../elsewhere/scripts/swd-python.sh check",
                            f"sh {prefix}../../../payload.sh scripts/swd-watch.sh y"):
                with self.subTest(root=name, command=command):
                    self.assertEqual([rule for rule in rules if allows(rule, command)], [])
        # Another version's commands are not allowed by the rules built for 0.9.0; setup must be run again.
        rules = module.rules(self.project, self.ROOTS["installed"])
        newer = self.ROOTS["installed"].parent / "0.9.1"
        for command in (f"sh {newer}/scripts/swd-python.sh check", f"sh {newer}/scripts/swd-watch.sh .swd/runs/x"):
            with self.subTest(command=command):
                self.assertEqual([rule for rule in rules if allows(rule, command)], [])

    def test_rules_for_an_older_version_count_as_missing(self):
        # After a plugin update, setup adds the new version's sh rules and keeps the old ones (it never removes).
        old = "/Users/you/.claude/plugins/cache/swd-agents/swd/0.8.0"
        new = "/Users/you/.claude/plugins/cache/swd-agents/swd/0.9.0"
        self.assertEqual(self.setup("--plugin-root", old).returncode, 0)
        result = self.setup("--plugin-root", new)
        self.assertIn("setup: 2 rules added", result.stdout)
        allow = self.allow()
        for version in (old, new):
            for rule in (f"Bash(sh {version}/scripts/swd-python.sh check)", f"Bash(sh {version}/scripts/swd-watch.sh *)"):
                with self.subTest(rule=rule):
                    self.assertIn(rule, allow)


def allows(rule, command):
    """Whether a Bash(...) rule covers the whole command, `*` standing for any text, spaces included.
    This approximates Claude Code's matcher; it is not the matcher itself."""
    match = re.fullmatch(r"Bash\((.*)\)", rule, re.S)
    pattern = ".*".join(re.escape(part) for part in match.group(1).split("*")) if match else None
    return bool(pattern) and re.fullmatch(pattern, command, re.S) is not None


if __name__ == "__main__":
    unittest.main()
