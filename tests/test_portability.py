"""Every script under scripts/ reads, writes and captures text as UTF-8, whatever the system's code page.

On Windows Python decodes and encodes text in the code page (cp1252) unless told otherwise, so a call
without `encoding=` garbles or crashes on non-ASCII text there and passes everywhere else. This reads
each script's syntax tree, so the rule holds on the machine the team works on too.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUBPROCESS_CALLS = {"run", "Popen", "check_output", "call"}


def keywords(call):
    return {k.arg: k.value for k in call.keywords if k.arg}


def is_true(node):
    return isinstance(node, ast.Constant) and node.value is True


def is_utf8_reconfigure(call, stream):
    """sys.<stream>.reconfigure(encoding="utf-8", ...)"""
    func = call.func
    encoding = keywords(call).get("encoding")
    return (isinstance(func, ast.Attribute) and func.attr == "reconfigure"
            and isinstance(func.value, ast.Attribute) and func.value.attr == stream
            and isinstance(func.value.value, ast.Name) and func.value.value.id == "sys"
            and isinstance(encoding, ast.Constant) and encoding.value == "utf-8")


def problems(source, name):
    """One line per text call with no encoding, and per __main__ block that leaves stdout or stderr alone."""
    found = []
    tree = ast.parse(source, name)
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        func, kw = call.func, keywords(call)
        if "encoding" in kw:
            continue
        where = f"{name}:{call.lineno}"
        if isinstance(func, ast.Attribute) and func.attr in ("read_text", "write_text"):
            found.append(f"{where}: {func.attr}() without encoding=")
        elif isinstance(func, ast.Name) and func.id == "open":
            mode = call.args[1] if len(call.args) > 1 else kw.get("mode")
            if not (isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" in mode.value):
                found.append(f"{where}: open() in text mode without encoding=")
        elif (isinstance(func, ast.Attribute) and func.attr in SUBPROCESS_CALLS
              and isinstance(func.value, ast.Name) and func.value.id == "subprocess"
              and (is_true(kw.get("text")) or is_true(kw.get("universal_newlines")))):
            found.append(f"{where}: subprocess.{func.attr}() with text output but no encoding=")
    for block in tree.body:
        test = getattr(block, "test", None)
        if not (isinstance(block, ast.If) and isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name) and test.left.id == "__name__"
                and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in test.comparators)):
            continue
        calls = [node for node in ast.walk(block) if isinstance(node, ast.Call)]
        for stream in ("stdout", "stderr"):
            if not any(is_utf8_reconfigure(call, stream) for call in calls):
                found.append(f"{name}:{block.lineno}: the __main__ block does not reconfigure sys.{stream} to utf-8")
    return found


class PortabilityTest(unittest.TestCase):
    def test_every_script_uses_utf8_explicitly(self):
        scripts = sorted((ROOT / "scripts").glob("*.py"))
        self.assertTrue(scripts)
        found = []
        for path in scripts:
            found += problems(path.read_text(encoding="utf-8"), f"scripts/{path.name}")
        self.assertEqual(found, [])

    def test_the_guard_catches_each_bad_call(self):
        bad = "\n".join([
            "import subprocess, sys",
            "p.read_text()",
            "p.write_text('x')",
            "open(p)",
            "open(p, 'a')",
            "open(p, mode='w')",
            "subprocess.run(['x'], text=True)",
            "subprocess.Popen(['x'], universal_newlines=True)",
            "subprocess.check_output(['x'], text=True)",
            "subprocess.call(['x'], text=True)",
            "if __name__ == '__main__':",
            "    sys.stdout.reconfigure(encoding='latin-1')",
            "    sys.exit(0)",
        ])
        self.assertEqual(problems(bad, "bad.py"), [
            "bad.py:2: read_text() without encoding=",
            "bad.py:3: write_text() without encoding=",
            "bad.py:4: open() in text mode without encoding=",
            "bad.py:5: open() in text mode without encoding=",
            "bad.py:6: open() in text mode without encoding=",
            "bad.py:7: subprocess.run() with text output but no encoding=",
            "bad.py:8: subprocess.Popen() with text output but no encoding=",
            "bad.py:9: subprocess.check_output() with text output but no encoding=",
            "bad.py:10: subprocess.call() with text output but no encoding=",
            "bad.py:11: the __main__ block does not reconfigure sys.stdout to utf-8",
            "bad.py:11: the __main__ block does not reconfigure sys.stderr to utf-8",
        ])

    def test_the_guard_passes_what_is_safe(self):
        good = "\n".join([
            "import os, subprocess, sys",
            "p.read_text(encoding='utf-8')",
            "p.write_text('x', encoding='utf-8')",
            "p.read_bytes()",
            "open(p, 'rb')",
            "open(p, mode='ab')",
            "open(p, 'a', encoding='utf-8')",
            "os.open(p, os.O_RDONLY)",
            "subprocess.run(['x'], capture_output=True)",
            "subprocess.run(['x'], text=True, encoding='utf-8', errors='replace')",
            "if __name__ == '__main__':",
            "    sys.stdout.reconfigure(encoding='utf-8', errors='replace')",
            "    sys.stderr.reconfigure(encoding='utf-8', errors='replace')",
            "    sys.exit(0)",
        ])
        self.assertEqual(problems(good, "good.py"), [])


if __name__ == "__main__":
    unittest.main()
