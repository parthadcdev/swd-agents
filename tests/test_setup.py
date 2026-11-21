"""Tests for scripts/swd-setup.py: the permission rules a project needs so swd runs are not held for approval."""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "swd-setup.py"
sys.path.insert(0, str(ROOT / "scripts"))
DENY = ["Bash(python3 *swd-mode.*)", "Bash(python *swd-mode.*)", "Bash(py *swd-mode.*)"]   # unchanged since 0.10.0
ASK = ["Bash(python3 *swd-setup.*)", "Bash(python *swd-setup.*)", "Bash(py *swd-setup.*)",
       "Bash(python3 *swd-queue.*)", "Bash(python *swd-queue.*)", "Bash(py *swd-queue.*)",
       "Bash(*SWD_UNATTENDED*)"]   # contract C1
PYTHONS = ("python3", "python", "py -3")
RUN_SCRIPTS = ("check_run.py", "swd-clean.py", "swd-dashboard.py", "swd-findings.py", "swd-log.py", "swd-pr.py", "swd-test.py")
ASK_HEADING = "Ask rules, so Claude Code asks you before a command runs the setup or queue script, or names SWD_UNATTENDED:"
DENY_HEADING = "Deny rules, so Claude Code refuses the plain ways of running the plugin's hook by name:"
OLD_HEADING = "Rules an earlier version of the plugin wrote, which setup removes:"
REFUSAL = ("a rule's first word must be the command's own name, with no '*' in it, and the command may hold no control "
           "character; '*' there would let the rule match every command")
RUNNER = ("a rule's first word must name the program that runs, not an assignment or a program that runs another command "
          "it is given (env, sh, bash, zsh, dash, ksh, fish, xargs, sudo, doas, eval, exec, npx), or the rule would match "
          'every command; give the command itself, such as "npm test" or "bash scripts/test.sh"')
NOT_PLAIN = ("a rule's first word must be a plain program name or path, made only of letters, digits and . _ - + @ / : and not "
             "starting with -; quotes, backslashes, =, [, $, backticks, redirections and other shell syntax are refused, "
             "because the rule would then not name the program that runs")
ROOT_REFUSAL = ("a plugin path must be absolute (a single / at the start, or on Windows a drive letter and /), at least two "
                "folders below the root and not your home folder or above it, with no . or .. folder, and made only of letters, "
                "digits and . _ - + @ / : ~, with no space; any other path would make the rules match commands or files other "
                "than the plugin's scripts; run setup from a plugin folder whose path is such a path")   # contract C1
NOTES = "the test command in .swd/project.md"
INSTALLED = "/Users/you/.claude/plugins/cache/swd-agents/swd"   # path text only; never exists
RUN = "/work/project/.swd/runs/2026-11-17-demo"
PROJECT = "/work/project"


