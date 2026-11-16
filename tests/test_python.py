"""Tests for scripts/swd-python.sh, the launcher every hook goes through and the skills' Python step.

Every Python, installer and system command the launcher can see is a stub in one folder that is
the whole of PATH, so no test can reach a real Python by name, install anything or use the network.
The launcher itself is started with the real `sh`, found before PATH is replaced.
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "scripts" / "swd-python.sh"
WINDOWS = os.name == "nt"
SH = shutil.which("sh")
CYGPATH = shutil.which("cygpath") if WINDOWS else None
VERSION = "%d.%d.%d" % sys.version_info[:3]

NOTICE = ("swd: the swd plugin needs Python 3.9 or later and found none (tried python3, python and py -3). "
          "Run /swd:setup: it can install Python on Windows, or tell you the command for this system.\n")
MISSING = "python: missing (none of python3, python or py -3 is Python 3.9 or later)"
WINGET_ARGS = ["install", "--exact", "--id", "Python.Python.3.13", "--source", "winget", "--scope", "user",
               "--silent", "--accept-package-agreements", "--accept-source-agreements"]
WINGET_LINE = "winget " + " ".join(WINGET_ARGS)
BY_HAND_WINDOWS = "by hand, from https://www.python.org/downloads/windows/"
NOT_HERE = ("swd does not run installers on macOS or Linux: run the command above yourself, "
            "then run /swd:setup again.")
INSTALLERS = ("winget", "brew", "apt-get", "dnf", "sudo")

WINDOWS_UNAME = "MINGW64_NT-10.0-20348"


def posix(path):
    """A path `sh` can run on every system: forward slashes, as Git Bash accepts `C:/...`."""
    return str(path).replace("\\", "/")


def unix(path):
    """What `cygpath -u` gives for `path`: the real one on Windows, the stub's echo elsewhere."""
    if WINDOWS:
        return subprocess.run([CYGPATH, "-u", str(path)], capture_output=True, check=True,
                              timeout=60).stdout.decode("utf-8").strip()
    return str(path)


def single_quoted(text):
    return "'" + text.replace("'", "'\\''") + "'"


class Stubs:
    """One folder of stub commands, which is the whole PATH the launcher sees."""

    def __init__(self, base):
        self.base = Path(base)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.logs = self.base / "logs"
        self.logs.mkdir()
        if SH is None:
            raise AssertionError("no sh on PATH: the plugin's hooks need it")
        self.exec_real("sh", SH)
        if WINDOWS:
            if CYGPATH is None:
                raise AssertionError("no cygpath on PATH: Git for Windows provides it")
            self.exec_real("cygpath", CYGPATH)
        else:  # stands in for Git for Windows' cygpath: prints the path it is given
            self.write("cygpath", '[ "$1" = -u ] && shift\nprintf "%s\\n" "$1"')

    def write(self, name, body, folder=None):
        path = (folder or self.bin) / name
        path.write_bytes(("#!/bin/sh\n" + body + "\n").encode("utf-8"))  # LF, also on Windows
        path.chmod(0o755)
        return path

    def exec_real(self, name, program, folder=None):
        return self.write(name, f'exec {shlex.quote(posix(program))} "$@"', folder)

    def python(self, name="python3", folder=None):
        """A real Python 3.9 or later, by this name."""
        if name == "py":  # the Windows launcher: works only as `py -3`
            return self.write(name, f'[ "$1" = -3 ] || exit 9\nshift\nexec {shlex.quote(posix(sys.executable))} "$@"',
                              folder)
        return self.exec_real(name, sys.executable, folder)

    def store(self, name="python"):
        """The Microsoft Store stub Windows puts on PATH as python and python3."""
        return self.write(name, "echo 'Python was not found; run without arguments to install from the "
                                "Microsoft Store' >&2\nexit 49")

    def old_python(self, name="python3"):
        return self.write(name, 'echo 3.8.18\nexit 1')

    def uname(self, answer):
        return self.write("uname", f"echo {shlex.quote(answer)}")

    def installer(self, name, body="exit 0"):
        """A stub that logs each call, one line of [arg] per call, then runs `body`."""
        log = posix(self.logs / name)
        return self.write(name, f'printf "[%s]" "$@" >> {shlex.quote(log)}\n'
                                f'printf "\\n" >> {shlex.quote(log)}\n{body}')

    def calls(self, name):
        log = self.logs / name
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def env(self, **extra):
        env = {"HOME": str(self.base), "USERPROFILE": str(self.base), "PATH": str(self.bin)}
        if "SYSTEMROOT" in os.environ:
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        env.update(extra)
        return env


class LauncherTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.stubs = Stubs(self.tmp)

    def launch(self, *args, stdin=b"", **extra):
        result = subprocess.run([SH, posix(LAUNCHER), *args], input=stdin, capture_output=True,
                                env=self.stubs.env(**extra), cwd=self.tmp, timeout=60)
        return (result.returncode, result.stdout.decode("utf-8").replace("\r\n", "\n"),
                result.stderr.decode("utf-8").replace("\r\n", "\n"))

    def script(self, source):
        path = self.tmp / "script.py"
        path.write_bytes(source.encode("utf-8"))
        return posix(path)

    def no_installer_ran(self):
        for name in INSTALLERS:
            self.assertEqual(self.stubs.calls(name), [], name)

    def every_installer(self):
        for name in INSTALLERS:
            self.stubs.installer(name)


ECHO = """import json, sys
sys.stdout.write(json.dumps({"args": sys.argv[1:], "stdin": sys.stdin.buffer.read().decode("utf-8")}))
"""


class RunTest(LauncherTest):
    def run_echo(self, *args, stdin=b""):
        code, out, err = self.launch("run", self.script(ECHO), *args, stdin=stdin)
        self.assertEqual((code, err), (0, ""), out)
        return json.loads(out)

    def test_run_uses_python_when_there_is_no_python3(self):
        self.stubs.python("python")
        self.assertEqual(self.run_echo("one"), {"args": ["one"], "stdin": ""})

    def test_run_skips_the_store_stub(self):
        self.stubs.store("python3")
        self.stubs.python("python")
        self.assertEqual(self.run_echo("one"), {"args": ["one"], "stdin": ""})  # and nothing on stderr

    def test_run_uses_the_py_launcher_with_3(self):
        self.stubs.store("python3")
        self.stubs.store("python")
        self.stubs.python("py")  # refuses to run without -3
        self.assertEqual(self.run_echo("one"), {"args": ["one"], "stdin": ""})

    def test_run_passes_stdin_and_arguments_through(self):
        self.stubs.python("python3")
        args = ["a b", "", "$HOME", "it's", "*", "--yes"]
        stdin = json.dumps({"prompt": "caf\u00e9 \u201dquoted\u201d"}, ensure_ascii=False).encode("utf-8")
        if WINDOWS:
            # Python sends one command line that Git's sh splits again: ' opens a quote, a bare * is globbed.
            args.remove("it's")
            self.assertFalse([arg for arg in args if '"' in arg or "\\" in arg])  # each fits in double quotes
            command = (subprocess.list2cmdline([SH, posix(LAUNCHER), "run", self.script(ECHO)])
                       + "".join(f' "{arg}"' for arg in args))
            result = subprocess.run(command, input=stdin, capture_output=True, env=self.stubs.env(), cwd=self.tmp,
                                    timeout=60)
            out, err = (result.stdout.decode("utf-8"), result.stderr.decode("utf-8"))
            self.assertEqual((result.returncode, err), (0, ""), out)
            self.assertEqual(json.loads(out), {"args": args, "stdin": stdin.decode("utf-8")})
        else:
            self.assertEqual(self.run_echo(*args, stdin=stdin), {"args": args, "stdin": stdin.decode("utf-8")})
        failing = self.script('import sys\nprint("out")\nprint("err", file=sys.stderr)\nsys.exit(7)\n')
        self.assertEqual(self.launch("run", failing), (7, "out\n", "err\n"))

    def test_a_failing_probe_leaves_the_input_to_the_script(self):
        # A python3 that reads all of its stdin and then fails: the probe must not take the hook's input.
        self.stubs.write("python3", "while read -r line; do :; done\nexit 49")
        self.stubs.python("python")
        stdin = ("\n".join(json.dumps({"prompt": "café ”%d”" % n}, ensure_ascii=False)
                           for n in range(200))).encode("utf-8")  # no newline at the end
        self.assertEqual(self.run_echo("one", stdin=stdin), {"args": ["one"], "stdin": stdin.decode("utf-8")})

    def test_a_python_in_the_project_folder_never_runs(self):
        # A hook runs in the user's project, so an empty or relative PATH entry would reach a planted python3.
        marker = self.tmp / "planted ran"
        planted = f": > {shlex.quote(posix(marker))}\nexec {shlex.quote(posix(sys.executable))} \"$@\""
        self.stubs.write("python3", planted, folder=self.tmp)
        (self.tmp / "rel").mkdir()
        self.stubs.write("python3", planted, folder=self.tmp / "rel")
        self.stubs.python("python")
        stubs, sep = str(self.stubs.bin), os.pathsep
        for path in (sep + stubs, stubs + sep, stubs + sep + sep + stubs, "." + sep + stubs, "rel" + sep + stubs,
                     stubs + sep + "."):
            with self.subTest(PATH=path):
                marker.unlink(missing_ok=True)
                code, out, err = self.launch("run", self.script(ECHO), "one", PATH=path)
                self.assertEqual((code, json.loads(out), err), (0, {"args": ["one"], "stdin": ""}, ""))
                self.assertFalse(marker.exists())
        for path in ("", sep, ".", "rel", "." + sep + "rel"):  # nothing absolute left to search
            with self.subTest(PATH=path):
                marker.unlink(missing_ok=True)
                self.assertEqual(self.launch("run", self.script(ECHO), PATH=path), (0, NOTICE, ""))
                self.assertFalse(marker.exists())

    def test_nothing_the_launcher_starts_may_install_a_runtime(self):
        # On Windows, py, python and python3 from the Python install manager install a runtime when there
        # is none, with no prompt, and the classic py launcher does when PYLAUNCHER_* is set.
        log = self.tmp / "environment.log"
        names = ("PYTHON_MANAGER_AUTOMATIC_INSTALL", "PYLAUNCHER_ALLOW_INSTALL", "PYLAUNCHER_ALWAYS_INSTALL")
        seen = " ".join(f'"${{{name}-unset}}"' for name in names)  # unset is not the same as set to ""

        def recording(name):
            return f'printf "{name} [%s][%s][%s]\\n" {seen} >> {shlex.quote(posix(log))}\n'

        self.stubs.write("python3", recording("python3") + "exit 49")
        self.stubs.write("python", recording("python") + "exit 49")
        self.stubs.write("py", recording("py") + f'[ "$1" = -3 ] || exit 9\nshift\n'
                                                 f'exec {shlex.quote(posix(sys.executable))} "$@"')
        script = self.script(f"import json, os\nprint(json.dumps([os.environ.get(n) for n in {names!r}]))\n")
        safe = "[false][unset][unset]"
        callers = ({"PYTHON_MANAGER_AUTOMATIC_INSTALL": "true", "PYLAUNCHER_ALLOW_INSTALL": "1",
                    "PYLAUNCHER_ALWAYS_INSTALL": "1"},
                   {"PYTHON_MANAGER_AUTOMATIC_INSTALL": "", "PYLAUNCHER_ALLOW_INSTALL": "",
                    "PYLAUNCHER_ALWAYS_INSTALL": ""},
                   {})
        for caller in callers:
            with self.subTest(caller=caller):
                log.unlink(missing_ok=True)
                self.assertEqual(self.launch("run", script, **caller), (0, '["false", null, null]\n', ""))
                self.assertEqual(log.read_text(encoding="utf-8").splitlines(),  # three probes, then the run
                                 [f"python3 {safe}", f"python {safe}", f"py {safe}", f"py {safe}"])
                log.unlink()
                self.assertEqual(self.launch("check", **caller), (0, f"python: py -3 (Python {VERSION})\n", ""))
                self.assertEqual(log.read_text(encoding="utf-8").splitlines(),
                                 [f"python3 {safe}", f"python {safe}", f"py {safe}"])

    def test_run_without_python_prints_the_notice_and_exits_0(self):
        cases = {
            "nothing": lambda: None,
            "store stubs": lambda: (self.stubs.store("python3"), self.stubs.store("python")),
            "old python": lambda: (self.stubs.old_python("python3"), self.stubs.old_python("python")),
            "py without 3": lambda: self.stubs.old_python("py"),
        }
        for name, make in cases.items():
            with self.subTest(case=name):
                for stub in ("python3", "python", "py"):
                    (self.stubs.bin / stub).unlink(missing_ok=True)
                make()
                marker = self.tmp / "ran"
                script = self.script(f"open({str(marker)!r}, 'w').close()\n")
                result = self.launch("run", script, stdin=b'{"hook_event_name": "UserPromptSubmit"}')
                self.assertEqual(result, (0, NOTICE, ""))
                self.assertFalse(marker.exists())