def module():
    spec = importlib.util.spec_from_file_location("swd_setup", SCRIPT)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class SetupTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"   # setup must never see the real ~/.claude
        self.home.mkdir()
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.settings = self.project / ".claude" / "settings.local.json"

    def run_script(self, script, *args):
        env = {**os.environ, "HOME": str(self.home), "USERPROFILE": str(self.home)}
        result = subprocess.run([sys.executable, str(script), *args, str(self.project)],
                                capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def setup(self, *args):
        return self.run_script(SCRIPT, *args)

    def write_settings(self, text):
        self.settings.parent.mkdir(exist_ok=True)
        self.settings.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))

    def data(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def allow(self):
        return self.data()["permissions"]["allow"]

    def module(self):
        return module()

    # --- what is written --------------------------------------------------------------------------------------

    def test_print_shows_the_rules_and_writes_nothing(self):
        result = self.setup("--print")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Bash(git *)", result.stdout)
        self.assertFalse(self.settings.parent.exists())

    def test_writes_rules_for_the_plugin_git_the_run_folder_and_the_test_command(self):
        (self.project / ".swd").mkdir()
        (self.project / ".swd" / "project.md").write_text("## Commands\nTest command: `npm test`\n", encoding="utf-8")
        self.assertEqual(self.setup().returncode, 0)
        allow = self.allow()
        for rule in ("Bash(git *)", "Bash(gh pr *)", "Bash(npm test)", "Bash(npm test *)", "Edit(/.swd/**)", "Bash(pwd)",
                     "Bash(echo *)", "Bash(cat *)", "Bash(mkdir *)", "Bash(touch *)"):   # the principal's own chained commands use these
            with self.subTest(rule=rule):
                self.assertIn(rule, allow)
        plugin = Path(os.path.abspath(SCRIPT)).parent.parent.as_posix()
        self.assertIn(f"Bash(python3 {plugin}/scripts/check_run.py *)", allow)
        self.assertEqual(self.data()["permissions"]["ask"], ASK)
        self.assertEqual(self.data()["permissions"]["deny"], DENY)

    def test_commands_can_be_named_before_the_project_notes_exist(self):
        # On a first run nothing has recorded the test command yet.
        self.assertEqual(self.setup("--command", "python3 -m unittest", "--command", "ruff check").returncode, 0)
        allow = self.allow()
        for rule in ("Bash(python3 -m unittest)", "Bash(python3 -m unittest *)", "Bash(ruff check)", "Bash(ruff check *)"):
            with self.subTest(rule=rule):
                self.assertIn(rule, allow)

    def test_existing_settings_are_kept_and_rules_are_not_duplicated(self):
        self.write_settings(json.dumps({"permissions": {"allow": ["Bash(make *)", "Bash(git *)"], "deny": ["Bash(rm *)"]},
                                        "env": {"X": "1"}}))
        self.setup()
        before = self.settings.read_bytes()
        self.assertEqual(self.setup().stdout.strip(), "setup: nothing to add")
        self.assertEqual(self.settings.read_bytes(), before)
        data = self.data()
        self.assertEqual(data["env"], {"X": "1"})
        self.assertEqual(data["permissions"]["deny"], ["Bash(rm *)", *DENY])
        self.assertEqual(data["permissions"]["ask"], ASK)
        self.assertEqual(list(data["permissions"]), ["allow", "deny", "ask"])   # ask is created after the existing keys
        allow = data["permissions"]["allow"]
        self.assertEqual(allow[:2], ["Bash(make *)", "Bash(git *)"])
        self.assertEqual(len(allow), len(set(allow)))

    def test_deny_and_ask_rules_already_there_are_kept_in_order_and_not_added_twice(self):
        self.write_settings(json.dumps({"permissions": {"deny": ["Bash(py *swd-mode.*)", "Bash(rm *)"],
                                                        "ask": ["Bash(*SWD_UNATTENDED*)", "Bash(rm *)"]}}))
        self.setup()
        permissions = self.data()["permissions"]
        self.assertEqual(permissions["deny"], ["Bash(py *swd-mode.*)", "Bash(rm *)", "Bash(python3 *swd-mode.*)", "Bash(python *swd-mode.*)"])
        self.assertEqual(permissions["ask"], ["Bash(*SWD_UNATTENDED*)", "Bash(rm *)", *ASK[:6]])

    def test_the_count_includes_the_ask_and_deny_rules(self):
        allow_count = len(self.module().rules(self.project.resolve(), [Path("/work/swd-agents")]))
        self.assertEqual(allow_count, 42)
        result = self.setup("--plugin-root", "/work/swd-agents")
        self.assertEqual(result.stdout.strip(), f"setup: 52 rules added to {self.settings.resolve()}")
        self.assertEqual(self.data()["permissions"]["deny"], DENY)
        self.assertEqual(self.data()["permissions"]["ask"], ASK)

    def test_an_installed_plugin_gets_a_read_rule_that_survives_updates(self):
        installed = Path.home() / ".claude" / "plugins" / "cache" / "swd-agents" / "swd" / "0.5.0"
        self.assertEqual(self.module().plugin_prefix(installed), installed.parent.as_posix() + "/")   # no version in it
        self.assertEqual(self.module().plugin_prefix(Path("/work/swd-agents")), "/work/swd-agents/")

    def test_print_lists_the_rules_for_a_posix_plugin_root(self):
        result = self.setup("--print", "--plugin-root", "/work/swd-agents")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        settings = self.settings.resolve()
        self.assertEqual(lines[0], f"Rules for {settings}:")
        self.assertEqual(lines[-13:], [ASK_HEADING, *["  " + rule for rule in ASK], DENY_HEADING, *["  " + rule for rule in DENY],
                                       f"Not in place: {settings} is missing 52 of the rules above and still holds 0 rules"
                                       " an earlier version wrote; run /swd:setup."])
        self.assertFalse(self.settings.parent.exists())
        listed = [line.strip() for line in lines[1:-13]]
        self.assertEqual(len(listed), 42)
        self.assertFalse([rule for rule in listed if "swd-mode" in rule or "swd-setup" in rule or "swd-queue" in rule])
        self.assertEqual(listed[:10], [
            "Bash(python3 /work/swd-agents/scripts/check_run.py *)",
            "Bash(python /work/swd-agents/scripts/check_run.py *)",
            "Bash(py -3 /work/swd-agents/scripts/check_run.py *)",
            "Bash(python3 /work/swd-agents/scripts/swd-clean.py *)",
            "Bash(python /work/swd-agents/scripts/swd-clean.py *)",
            "Bash(py -3 /work/swd-agents/scripts/swd-clean.py *)",
            "Bash(python3 /work/swd-agents/scripts/swd-dashboard.py *)",
            "Bash(python /work/swd-agents/scripts/swd-dashboard.py *)",
            "Bash(py -3 /work/swd-agents/scripts/swd-dashboard.py *)",
            "Bash(python3 /work/swd-agents/scripts/swd-findings.py *)",
        ])
        self.assertEqual(listed[21:28], [
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

    def test_no_rule_lets_a_python_name_run_anything_under_the_plugin(self):
        # Criterion 1: no Bash(<python name> <prefix>*); one rule per run script per Python name, by its full path.
        for root in (PurePosixPath(f"{INSTALLED}/0.11.0"), PurePosixPath("/work/swd-agents"),
                     PureWindowsPath(r"C:\Users\you\.claude\plugins\cache\swd-agents\swd\0.11.0")):
            rules = self.module().rules(self.project, [root])
            prefix = self.module().plugin_prefix(root)
            with self.subTest(root=str(root)):
                self.assertFalse([rule for rule in rules if rule.startswith(tuple(f"Bash({p} {prefix}" for p in PYTHONS))
                                  and not re.fullmatch(r"Bash\(\S+(?: -3)? \S+/scripts/[\w-]+\.py \*\)", rule)])
                for script in RUN_SCRIPTS:
                    for python in PYTHONS:
                        self.assertIn(f"Bash({python} {root.as_posix()}/scripts/{script} *)", rules)

    def test_rules_for_a_windows_plugin_root_use_forward_slashes_and_the_c_drive_form(self):
        rules = self.module().rules(self.project, [PureWindowsPath(r"C:\work\swd-agents")])
        self.assertEqual(rules[:3], [
            "Bash(python3 C:/work/swd-agents/scripts/check_run.py *)",
            "Bash(python C:/work/swd-agents/scripts/check_run.py *)",
            "Bash(py -3 C:/work/swd-agents/scripts/check_run.py *)",
        ])
        self.assertEqual(rules[21:24], [
            "Bash(sh C:/work/swd-agents/scripts/swd-python.sh check)",
            "Bash(sh C:/work/swd-agents/scripts/swd-watch.sh *)",
            "Read(//c/work/swd-agents/**)",
        ])
        self.assertFalse([rule for rule in rules if "\\" in rule])

    def test_rules_for_a_windows_short_name_root_name_it_as_typed(self):
        # A root the Windows job accepts through the command line, built here on every platform through rules().
        rules = self.module().rules(self.project, [PureWindowsPath("C:/Users/RUNNER~1/x/swd-agents")])
        for rule in ("Bash(python3 C:/Users/RUNNER~1/x/swd-agents/scripts/check_run.py *)",
                     "Bash(sh C:/Users/RUNNER~1/x/swd-agents/scripts/swd-watch.sh *)",
                     "Read(//c/Users/RUNNER~1/x/swd-agents/**)"):
            self.assertIn(rule, rules)

    def test_an_installed_windows_plugin_is_read_through_its_version_free_folder(self):
        installed = PureWindowsPath(r"C:\Users\you\.claude\plugins\cache\swd-agents\swd\0.9.0")
        self.assertEqual(self.module().plugin_prefix(installed), "C:/Users/you/.claude/plugins/cache/swd-agents/swd/")
        self.assertIn("Read(//c/Users/you/.claude/plugins/cache/swd-agents/swd/**)", self.module().rules(self.project, [installed]))

    def test_the_outcome_for_a_fresh_project(self):
        # The plan's Outcome, criteria 1 and 4: 56 rules, then In place.
        args = ("--plugin-root", f"{INSTALLED}/0.11.0", "--command", "python3 -m unittest", "--command", "python3")
        settings = self.settings.resolve()
        shown = self.setup("--print", *args)
        self.assertEqual(shown.stdout.splitlines()[-1], f"Not in place: {settings} is missing 56 of the rules above and still holds"
                                                        " 0 rules an earlier version wrote; run /swd:setup.")
        listed = shown.stdout.splitlines()[1:47]
        self.assertEqual(listed[-4:], ["  Bash(python3 -m unittest)", "  Bash(python3 -m unittest *)", "  Bash(python3)", "  Bash(python3 *)"])
        self.assertEqual(self.setup(*args).stdout, f"setup: 56 rules added to {settings}\n")
        again = self.setup("--print", *args)
        self.assertEqual(again.stdout.splitlines()[-1],
                         f"In place: {settings} holds every rule above and none an earlier version wrote.")
        self.assertEqual(again.stdout.splitlines()[:-1], shown.stdout.splitlines()[:-1])

    # --- the typed and the resolved path ----------------------------------------------------------------------

    @unittest.skipIf(os.name == "nt", "symlinks need extra rights on Windows")
    def test_rules_are_written_for_the_path_as_typed_and_as_resolved(self):
        real = self.tmp / "real" / "plugin" / "scripts"
        real.mkdir(parents=True)
        shutil.copy(SCRIPT, real / "swd-setup.py")
        (self.tmp / "link").symlink_to(self.tmp / "real", target_is_directory=True)
        typed = (self.tmp / "link" / "plugin").as_posix()
        resolved = (self.tmp / "link" / "plugin").resolve().as_posix()
        self.assertNotEqual(typed, resolved)
        for args in ((), ("--plugin-root", typed)):
            with self.subTest(args=args):
                result = self.run_script(self.tmp / "link" / "plugin" / "scripts" / "swd-setup.py", "--print", *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                listed = [line.strip() for line in result.stdout.splitlines()]
                for folder in (typed, resolved):
                    self.assertIn(f"Bash(python3 {folder}/scripts/check_run.py *)", listed)
                    self.assertIn(f"Bash(sh {folder}/scripts/swd-python.sh check)", listed)
                    self.assertIn(f"Read(/{folder}/**)", listed)
                self.assertLess(listed.index(f"Bash(python3 {typed}/scripts/check_run.py *)"),
                                listed.index(f"Bash(python3 {resolved}/scripts/check_run.py *)"))   # the typed one first
        # A root that is already its resolved form, or that does not exist, gives each rule once.
        for root in (resolved, (self.tmp / "nowhere" / "plugin").as_posix()):
            with self.subTest(root=root):
                listed = [line.strip() for line in self.setup("--print", "--plugin-root", root).stdout.splitlines()]
                self.assertEqual(len([rule for rule in listed if rule.startswith("Bash(python3 ") and "check_run.py" in rule]), 1)
                self.assertIn(f"Bash(python3 {root}/scripts/check_run.py *)", listed)

    def test_rules_for_two_windows_spellings_name_both(self):
        rules = self.module().rules(self.project, [PureWindowsPath(r"c:\work\swd-agents"), PureWindowsPath(r"C:\work\swd-agents")])
        self.assertIn("Bash(python3 c:/work/swd-agents/scripts/check_run.py *)", rules)
        self.assertIn("Bash(python3 C:/work/swd-agents/scripts/check_run.py *)", rules)
        self.assertIn("Bash(sh c:/work/swd-agents/scripts/swd-watch.sh *)", rules)
        self.assertIn("Bash(sh C:/work/swd-agents/scripts/swd-watch.sh *)", rules)
        self.assertEqual(rules.count("Read(//c/work/swd-agents/**)"), 1)
        self.assertEqual(len(rules), 42 + 24 - 1)
        self.assertFalse([rule for rule in rules if "\\" in rule])

    # --- the matcher: criteria 2, 3 and 4 ---------------------------------------------------------------------

    ROOTS = {
        "installed": PurePosixPath(f"{INSTALLED}/0.11.0"),
        "installed on Windows": PureWindowsPath(r"C:\Users\you\.claude\plugins\cache\swd-agents\swd\0.11.0"),
        "checkout": PurePosixPath("/work/swd-agents"),
    }

    def playbook_commands(self, plugin, run):
        """Every command the build, follow and queue playbooks and the agents run with the plugin's scripts (Design 2)."""
        commands = [f"sh {plugin}/scripts/swd-python.sh check", f"sh {plugin}/scripts/swd-watch.sh {run}"]
        for python in PYTHONS:
            commands += [f"{python} {plugin}/scripts/{tail}" for tail in (
                f"swd-clean.py {run}",
                f"check_run.py --plan {run}", f"check_run.py --seal {run}", f"check_run.py --task T2 {run}",
                f"check_run.py --finish {run}", f"check_run.py {run}",
                f"swd-dashboard.py --watch --open {run}",
                f"swd-log.py {run} dispatch T1 generalist-engineer", f"swd-log.py {run} verdict T1 code-reviewer pass",
                f"swd-log.py {run} blocked the Fable judge could not be reached for the plan",
                f"swd-test.py {run} T2", f"swd-test.py {run} wave-1", f"swd-test.py {run} final",
                f"swd-findings.py {run}",
                f"swd-pr.py --wait 600 {run}", f"swd-pr.py --wait 300 {run}", f"swd-pr.py --mark-handled {run}")]
        return commands

    def test_every_command_a_run_needs_is_allowed_and_neither_asks_nor_is_denied(self):
        # Criterion 2, with the printed allow rules alone.
        for name, root in self.ROOTS.items():
            allow = self.module().rules(self.project, [root])
            plugin = root.as_posix()
            for run in (RUN, RUN + "-swd-setup-fix", RUN + "-swd-queue-fix", RUN + "-swd-mode-fix"):
                for command in self.playbook_commands(plugin, run):
                    with self.subTest(root=name, command=command):
                        self.assertTrue(allowed(command, allow))
                        self.assertFalse(stopped(command, ASK + DENY))

    def test_no_allow_rule_matches_the_setup_or_queue_script_the_hook_or_a_stretched_path(self):
        # Criterion 3.
        for name, root in self.ROOTS.items():
            allow = self.module().rules(self.project, [root])
            plugin = root.as_posix()
            tails = [f"scripts/swd-setup.py --print {PROJECT}", f"scripts/swd-setup.py --command * {PROJECT}",
                     f"scripts/swd-queue.py --dry-run {PROJECT}", f"scripts/swd-queue.py {PROJECT}",
                     "hooks/swd-mode.py", "hooks/__pycache__/swd-mode.cpython-310.pyc", "scripts/../hooks/swd-mode.py",
                     "scripts/check_run.py/../../hooks/swd-mode.py", "../../../../payload.py",
                     f"scripts/CHECK_RUN.py {RUN}", f"scripts/SWD-SETUP.py --print {PROJECT}", "hooks/SWD-MODE.py",
                     f"scripts/check_ru?.py {RUN}", f"scripts/swd-setu*.py --print {PROJECT}", "hooks/swd-mod?.py",
                     "scripts/*.py", f"scripts/'check_run'.py {RUN}", "hooks/swd-'mode'.py",
                     f"scripts/swd-'setup'.py --print {PROJECT}"]
            commands = [f"{python} {plugin}/{tail}" for python in PYTHONS for tail in tails]
            commands += [f'{python} "{plugin}/scripts/check_run.py" {RUN}' for python in PYTHONS]
            if name.startswith("installed"):   # another version folder's script needs setup run again
                newer = root.parent.as_posix() + "/0.11.1"
                commands += [f"{python} {newer}/scripts/check_run.py {RUN}" for python in PYTHONS]
                commands += [f"sh {newer}/scripts/swd-python.sh check", f"sh {newer}/scripts/swd-watch.sh {RUN}"]
            for command in commands:
                with self.subTest(root=name, command=command):
                    self.assertEqual([rule for rule in allow if matches(rule, command)], [])
                    self.assertFalse(allowed(command, allow))

    def test_each_sh_rule_matches_the_command_the_skills_run_and_nothing_stretched(self):
        # The skills run `sh <plugin>/scripts/...`, where <plugin> is ${CLAUDE_PLUGIN_ROOT}: for an installed
        # plugin that is the folder named for its version, and the two sh rules name that folder exactly.
        for name, root in self.ROOTS.items():
            rules = self.module().rules(self.project, [root])
            plugin = root.as_posix()
            with self.subTest(root=name, rules="sh rules have no wildcard in the path"):
                check, watch = [r for r in rules if r.startswith("Bash(sh ")]
                self.assertEqual(check, f"Bash(sh {plugin}/scripts/swd-python.sh check)")
                self.assertEqual(watch, f"Bash(sh {plugin}/scripts/swd-watch.sh *)")
                self.assertFalse(set("*?[") & set(check), check)
                self.assertEqual((watch.count("*"), watch[:-1].endswith(" *")), (1, True), watch)
            prefix = self.module().plugin_prefix(root)
            launcher = f"sh {plugin}/scripts/swd-python.sh"
            for command in (f"{launcher} run {plugin}/scripts/check_run.py",
                            f"{launcher} install --yes",
                            # stretched to end in a rule's tail (found by the 0.9.0 T2 security review)
                            f"{launcher} run payload.py scripts/swd-python.sh check",
                            f"{launcher} run payload.py #scripts/swd-python.sh check",
                            f"{launcher} install --yes scripts/swd-python.sh check",
                            f"{launcher} install --yes #scripts/swd-python.sh check",
                            f"{launcher} run payload.py scripts/swd-watch.sh y",
                            f"sh {prefix}../../../payload.sh scripts/swd-python.sh check",
                            f"sh {prefix}../../../elsewhere/scripts/swd-python.sh check",
                            f"sh {prefix}../../../payload.sh scripts/swd-watch.sh y"):
                with self.subTest(root=name, command=command):
                    self.assertEqual([rule for rule in rules if matches(rule, command)], [])

    def test_with_an_interpreter_rule_the_setup_and_queue_scripts_ask_and_the_hook_is_denied(self):
        # Criterion 4: an interpreter rule allows any Python command, so only the ask and deny rules stand in the way.
        for name, root in self.ROOTS.items():
            allow = self.module().rules(self.project, [root], ["python3"])
            self.assertIn("Bash(python3)", allow)
            self.assertIn("Bash(python3 *)", allow)
            plugin = root.as_posix()
            for command in (f"python3 {plugin}/scripts/swd-setup.py --command * {PROJECT}",
                            f"python3 {plugin}/scripts/swd-queue.py {PROJECT}",
                            f"HOME=/x python3 {plugin}/scripts/swd-queue.py {PROJECT}",
                            f"echo x | python3 {plugin}/scripts/swd-setup.py --print {PROJECT}",
                            f"unset SWD_UNATTENDED && python3 {plugin}/scripts/check_run.py --seal {RUN}"):
                with self.subTest(root=name, command=command):
                    self.assertTrue(stopped(command, self.module().ASK))
            for command in self.hook_commands(root):
                with self.subTest(root=name, hook=command):
                    self.assertTrue(stopped(command, self.module().DENY))

    def hook_commands(self, root):
        plugin = root.as_posix()
        prefix = self.module().plugin_prefix(root)
        return [f"python3 {plugin}/hooks/swd-mode.py",
                f"python {plugin}/hooks/swd-mode.py",
                f"py -3 {plugin}/hooks/swd-mode.py",
                f"python3 {prefix}scripts/../hooks/swd-mode.py",
                f"py -3 {root}\\hooks\\swd-mode.py".replace("/", "\\"),
                f"python {root}\\hooks\\swd-mode.py".replace("/", "\\"),
                f"echo '{{}}' | python3 {plugin}/hooks/swd-mode.py",
                *[f"{python} {plugin}/hooks/__pycache__/swd-mode.cpython-310.pyc" for python in PYTHONS]]

    def test_deny_rules_match_every_way_of_running_the_hook_and_no_allow_rule_does(self):
        self.assertEqual(self.module().DENY, DENY)
        self.assertEqual(self.module().ASK, ASK)
        for name, root in self.ROOTS.items():
            allow = self.module().rules(self.project, [root])
            plugin = root.as_posix()
            event = '{"hook_event_name":"UserPromptExpansion","command_name":"swd:conductor","command_args":"opus"}'
            piped = f"echo '{event}' | python3 {plugin}/hooks/swd-mode.py"
            for command in self.hook_commands(root):
                with self.subTest(root=name, hook=command):
                    self.assertTrue(stopped(command, DENY))
            # Under the per-script rules the hook part of the 0.9.0 forgery is allowed by no rule at all.
            self.assertTrue(allowed("echo x", allow))
            self.assertEqual([rule for rule in allow if matches(rule, f"python3 {plugin}/hooks/swd-mode.py")], [])
            self.assertFalse(allowed(piped, allow))

    def test_the_matcher_model_splits_commands_and_strips_assignments_only_for_ask_and_deny(self):
        self.assertTrue(allowed("ls a && ls b; ls c | ls d || ls e & ls f\nls g", ["Bash(ls *)"]))
        self.assertFalse(allowed("ls a && rm b", ["Bash(ls *)"]))
        self.assertFalse(allowed("X=1 ls a", ["Bash(ls *)"]))
        self.assertTrue(stopped("X=1 Y=2 rm a", ["Bash(rm *)"]))
        self.assertTrue(allowed("git", ["Bash(git *)"]))   # a trailing ` *` also matches the bare command

    # --- earlier versions' rules: criterion 6 ------------------------------------------------------------------

    OLD_10 = [f"Bash(python3 {INSTALLED}/*)", f"Bash(python {INSTALLED}/*)", f"Bash(py -3 {INSTALLED}/*)",
              f"Bash(sh {INSTALLED}/0.10.0/scripts/swd-python.sh check)", f"Bash(sh {INSTALLED}/0.10.0/scripts/swd-watch.sh *)"]

    def test_the_outcome_for_a_file_with_old_rules(self):
        # The plan's Outcome for <p2>, as written there.
        allow = ["Bash(make *)", *self.OLD_10, f"Bash({INSTALLED}/*)",
                 f"Bash(sh {INSTALLED}/0.9.0/scripts/swd-python.sh check)", "Bash(python3 *)",
                 f"Bash(python3 {INSTALLED}/0.10.0/scripts/check_run.py --plan *)", f"Read(/{INSTALLED}/**)", "Bash(git *)"]
        text = json.dumps({"permissions": {"allow": allow, "deny": ["Bash(rm *)"]}, "env": {"X": "1"}})
        self.write_settings(text)
        settings = self.settings.resolve()
        args = ("--plugin-root", f"{INSTALLED}/0.11.0")
        old = [*self.OLD_10, f"Bash({INSTALLED}/*)", f"Bash(sh {INSTALLED}/0.9.0/scripts/swd-python.sh check)"]
        shown = self.setup("--print", *args)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        lines = shown.stdout.splitlines()
        self.assertEqual(lines[-9:], [OLD_HEADING, *["  " + rule for rule in old],
                                      f"Not in place: {settings} is missing 50 of the rules above and still holds 7 rules"
                                      " an earlier version wrote; run /swd:setup."])
        self.assertEqual(self.settings.read_bytes(), text.encode("utf-8"))
        result = self.setup(*args)
        self.assertEqual(result.stdout, f"setup: 50 rules added to {settings}; 7 rules an earlier version of the plugin wrote removed\n")
        self.assertEqual(self.setup(*args).stdout, "setup: nothing to add\n")
        data = self.data()
        wanted = self.module().rules(self.project.resolve(), [PurePosixPath(f"{INSTALLED}/0.11.0")])
        kept = ["Bash(make *)", "Bash(python3 *)", f"Bash(python3 {INSTALLED}/0.10.0/scripts/check_run.py --plan *)",
                f"Read(/{INSTALLED}/**)", "Bash(git *)"]
        self.assertEqual(data["permissions"]["allow"], kept + [rule for rule in wanted if rule not in kept])
        self.assertEqual(data["permissions"]["allow"][5], f"Bash(python3 {INSTALLED}/0.11.0/scripts/check_run.py *)")
        self.assertEqual(len(data["permissions"]["allow"]), 45)
        self.assertEqual(data["permissions"]["deny"], ["Bash(rm *)", *DENY])
        self.assertEqual(data["permissions"]["ask"], ASK)
        self.assertEqual(data["env"], {"X": "1"})
        self.assertTrue(self.setup("--print", *args).stdout.splitlines()[-1].startswith("In place: "))

    def test_only_the_plugins_own_old_rules_are_removed(self):
        user = ["Bash(make *)", "Bash(python3 *)", f"Bash(python3 {INSTALLED}/0.10.0/scripts/check_run.py --plan *)",
                f"Bash(python3 {INSTALLED}/*) ", f"Bash(sh {INSTALLED}/0.9.0/../0.10.0/scripts/swd-python.sh check)",
                "Bash(python3 /other/plugin/*)", f"Bash(PYTHON3 {INSTALLED}/*)", f"Bash(sh {INSTALLED}/0.11.0/scripts/swd-watch.sh *)",
                5, None, {"a": 1}, [1]]
        allow = [*self.OLD_10, f"Read(/{INSTALLED}/**)", "Bash(git *)", "Bash(pwd)", user[0], f"Bash({INSTALLED}/*)",
                 user[1], f"Bash(sh {INSTALLED}/0.9.0/scripts/swd-python.sh check)", user[2],
                 f"Bash(sh {INSTALLED}/0.9.0/scripts/swd-watch.sh *)", *user[3:], self.OLD_10[0]]
        text = json.dumps({"permissions": {"allow": allow, "deny": [*DENY, "Bash(python3 /other/plugin/*)"],
                                           "ask": [f"Bash(python3 {INSTALLED}/*)"], "defaultMode": "default"},
                           "env": {"X": "1"}, "model": "opus"}, indent=4)
        self.write_settings(text)
        args = ("--plugin-root", f"{INSTALLED}/0.11.0")
        old = [*self.OLD_10, f"Bash({INSTALLED}/*)", f"Bash(sh {INSTALLED}/0.9.0/scripts/swd-python.sh check)",
               f"Bash(sh {INSTALLED}/0.9.0/scripts/swd-watch.sh *)", self.OLD_10[0]]
        shown = self.setup("--print", *args).stdout.splitlines()
        start = shown.index(OLD_HEADING)
        self.assertEqual(shown[start + 1:-1], ["  " + rule for rule in old])   # in file order, the duplicate twice
        self.assertIn("still holds 9 rules an earlier version wrote", shown[-1])
        self.assertEqual(self.settings.read_text(encoding="utf-8"), text)
        result = self.setup(*args)
        self.assertRegex(result.stdout, r"^setup: \d+ rules added to .*; 9 rules an earlier version of the plugin wrote removed\n$")
        data = self.data()
        self.assertEqual(data["permissions"]["allow"][:15], [f"Read(/{INSTALLED}/**)", "Bash(git *)", "Bash(pwd)", *user])
        self.assertFalse(set(old) & {rule for rule in data["permissions"]["allow"] if isinstance(rule, str)})
        self.assertEqual(data["permissions"]["deny"], [*DENY, "Bash(python3 /other/plugin/*)"])
        self.assertEqual(data["permissions"]["ask"], [f"Bash(python3 {INSTALLED}/*)", *ASK])
        self.assertEqual(list(data["permissions"]), ["allow", "deny", "ask", "defaultMode"])
        self.assertEqual((data["env"], data["model"], data["permissions"]["defaultMode"]), ({"X": "1"}, "opus", "default"))
        before = self.settings.read_bytes()
        self.assertEqual(self.setup(*args).stdout, "setup: nothing to add\n")
        self.assertEqual(self.settings.read_bytes(), before)

    def test_a_removal_with_nothing_to_add_still_reports_the_count(self):
        self.setup("--plugin-root", f"{INSTALLED}/0.11.0")
        data = self.data()
        data["permissions"]["allow"].append(self.OLD_10[1])
        self.write_settings(json.dumps(data))
        result = self.setup("--plugin-root", f"{INSTALLED}/0.11.0")
        self.assertEqual(result.stdout, f"setup: 0 rules added to {self.settings.resolve()};"
                                        " 1 rules an earlier version of the plugin wrote removed\n")
        self.assertNotIn(self.OLD_10[1], self.allow())

    def test_rules_for_an_older_version_are_replaced_after_an_update(self):
        old = f"{INSTALLED}/0.8.0"
        new = f"{INSTALLED}/0.9.0"
        self.assertEqual(self.setup("--plugin-root", old).returncode, 0)
        result = self.setup("--plugin-root", new)
        self.assertEqual(result.stdout, f"setup: 23 rules added to {self.settings.resolve()};"
                                        " 23 rules an earlier version of the plugin wrote removed\n")
        allow = self.allow()
        for rule in (f"Bash(sh {new}/scripts/swd-python.sh check)", f"Bash(sh {new}/scripts/swd-watch.sh *)",
                     f"Bash(py -3 {new}/scripts/swd-test.py *)"):
            with self.subTest(rule=rule):
                self.assertIn(rule, allow)
        self.assertFalse([rule for rule in allow if "/0.8.0/" in rule])

    def test_the_current_versions_rules_go_when_run_as_the_next(self):
        self.setup("--plugin-root", f"{INSTALLED}/0.11.0")
        result = self.setup("--plugin-root", f"{INSTALLED}/0.11.1")
        self.assertIn("; 23 rules an earlier version of the plugin wrote removed", result.stdout)
        self.assertFalse([rule for rule in self.allow() if "/0.11.0/" in rule])

    def test_a_checkout_recognises_the_broad_rules_and_keeps_its_own_sh_rules(self):
        checkout = "/work/swd-agents"
        broad = [f"Bash(python3 {checkout}/*)", f"Bash(python {checkout}/*)", f"Bash(py -3 {checkout}/*)", f"Bash({checkout}/*)"]
        own = [f"Bash(sh {checkout}/scripts/swd-python.sh check)", f"Bash(sh {checkout}/scripts/swd-watch.sh *)"]
        # A folder under the checkout that looks like a version folder is not one: these are the user's rules.
        versioned = [f"Bash(python3 {checkout}/0.10.0/scripts/check_run.py *)", f"Bash(sh {checkout}/0.10.0/scripts/swd-python.sh check)"]
        self.write_settings(json.dumps({"permissions": {"allow": [*broad, *own, *versioned]}}))
        result = self.setup("--plugin-root", checkout)
        self.assertIn("; 4 rules an earlier version of the plugin wrote removed", result.stdout)
        self.assertEqual(self.allow()[:4], [*own, *versioned])
        self.assertFalse(set(broad) & set(self.allow()))
        self.assertEqual(self.module().earlier_rules([*broad, *own], [PurePosixPath(checkout)]), broad)
        self.assertEqual(self.module().earlier_rules(versioned, [PurePosixPath(checkout)]), [])

    def test_a_windows_root_recognises_the_c_drive_forms(self):
        root = PureWindowsPath(r"C:\Users\you\.claude\plugins\cache\swd-agents\swd\0.11.0")
        prefix = "C:/Users/you/.claude/plugins/cache/swd-agents/swd/"
        old = [f"Bash(python3 {prefix}*)", f"Bash(python {prefix}*)", f"Bash(py -3 {prefix}*)", f"Bash({prefix}*)",
               f"Bash(sh {prefix}0.10.0/scripts/swd-python.sh check)", f"Bash(sh {prefix}0.10.0/scripts/swd-watch.sh *)",
               f"Bash(python {prefix}0.10.1-rc1/scripts/check_run.py *)"]
        kept = [f"Bash(sh {prefix}0.11.0/scripts/swd-python.sh check)", f"Bash(python3 {prefix.lower()}*)",
                f"Bash(python3 {prefix}0.11.0/scripts/check_run.py *)", f"Bash(python3 {prefix}x/scripts/check_run.py *)",
                f"Bash(python3 {prefix}0.10.0/scripts/swd-setup.py *)"]
        self.assertEqual(self.module().earlier_rules([*kept, *old], [root]), old)

    @unittest.skipIf(os.name == "nt", "symlinks need extra rights on Windows")
    def test_a_rule_that_is_wanted_is_never_counted_as_old(self):
        # A version folder reached through a link with another name: each spelling's per-script and sh rules have the
        # other's "earlier version" form. Setup does not remove a rule it is about to add, so it reaches In place.
        swd = self.tmp.resolve() / "plugins" / "cache" / "swd-agents" / "swd"   # resolved: the version folder is the only link
        (swd / "0.11.0-x").mkdir(parents=True)
        (swd / "0.11.0").symlink_to(swd / "0.11.0-x", target_is_directory=True)
        args = ("--plugin-root", (swd / "0.11.0").as_posix())
        self.assertNotIn(";", self.setup(*args).stdout)
        for version in ("0.11.0", "0.11.0-x"):
            self.assertIn(f"Bash(python3 {swd.as_posix()}/{version}/scripts/check_run.py *)", self.allow())
        self.assertEqual(self.setup(*args).stdout, "setup: nothing to add\n")
        self.assertTrue(self.setup("--print", *args).stdout.splitlines()[-1].startswith("In place: "))

    def test_a_file_that_needs_nothing_is_not_rewritten(self):
        # The user's own layout is kept: a rewrite would give json.dumps(indent=2) bytes, not these.
        self.setup()
        compact = json.dumps(self.data(), separators=(",", ":"))
        self.write_settings(compact)
        self.assertEqual(self.setup().stdout, "setup: nothing to add\n")
        self.assertEqual(self.settings.read_text(encoding="utf-8"), compact)

    # --- the status line and damaged files ---------------------------------------------------------------------

    def test_the_status_line_says_how_much_is_missing(self):
        settings = self.settings.resolve()
        args = ("--plugin-root", "/work/swd-agents")
        self.write_settings(json.dumps({"permissions": {"allow": ["Bash(git *)", "Bash(pwd)"], "deny": DENY[:1]}}))
        self.assertEqual(self.setup("--print", *args).stdout.splitlines()[-1],
                         f"Not in place: {settings} is missing 49 of the rules above and still holds 0 rules"
                         " an earlier version wrote; run /swd:setup.")
        self.setup(*args)
        last = self.setup("--print", *args).stdout.splitlines()
        self.assertEqual(last[-1], f"In place: {settings} holds every rule above and none an earlier version wrote.")
        self.assertNotIn(OLD_HEADING, last)

    DAMAGED = ["{ not json", "[]", "null", '{"permissions": []}', '{"permissions": null}', '{"permissions": {"allow": {}}}',
               '{"permissions": {"ask": "Bash(rm *)"}}', '{"permissions": {"deny": "Bash(rm *)"}}', b'{"x": "\xff"}',
               # Not strict JSON: Python reads these, and writing them back would change or drop what the file holds.
               '{"permissions": {"allow": []}, "x": NaN}', '{"permissions": {"allow": []}, "x": Infinity}',
               '{"permissions": {"allow": []}, "x": -Infinity}', '{"permissions": {"allow": []}, "x": 1e400}',
               '{"permissions": {"allow": ["Bash(a)"]}, "permissions": {"allow": ["Bash(b)"]}}',
               '{"permissions": {"allow": ["Bash(a)"], "allow": ["Bash(b)"]}}',
               '{"permissions": {"allow": []}, "env": {"X": "1", "X": "2"}}']

    def test_a_damaged_file_is_listed_as_not_valid_under_print(self):
        settings = self.settings.resolve()
        for text in self.DAMAGED:
            with self.subTest(settings=text):
                self.write_settings(text)
                before = self.settings.read_bytes()
                result = self.setup("--print", "--plugin-root", "/work/swd-agents")
                self.assertEqual(result.returncode, 0)
                lines = result.stdout.splitlines()
                self.assertIn("  Bash(git *)", lines)
                self.assertIn(DENY_HEADING, lines)
                self.assertNotIn(OLD_HEADING, lines)
                self.assertEqual(lines[-1], f"Not in place: {settings} is not valid JSON; fix or remove it, then run setup again.")
                self.assertEqual(self.settings.read_bytes(), before)

    def test_a_damaged_file_is_not_overwritten(self):
        for text in self.DAMAGED:
            with self.subTest(settings=text):
                self.write_settings(text)
                before = self.settings.read_bytes()
                result = self.setup()
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, f"{self.settings.resolve()} is not valid JSON; fix or remove it, then run setup again\n")
                self.assertEqual(self.settings.read_bytes(), before)

    def test_setup_never_writes_a_file_that_is_not_json(self):
        # Strict reading leaves nothing json.dumps would refuse, so a float that is not JSON goes into the data to write.
        setup = self.module()
        text = json.dumps({"permissions": {"allow": ["Bash(make *)"]}})
        for existing in (True, False):
            with self.subTest(existing=existing):
                shutil.rmtree(self.settings.parent, ignore_errors=True)
                if existing:
                    self.write_settings(text)
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(setup, "ASK", [*setup.ASK, float("inf")]), \
                        mock.patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)}), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = setup.main(["--plugin-root", "/work/swd-agents", str(self.project)])
                self.assertEqual((code, out.getvalue()), (1, ""))
                self.assertEqual(err.getvalue(), f"{self.settings.resolve()} is not valid JSON; fix or remove it, then run setup again\n")
                if existing:
                    self.assertEqual(self.settings.read_text(encoding="utf-8"), text)
                else:
                    self.assertFalse(self.settings.parent.exists())

    # --- the --command refusal: criterion 5 --------------------------------------------------------------------

    REFUSED = ["*", "", "  ", "*test", "py* -3", ":*", "npm test\n", "npm\x1btest"]
    SHOWN = {"*": "*", "": "", "  ": "  ", "*test": "*test", "py* -3": "py* -3", ":*": ":*", "npm test\n": "npm test\\n",
             "npm\x1btest": "npm\\x1btest"}

    def test_a_command_that_would_allow_everything_is_refused(self):
        for value in self.REFUSED:
            for show in ((), ("--print",)):
                with self.subTest(value=value, args=show):
                    result = self.setup(*show, "--command", "npm test", "--command", value)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr, f'setup: refused --command "{self.SHOWN[value]}": {REFUSAL}\n')
                    self.assertFalse(self.settings.parent.exists())

    def test_a_test_command_in_the_project_notes_that_would_allow_everything_is_refused(self):
        # A newline cannot reach the test command from the notes: the line ends there. \x1b stands in for it.
        notes = self.project / ".swd" / "project.md"
        notes.parent.mkdir()
        for value in self.REFUSED:
            if "\n" in value:
                continue
            for show in ((), ("--print",)):
                with self.subTest(value=value, args=show):
                    notes.write_text(f"## Commands\nTest command: `{value}`\n", encoding="utf-8")
                    result = self.setup(*show)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    shown = self.SHOWN[value].strip()   # the notes' value is read trimmed
                    self.assertEqual(result.stderr, f'setup: refused {NOTES} "{shown}": {REFUSAL}\n')
                    self.assertFalse(self.settings.parent.exists())

    def test_a_test_command_split_over_two_lines_writes_no_rule_with_a_newline(self):
        notes = self.project / ".swd" / "project.md"
        notes.parent.mkdir()
        notes.write_text("Test command: `npm test\nrm -rf /`\n", encoding="utf-8")
        self.setup()
        self.assertFalse([rule for rule in self.allow() if "\n" in rule or "rm -rf" in rule])

    ACCEPTED = ["npm test", "npx jest", "python3", "node", "go run .", "make test", "./gradlew test", "bash scripts/test.sh",
                "C:/tools/x.exe test", "g++ -o t t.cpp", "python3.12 -m pytest", "pytest tests/test_*.py",
                "./run_tests.sh", "golangci-lint run", "/opt/homebrew/opt/node@20/bin/npm test"]   # _ - @ in a first word

    def test_normal_commands_are_accepted(self):
        notes = self.project / ".swd" / "project.md"
        notes.parent.mkdir()
        for source in (NOTES, "--command"):
            for value in self.ACCEPTED:
                with self.subTest(value=value, source=source):
                    shutil.rmtree(self.settings.parent, ignore_errors=True)   # so an earlier run's rules cannot stand in
                    notes.write_text(f"Test command: `{value if source == NOTES else 'npm test'}`\n", encoding="utf-8")
                    result = self.setup(*(("--command", value) if source == "--command" else ()))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(f"Bash({value})", self.allow())
                    self.assertIn(f"Bash({value} *)", self.allow())

    def refused_from_both_sources(self, values, why):
        notes = self.project / ".swd" / "project.md"
        notes.parent.mkdir(exist_ok=True)
        for value in values:
            for source, args in (("--command", ("--command", value)), (NOTES, ())):
                notes.write_text(f"Test command: `{value if source == NOTES else 'npm test'}`\n", encoding="utf-8")
                for show in ((), ("--print",)):
                    with self.subTest(value=value, source=source, args=show):
                        result = self.setup(*show, *args)
                        self.assertEqual((result.returncode, result.stdout), (2, ""))
                        self.assertEqual(result.stderr, f'setup: refused {source} "{value}": {why}\n')
                        self.assertFalse(self.settings.parent.exists())

    # A first word with shell syntax in it does not name the program that runs: an assignment in any form, a quoted or
    # escaped name, a value made only of syntax, a back-slashed path, `~`, or a leading `-`.
    NOT_PLAIN = ["X+=1", "X=1", "NODE_ENV=test npm test", "X[0]=1", '"env"', "e''nv", "(x)", r"C:\tools\x.exe test",
                 "~/bin/t", "-c x", r"\sh", "$x", "a;b", "a|b", ">out", "{x}", "!x", "x\\",
                 r"C:\Windows\System32\bash.exe -c x"]

    def test_a_first_word_that_is_not_a_plain_name_or_path_is_refused(self):
        self.refused_from_both_sources(self.NOT_PLAIN, NOT_PLAIN)

    # These programs run the command they are given, which no ask or deny rule sees.
    RUNS_ANOTHER = ["sh", "bash -c x", "/usr/bin/env python3", "xargs", "sudo make test", "eval", "exec", "npx", "env",
                    "/bin/sh", "bash.exe", "zsh -lc x", "npx --yes x", "doas make",
                    "BASH.EXE", "Env", "C:/Windows/System32/Bash.exe -c x"]   # case ignored: these file systems find them

    def test_a_command_that_runs_another_is_refused(self):
        self.refused_from_both_sources(self.RUNS_ANOTHER, RUNNER)

    def test_a_command_that_names_the_plugins_own_folder_is_refused(self):
        # It would keep, or bring back, the broad rule Bash(python3 <prefix>*), which setup could then not remove.
        notes = self.project / ".swd" / "project.md"
        notes.parent.mkdir()
        broad = f"python3 {INSTALLED}/*"
        text = json.dumps({"permissions": {"allow": [f"Bash({broad})"]}})
        self.write_settings(text)
        checkout = "python3 /work/swd-agents/scripts/check_run.py"
        for source, value, root, prefix in ((NOTES, broad, f"{INSTALLED}/0.11.0", f"{INSTALLED}/"),
                                            ("--command", checkout, "/work/swd-agents", "/work/swd-agents/")):
            notes.write_text(f"Test command: `{broad if source == NOTES else 'npm test'}`\n", encoding="utf-8")
            args = ("--command", value) if source == "--command" else ()
            for show in ((), ("--print",)):
                with self.subTest(source=source, args=show):
                    result = self.setup(*show, "--plugin-root", root, *args)
                    self.assertEqual((result.returncode, result.stdout), (2, ""))
                    self.assertEqual(result.stderr, f'setup: refused {source} "{value}": it names the plugin\'s own folder,'
                                                    f" {prefix}, whose scripts setup allows one by one; give the project's own"
                                                    " command\n")
                    self.assertEqual(self.settings.read_text(encoding="utf-8"), text)
        # With an accepted test command in the notes, the broad rule goes.
        result = self.setup("--plugin-root", f"{INSTALLED}/0.11.0")
        self.assertIn("; 1 rules an earlier version of the plugin wrote removed", result.stdout)
        self.assertNotIn(f"Bash({broad})", self.allow())
        self.assertIn("Bash(npm test)", self.allow())

    @unittest.skipIf(os.name == "nt", "symlinks need extra rights on Windows")
    def test_a_command_that_names_the_plugins_folder_as_typed_or_as_resolved_is_refused(self):
        real = self.tmp / "real" / "plugin" / "scripts"
        real.mkdir(parents=True)
        shutil.copy(SCRIPT, real / "swd-setup.py")
        (self.tmp / "link").symlink_to(self.tmp / "real", target_is_directory=True)
        typed = (self.tmp / "link" / "plugin").as_posix()
        resolved = (self.tmp / "link" / "plugin").resolve().as_posix()
        self.assertNotEqual(typed, resolved)
        for folder in (resolved, typed):
            with self.subTest(folder=folder):
                value = f"python3 {folder}/x.py"
                result = self.run_script(self.tmp / "link" / "plugin" / "scripts" / "swd-setup.py", "--print", "--command", value)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertEqual(result.stderr, f'setup: refused --command "{value}": it names the plugin\'s own folder, {folder}/,'
                                                " whose scripts setup allows one by one; give the project's own command\n")

    def test_a_value_that_fails_two_tests_gets_the_first_tests_line_only(self):
        for value, why in (("X=* npm test", REFUSAL), ('"env"', NOT_PLAIN), ("~/bin/env", NOT_PLAIN),
                           (f"X=1 python3 {INSTALLED}/x.py", NOT_PLAIN), (f"env python3 {INSTALLED}/*", RUNNER)):
            with self.subTest(value=value):
                result = self.setup("--plugin-root", f"{INSTALLED}/0.11.0", "--command", value)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertEqual(result.stderr, f'setup: refused --command "{value}": {why}\n')

    # --- the plugin root check (contract C1, re-planned in T5) ------------------------------------------------

    # Every per-script, sh and Read rule is built from the plugin's path, so the path must be one no shell or interpreter
    # reads as an option, an expansion or code, and the Read rule must stay below the home folder: `--plugin-root=-c'...#'`
    # wrote `Bash(python3 -c'...#'/scripts/check_run.py *)`, which ran any code (T1 security review), and `/` wrote
    # `Read(//**)`. Each value goes in one argument, `--plugin-root=<value>`, so argparse takes a leading '-' as the value.
    REFUSED_ROOTS = ["-c'__import__(\"os\").system(__import__(\"sys\").argv.pop())#'", "x", "",   # relative ("" is ".")
                     "/work/a'b", '/work/a"b', "/work/a$(b", "/work/a#b",   # shell syntax
                     "/", "C:/", "/work",   # too high: Read(//**), Read(//c/**), a whole top folder; C:/ is relative off Windows
                     "/work/../etc/x",   # a .. folder
                     "*", "/work/a?b", "/work/[x]", "/work/a\tb", "/work/a\nb",   # T1's wildcards and control characters
                     # A space: the shell splits the rule there, so `<stdlib>/pdb.py -c` made Bash(python3 <stdlib>/pdb.py
                     # -c/scripts/check_run.py *), which runs any -c an agent adds as Python, with nothing planted (T5
                     # security review). The skills type the plugin path unquoted, so a spaced path never worked.
                     "/Users/John Doe/.claude/plugins/cache/swd-agents/swd/0.11.0", "/work/x -c y",
                     Path(os.__file__).parent.as_posix() + "/pdb.py -c",
                     # Not on Windows: there a back slash is a separator, and //work/x is a network path the command line must
                     # never be given, so no test looks up a host (test_plain_root_reads_the_text_alone covers it everywhere).
                     # Off Windows a drive letter starts a relative path: its rules would run a file under the working folder.
                     *([] if os.name == "nt" else ["/work/a\\b", "//work/x", "C:/work/swd-agents",
                                                   "C:/Users/RUNNER~1/x/swd-agents"])]

    def root_refusal(self, source, root):
        shown = "".join(c if c.isprintable() else c.encode("unicode_escape").decode() for c in Path(root).as_posix())
        return f'setup: refused {source} "{shown}": {ROOT_REFUSAL}\n'

    def test_a_plugin_root_that_is_not_an_absolute_plain_path_below_the_home_folder_is_refused(self):
        # The home folder itself, by either spelling (on macOS /var/... is /private/var/...; on Windows a short name is
        # resolved to the long one), and the folder above it: a Read rule there would cover every file in it.
        for root in [*self.REFUSED_ROOTS, str(self.home), str(self.home.parent), str(self.home.resolve())]:
            # With --command "*" too: the root is checked first, so its line is the only one.
            for args in ((), ("--print",), ("--command", "*"), ("--print", "--command", "*")):
                with self.subTest(root=root, args=args):
                    result = self.setup(*args, f"--plugin-root={root}")
                    self.assertEqual((result.returncode, result.stdout), (2, ""))
                    self.assertEqual(result.stderr, self.root_refusal("--plugin-root", root))
                    self.assertFalse(self.settings.parent.exists())
        text = json.dumps({"permissions": {"allow": ["Bash(make *)"]}})
        self.write_settings(text)
        result = self.setup("--plugin-root=-c'x#'")   # the plan's Outcome
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertEqual(result.stderr, f'setup: refused --plugin-root "-c\'x#\'": {ROOT_REFUSAL}\n')
        self.assertEqual(self.settings.read_text(encoding="utf-8"), text)

    @unittest.skipIf(os.name == "nt", "folder names with '*' and symlinks are not for Windows")
    def test_a_plugin_path_setup_finds_by_itself_is_refused_as_typed_or_as_resolved(self):
        # Checkouts cloned into folders named a[1], a'b and a b, run by their own path; and copies reached through symlinks
        # whose targets, re*al, a#b and a b, hold a refused character, so only the resolved path holds one.
        for name in ("a[1]", "a'b", "re*al", "a#b", "a b"):
            (self.tmp / name / "plugin" / "scripts").mkdir(parents=True)
            shutil.copy(SCRIPT, self.tmp / name / "plugin" / "scripts" / "swd-setup.py")
        cases = [(self.tmp / name / "plugin", "the plugin's path", os.path.abspath(self.tmp / name / "plugin"))
                 for name in ("a[1]", "a'b", "a b")]
        for name, link in (("re*al", "link"), ("a#b", "hash-link"), ("a b", "space-link")):
            (self.tmp / link).symlink_to(self.tmp / name, target_is_directory=True)
            cases.append((self.tmp / link / "plugin", "the plugin's resolved path", (self.tmp / link / "plugin").resolve()))
        for plugin, source, shown in cases:
            for args in ((), ("--print",)):
                with self.subTest(plugin=plugin.as_posix(), source=source, args=args):
                    result = self.run_script(plugin / "scripts" / "swd-setup.py", *args)
                    self.assertEqual((result.returncode, result.stdout), (2, ""))
                    self.assertEqual(result.stderr, self.root_refusal(source, shown))
                    self.assertFalse(self.settings.parent.exists())

    def test_a_plugin_root_that_passes_the_check_is_accepted_and_named_as_typed(self):
        # '~' is accepted, and so are letters outside ASCII, a plugin below the home folder, and a folder whose name only
        # starts like the home folder's. A drive letter only on Windows; elsewhere it is refused above, and plain_root's
        # test covers both. A space is refused above.
        home = self.home.as_posix()
        installed_home = self.home / ".claude" / "plugins" / "cache" / "swd-agents" / "swd" / "0.11.0"
        for root, read in ((f"{INSTALLED}/0.11.0", f"Read(/{INSTALLED}/**)"),
                           ("/work/swd-agents", "Read(//work/swd-agents/**)"),
                           *([("C:/work/swd-agents", "Read(//c/work/swd-agents/**)"),
                              ("C:/Users/RUNNER~1/x/swd-agents", "Read(//c/Users/RUNNER~1/x/swd-agents/**)")]
                             if os.name == "nt" else []),
                           ("/work/RUNNER~1/x/swd-agents", "Read(//work/RUNNER~1/x/swd-agents/**)"),
                           ("/Users/Jos\u00e9/x/swd-agents", "Read(//Users/Jos\u00e9/x/swd-agents/**)"),
                           (str(installed_home), f"Read({self.module().permission_path(installed_home.parent.as_posix() + '/')}**)"),
                           (str(self.home)[:-1], f"Read({self.module().permission_path(home[:-1] + '/')}**)")):
            with self.subTest(root=root):
                shutil.rmtree(self.settings.parent, ignore_errors=True)
                result = self.setup("--plugin-root", root)
                self.assertEqual((result.returncode, result.stderr), (0, ""))
                self.assertEqual(result.stdout, f"setup: 52 rules added to {self.settings.resolve()}\n")
                allow = self.allow()
                folder = Path(root).as_posix()
                for script in RUN_SCRIPTS:
                    for python in PYTHONS:
                        self.assertIn(f"Bash({python} {folder}/scripts/{script} *)", allow)
                self.assertIn(f"Bash(sh {folder}/scripts/swd-python.sh check)", allow)
                self.assertIn(f"Bash(sh {folder}/scripts/swd-watch.sh *)", allow)
                self.assertIn(read, allow)

    def test_plain_root_reads_the_text_alone(self):
        # On every platform, through plain_root(root, homes, windows): a drive letter starts an absolute path on Windows
        # only (elsewhere C:/work/x is relative); a // start is refused everywhere (on Windows a network path); the home
        # folder is refused by each spelling given, case ignored.
        homes = ("/var/you", "/private/var/you", "C:/Users/RUNNER~1", "C:/Users/runneradmin")
        for root, on_windows, elsewhere in ((PureWindowsPath("C:/work/swd-agents"), True, False),
                                            (PureWindowsPath("C:/Users/RUNNER~1/x/swd-agents"), True, False),
                                            (PureWindowsPath("//host/x"), False, False),
                                            # Relative to drive C's current folder: a drive needs its / after the colon.
                                            (PureWindowsPath("C:x/y/z"), False, False),
                                            (PurePosixPath("//work/x"), False, False),
                                            (PurePosixPath("/work/swd-agents"), True, True),
                                            (PurePosixPath("/private/var/you"), False, False),
                                            (PurePosixPath("/private/var"), False, False),
                                            (PureWindowsPath("C:/Users/RunnerAdmin"), False, False)):
            for windows, expected in ((True, on_windows), (False, elsewhere)):
                with self.subTest(root=repr(root), windows=windows):
                    self.assertIs(self.module().plain_root(root, homes, windows=windows), expected)

    def test_plain_root_reads_the_git_bash_drive_spelling_as_a_drive_on_windows(self):
        # Git Bash and Claude Code's matcher read /c/... as drive C ("C:\Users\alice becomes /c/Users/alice"), so with
        # windows the depth and home tests read it so: /c/Users is one folder below C:/, /c/Users/you is the home folder.
        # Elsewhere /c is an ordinary folder. A first folder of more than one letter is not a drive either way.
        homes = ("C:/Users/you",)
        for text, on_windows, elsewhere in (("/c/Users", False, True), ("/c/x", False, True), ("/c", False, False),
                                            ("/c/Users/you", False, True), ("/C/Users/you", False, True),
                                            ("/c/Users/you/plugins/swd-agents", True, True),
                                            ("/work/swd-agents", True, True)):
            for flavour in (PurePosixPath, PureWindowsPath):
                for windows, expected in ((True, on_windows), (False, elsewhere)):
                    with self.subTest(root=text, flavour=flavour.__name__, windows=windows):
                        self.assertIs(self.module().plain_root(flavour(text), homes, windows=windows), expected)

    def test_the_typed_root_is_tested_before_setup_opens_it(self):
        # On Windows exists() or resolve() on //host/x would reach that host, and can send it the user's credentials. The
        # fakes fail on the typed root without calling the real function, so no host is looked up even if this fails.
        setup = self.module()
        passed = []

        def guard(real):
            def fake(path, *args, **kwargs):
                if path == Path(root):
                    self.fail(f"{real.__name__}() called on the typed root {path}")
                passed.append(path)   # the project and the home folder
                return real(path, *args, **kwargs)
            return fake

        for root in ("//host/x", "-c'x#'"):
            with self.subTest(root=root):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(Path, "exists", guard(Path.exists)), \
                        mock.patch.object(Path, "resolve", guard(Path.resolve)), \
                        mock.patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)}), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = setup.main([f"--plugin-root={root}", str(self.project)])
                self.assertEqual((code, out.getvalue(), err.getvalue()), (2, "", self.root_refusal("--plugin-root", root)))
                self.assertFalse(self.settings.parent.exists())
        self.assertTrue(passed)   # the fakes were in place

    @unittest.skipIf(os.name == "nt", "symlinks need extra rights on Windows")
    def test_the_home_folder_is_refused_by_its_resolved_spelling(self):
        # HOME a symlink: the real folder, and the one above it, are the home folder and above it by the resolved spelling.
        real = self.tmp.resolve() / "real-home"
        real.mkdir()
        self.home = self.tmp / "home-link"
        self.home.symlink_to(real, target_is_directory=True)
        for root in (real.as_posix(), real.parent.as_posix()):
            for args in ((), ("--print",)):
                with self.subTest(root=root, args=args):
                    result = self.setup(*args, "--plugin-root", root)
                    self.assertEqual((result.returncode, result.stdout), (2, ""))
                    self.assertEqual(result.stderr, self.root_refusal("--plugin-root", root))
                    self.assertFalse(self.settings.parent.exists())