class CheckTest(LauncherTest):
    def test_check_reports_the_command_and_version(self):
        for name, shown in (("python3", "python3"), ("python", "python"), ("py", "py -3")):
            with self.subTest(python=name):
                for stub in ("python3", "python", "py"):
                    (self.stubs.bin / stub).unlink(missing_ok=True)
                self.stubs.python(name)
                self.assertEqual(self.launch("check"), (0, f"python: {shown} (Python {VERSION})\n", ""))

    def test_check_without_python_names_the_installer_for_each_system(self):
        rows = [
            (WINDOWS_UNAME, ["winget"], WINGET_LINE, "yes"),
            ("MSYS_NT-10.0", ["winget"], WINGET_LINE, "yes"),
            ("CYGWIN_NT-10.0", ["winget"], WINGET_LINE, "yes"),
            (WINDOWS_UNAME, [], BY_HAND_WINDOWS, "no"),
            ("Darwin", ["brew", "winget"], "brew install python", "no"),
            ("Darwin", [], "xcode-select --install", "no"),
            ("Linux", ["apt-get", "dnf"], "sudo apt-get install python3", "no"),
            ("Linux", ["dnf"], "sudo dnf install python3", "no"),
            ("Linux", [], "by hand, from https://www.python.org/downloads/", "no"),
            ("FreeBSD", ["winget"], "by hand, from https://www.python.org/downloads/", "no"),
            ("", [], "by hand, from https://www.python.org/downloads/", "no"),
            (None, [], "by hand, from https://www.python.org/downloads/", "no"),  # no uname at all
        ]
        self.stubs.store("python3")
        self.stubs.store("python")
        for system, tools, how, can in rows:
            with self.subTest(system=system, tools=tools):
                for name in INSTALLERS + ("uname",):
                    (self.stubs.bin / name).unlink(missing_ok=True)
                if system is not None:
                    self.stubs.uname(system)
                for tool in tools:
                    self.stubs.installer(tool)
                self.assertEqual(self.launch("check"),
                                 (3, f"{MISSING}\ninstall: {how}\nswd can install it: {can}\n", ""))
                for name in INSTALLERS:
                    self.assertEqual(self.stubs.calls(name), [], name)

    def test_fallback_finds_python_in_the_per_user_install_folder(self):
        # After winget, an open terminal still has the old PATH: the Store stubs, no new Python.
        self.stubs.store("python3")
        self.stubs.store("python")
        local = self.tmp / "O'Brien App" / "Local"  # a space and a quote, as a Windows user name can have
        base = unix(local) + "/Programs/Python/"
        for folder, name, shown in (("Python313", "python", single_quoted(base + "Python313/python")),
                                    ("Launcher", "py", single_quoted(base + "Launcher/py") + " -3")):
            with self.subTest(folder=folder):
                shutil.rmtree(local, ignore_errors=True)
                target = local / "Programs" / "Python" / folder
                target.mkdir(parents=True)
                self.stubs.python(name, folder=target)
                self.assertEqual(self.launch("check", LOCALAPPDATA=str(local)),
                                 (0, f"python: {shown} (Python {VERSION})\n", ""))
                ran = self.launch("run", self.script(ECHO), "x", LOCALAPPDATA=str(local))
                self.assertEqual((ran[0], json.loads(ran[1]), ran[2]), (0, {"args": ["x"], "stdin": ""}, ""))
                # The shown command is one that works when pasted into sh.
                pasted = subprocess.run([SH, "-c", shown + ' -c "print(42)"'],
                                        capture_output=True, env=self.stubs.env(), timeout=60)
                self.assertEqual(pasted.stdout.decode("utf-8").strip(), "42")
        with self.subTest(without="LOCALAPPDATA"):
            self.assertEqual(self.launch("check")[0], 3)

    @unittest.skipIf(WINDOWS, "the stub folder needs cygpath on Windows, where Git for Windows always has it")
    def test_the_fallback_needs_cygpath(self):
        (self.stubs.bin / "cygpath").unlink()
        target = self.tmp / "Local" / "Programs" / "Python" / "Python313"
        target.mkdir(parents=True)
        self.stubs.python("python", folder=target)
        self.assertEqual(self.launch("check", LOCALAPPDATA=str(self.tmp / "Local"))[0], 3)

    def test_the_fallback_ignores_a_relative_local_app_data(self):
        # A relative LOCALAPPDATA would be searched from the hook's folder, the user's project.
        self.stubs.store("python3")
        self.stubs.store("python")
        marker = self.tmp / "planted ran"
        target = self.tmp / "Local" / "Programs" / "Python" / "Python313"
        target.mkdir(parents=True)
        self.stubs.write("python", f": > {shlex.quote(posix(marker))}\n"
                                   f"exec {shlex.quote(posix(sys.executable))} \"$@\"", folder=target)
        missing = f"{MISSING}\ninstall: by hand, from https://www.python.org/downloads/\nswd can install it: no\n"
        for local in ("Local", "./Local", ""):
            with self.subTest(LOCALAPPDATA=local):
                marker.unlink(missing_ok=True)
                self.assertEqual(self.launch("run", self.script(ECHO), LOCALAPPDATA=local), (0, NOTICE, ""))
                self.assertEqual(self.launch("check", LOCALAPPDATA=local), (3, missing, ""))
                self.assertFalse(marker.exists())


class InstallTest(LauncherTest):
    def setUp(self):
        super().setUp()
        self.every_installer()
        self.stubs.store("python3")
        self.stubs.store("python")
        self.local = self.tmp / "Local"
        self.installed = self.tmp / "installed"  # the winget stub creates it to stand for a finished install
        target = self.local / "Programs" / "Python" / "Python313"
        target.mkdir(parents=True)
        self.stubs.write("python", f'[ -f {shlex.quote(posix(self.installed))} ] || exit 9009\n'
                                   f'exec {shlex.quote(posix(sys.executable))} "$@"', folder=target)
        self.shown = single_quoted(unix(self.local) + "/Programs/Python/Python313/python")

    def install(self, *args, system=WINDOWS_UNAME):
        self.stubs.uname(system)
        return self.launch("install", *args, LOCALAPPDATA=str(self.local))

    def test_install_needs_yes_and_runs_nothing_without_it(self):
        for args in ([], ["--yes", "--yes"], ["--yes", "x"], ["yes"], ["--YES"], ["-y"], [""], ["x", "--yes"]):
            with self.subTest(args=args):
                self.assertEqual(self.install(*args), (2, "", "usage: sh swd-python.sh install --yes\n"))
        self.no_installer_ran()
        self.assertEqual(self.launch("check", LOCALAPPDATA=str(self.local))[0], 3)  # nothing was installed

    def test_install_on_macos_and_linux_runs_no_installer(self):
        for system, how in (("Darwin", "brew install python"), ("Linux", "sudo apt-get install python3")):
            with self.subTest(system=system):
                self.assertEqual(self.install("--yes", system=system),
                                 (4, f"{MISSING}\ninstall: {how}\n{NOT_HERE}\n", ""))
        self.no_installer_ran()

    def test_install_on_windows_calls_winget_once_and_checks_python_runs(self):
        self.stubs.installer("winget", f": > {shlex.quote(posix(self.installed))}")
        code, out, err = self.install("--yes")
        self.assertEqual((code, out, err), (0, f"running: {WINGET_LINE}\npython: {self.shown} (Python {VERSION})\n"
                                               "installed: Python now runs\n", ""))
        self.assertEqual(self.stubs.calls("winget"), ["".join(f"[{a}]" for a in WINGET_ARGS)])
        for name in ("brew", "apt-get", "dnf", "sudo"):
            self.assertEqual(self.stubs.calls(name), [], name)

    def test_install_on_windows_reports_a_failed_install(self):
        self.stubs.installer("winget", "exit 17")
        self.assertEqual(self.install("--yes"), (5, f"running: {WINGET_LINE}\n"
                                                    "python: still missing after winget (exit 17)\n"
                                                    f"install: {BY_HAND_WINDOWS}\n", ""))
        self.assertEqual(len(self.stubs.calls("winget")), 1)
        (self.stubs.bin / "winget").unlink()
        self.assertEqual(self.install("--yes"), (5, f"{MISSING}\ninstall: {BY_HAND_WINDOWS}\n", ""))
        self.assertEqual(len(self.stubs.calls("winget")), 1)  # no second call

    def test_install_with_python_present_installs_nothing(self):
        self.stubs.python("python3")
        for system in (WINDOWS_UNAME, "Darwin", "Linux"):
            with self.subTest(system=system):
                self.assertEqual(self.install("--yes", system=system),
                                 (0, f"python: python3 (Python {VERSION})\nnothing to install\n", ""))
        self.no_installer_ran()

    def test_the_installer_command_is_fixed_text(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertEqual(source.count("Python.Python.3.13"), 2, "the line shown and the line run")
        self.assertNotIn("eval", source)
        for line in source.splitlines():
            if line.lstrip().startswith("winget "):
                self.assertEqual(line.split("<")[0].strip(), WINGET_LINE)


if __name__ == "__main__":
    unittest.main()