def matches(rule, command):
    """Whether a Bash(...) rule covers the whole of one simple command, `*` standing for any text, spaces included,
    and a trailing ` *` also matching the bare command. This approximates Claude Code's matcher; it is not the matcher."""
    match = re.fullmatch(r"Bash\((.*)\)", rule, re.S)
    if not match:
        return False
    body = match.group(1)
    pattern = ".*".join(re.escape(part) for part in body.split("*"))
    bare = body.endswith(" *") and command == body[:-2]
    return bare or re.fullmatch(pattern, command, re.S) is not None


def parts(command):
    """The subcommands of a command line, split at &&, ||, ;, |, & and newlines."""
    return [part.strip() for part in re.split(r"&&|\|\||;|\||&|\n", command) if part.strip()]


def allowed(command, allow):
    """Every subcommand matches an allow rule, as written: an allow rule does not match past an assignment."""
    return all(any(matches(rule, part) for rule in allow) for part in parts(command))


def stopped(command, rules):
    """Some subcommand, also with its leading NAME=value assignments stripped, matches an ask or deny rule."""
    return any(matches(rule, form) for part in parts(command)
               for form in (part, re.sub(r"^(?:\w+=\S*\s+)+", "", part)) for rule in rules)


class CodeGraphRulesTest(unittest.TestCase):
    """Contracts C2 and C3 of the code graph run. Never runs a real `codegraph`: the child's whole PATH is one temp
    folder, holding a stub that records a run, or nothing."""
    SUBCOMMANDS = ("init", "uninit", "index", "sync", "unlock", "install", "uninstall", "telemetry", "upgrade",
                   "daemon", "daemons", "serve", "ui", "web")   # copied from C2; every check loops over it
    ALLOW = "Bash(codegraph explore *)"
    BARE = "Bash(codegraph)"   # `codegraph` typed alone starts the installer
    ASK_RULES = [BARE] + [f"Bash(codegraph {sub} *)" for sub in SUBCOMMANDS]
    HEADING = ("Ask rules, so Claude Code asks you before a command builds, changes or removes a code graph index, "
               "or changes CodeGraph on this machine:")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        for name in ("home", "project", "bin", "cwd"):
            (self.tmp / name).mkdir()
        self.project, self.bin, self.cwd = self.tmp / "project", self.tmp / "bin", self.tmp / "cwd"
        self.settings = self.project / ".claude" / "settings.local.json"
        self.stub = self.bin / ("codegraph.exe" if os.name == "nt" else "codegraph")

    def put_stub(self):
        if os.name == "nt":
            self.stub.write_bytes(b"")
        else:
            self.stub.write_text('#!/bin/sh\necho ran >> "$0.ran"\nexit 3\n', encoding="utf-8")
            self.stub.chmod(0o755)

    def run_setup(self, *args, stub=True, index="dir"):
        """Run setup in a child whose PATH is only self.bin; first make .codegraph a "dir", a "file" or absent (None)
        and the stub present or not."""
        path = self.project / ".codegraph"
        if path.is_dir():
            path.rmdir()
        path.unlink(missing_ok=True)
        if index == "dir":
            path.mkdir()
        elif index == "file":
            path.write_text("not a directory", encoding="utf-8")
        if stub:
            self.put_stub()
        elif self.stub.exists():
            self.stub.unlink()
        env = {**os.environ, "PATH": str(self.bin), "HOME": str(self.tmp / "home"), "USERPROFILE": str(self.tmp / "home")}
        result = subprocess.run([sys.executable, str(SCRIPT), *args, str(self.project)], capture_output=True, text=True,
                                encoding="utf-8", env=env, cwd=self.cwd)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.bin / "codegraph.ran").exists())   # nothing ever runs the stub
        return result

    def written(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))["permissions"]

    def written_rules(self):
        """Run setup with a code graph and return the allow and ask rules it wrote, so the matching tests check the
        script's rules, not this class's copy of them."""
        self.assertEqual(self.run_setup().returncode, 0)
        permissions = self.written()
        return permissions["allow"], permissions["ask"]

    def test_print_lists_the_allow_rule_and_every_ask_rule_before_the_deny_block(self):
        result = self.run_setup("--print")
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.splitlines()
        self.assertEqual(lines.count("  " + self.ALLOW), 1)
        self.assertLess(lines.index("  " + ASK[-1]), lines.index(self.HEADING))
        heading = lines.index(self.HEADING)
        end = heading + 1 + len(self.ASK_RULES)
        self.assertEqual(lines[heading + 1:end], ["  " + rule for rule in self.ASK_RULES])
        self.assertEqual(lines[end], DENY_HEADING)
        self.assertIn("is missing", result.stdout)

    def test_the_written_file_holds_them_after_the_existing_rules(self):
        result = self.run_setup()
        self.assertEqual(result.returncode, 0)
        permissions = self.written()
        self.assertEqual(permissions["allow"].count(self.ALLOW), 1)
        self.assertEqual(permissions["allow"][-1], self.ALLOW)
        self.assertEqual(permissions["ask"], ASK + self.ASK_RULES)
        self.assertEqual(permissions["ask"][len(ASK)], self.BARE)
        self.assertEqual(permissions["deny"], DENY)
        total = len(permissions["allow"]) + len(permissions["ask"]) + len(permissions["deny"])
        self.assertIn(f"setup: {total} rules added", result.stdout)

    def test_a_command_that_already_allows_explore_does_not_add_the_rule_twice(self):
        shown = self.run_setup("--print", "--command", "codegraph explore")
        self.assertEqual(shown.stdout.splitlines().count("  " + self.ALLOW), 1)
        result = self.run_setup("--command", "codegraph explore")
        self.assertEqual(result.returncode, 0)
        permissions = self.written()
        self.assertEqual(permissions["allow"].count(self.ALLOW), 1)
        self.assertEqual(permissions["ask"], ASK + self.ASK_RULES)
        total = len(permissions["allow"]) + len(permissions["ask"]) + len(permissions["deny"])   # the file was empty
        self.assertIn(f"setup: {total} rules added", result.stdout)
        self.assertIn(f"is missing {total} of the rules above", shown.stdout)

    def test_print_after_setup_says_in_place_and_a_second_run_changes_nothing(self):
        self.run_setup()
        before = self.settings.read_bytes()
        self.assertIn("In place:", self.run_setup("--print").stdout)
        second = self.run_setup()
        self.assertEqual((second.returncode, second.stdout), (0, "setup: nothing to add\n"))
        self.assertEqual(self.settings.read_bytes(), before)

    def test_a_project_set_up_before_the_index_is_missing_only_the_code_graph_rules(self):
        self.run_setup(index=None)
        new = 1 + len(self.ASK_RULES)
        result = self.run_setup("--print")
        self.assertIn(f"is missing {new} of the rules above", result.stdout)
        self.assertEqual(self.run_setup().stdout.split()[1:3], [str(new), "rules"])
        self.assertIn(self.ALLOW, self.written()["allow"])

    def test_each_ask_rule_covers_the_bare_subcommand(self):
        allow, ask = self.written_rules()
        for sub in self.SUBCOMMANDS:
            with self.subTest(sub=sub):
                self.assertTrue(stopped(f"codegraph {sub}", ask))
                self.assertFalse(allowed(f"codegraph {sub}", allow))

    def test_each_subcommand_asks_with_arguments_and_after_an_assignment_and_is_not_allowed(self):
        allow, ask = self.written_rules()
        for sub in self.SUBCOMMANDS:
            for command in (f"codegraph {sub}", f"codegraph {sub} --force", f"codegraph {sub} --mcp",
                            f"X=1 codegraph {sub}"):
                with self.subTest(command=command):
                    self.assertTrue(stopped(command, ask))
                    self.assertFalse(allowed(command, allow))
        for command in ("codegraph status", "codegraph explorer"):   # not allowed either
            with self.subTest(command=command):
                self.assertFalse(allowed(command, allow))

    def test_bare_codegraph_is_stopped_and_not_allowed(self):
        allow, ask = self.written_rules()
        self.assertIn(self.BARE, ask)
        self.assertTrue(stopped("codegraph", ask))
        self.assertFalse(allowed("codegraph", allow))
        for command in ("codegraph explore", 'codegraph explore -p /x "q"'):   # Bash(codegraph) matches neither
            with self.subTest(command=command):
                self.assertTrue(allowed(command, allow))
                self.assertFalse(stopped(command, ask))

    def test_the_docstring_states_no_count_and_no_nothing_else_for_codegraph(self):
        doc = module().__doc__
        start = doc.index("When the project has a code graph")
        paragraph = " ".join(doc[start:doc.index("No rule lets an agent build, sync or remove an index.", start)].split())
        self.assertNotIn("nothing else", paragraph)
        self.assertIsNone(re.search(r"\d|\b(?:ten|eleven|twelve|thirteen|fourteen|fifteen)\b", paragraph))
        self.assertIn("does not build or sync it", paragraph)
        self.assertIn("`codegraph` typed alone, which starts the installer", paragraph)

    def test_without_a_code_graph_the_output_and_the_file_are_those_of_a_project_with_neither(self):
        def outcome(**case):
            self.settings.unlink(missing_ok=True)
            shown = self.run_setup("--print", **case).stdout
            ran = self.run_setup(**case).stdout
            return shown, ran, self.settings.read_text(encoding="utf-8")

        baseline = outcome(stub=False, index=None)
        # Not a bare "codegraph": the plugin's own folder here may be named for it.
        self.assertNotIn("Bash(codegraph", "".join(baseline))
        self.assertNotIn("code graph", "".join(baseline))
        for case in ({"stub": True, "index": None}, {"stub": False, "index": "dir"}, {"stub": True, "index": "file"}):
            with self.subTest(case=case):
                self.assertEqual(outcome(**case), baseline)


if __name__ == "__main__":
    unittest.main()
