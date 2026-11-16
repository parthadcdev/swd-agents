"""Tests for scripts/swd-watch.sh, using stub `herdr` and `hc` commands on PATH."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "swd-watch.sh"

STUB = """#!/bin/sh
echo "$*" >> "$HERDR_STUB_LOG"
[ -n "$HERDR_STUB_FAIL" ] && exit 1
echo '{"result":{"pane":{"pane_id":"p2"}}}'
"""

HC_STUB = """#!/bin/sh
echo "$# $*" >> "$HC_STUB_LOG"
[ -n "$HC_STUB_FAIL" ] && exit 1
exit 0
"""


@unittest.skipIf(os.name == "nt", "the herdr watch terminals are macOS and Linux only")
class WatchTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.run_dir = tmp / "run"
        self.run_dir.mkdir()
        self.log = tmp / "herdr.log"
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "herdr"
        stub.write_text(STUB, encoding="utf-8")
        stub.chmod(0o755)
        self.hc_log = tmp / "hc.log"
        self.hc_stub = bin_dir / "hc"
        self.hc_stub.write_text(HC_STUB, encoding="utf-8")
        self.hc_stub.chmod(0o755)
        self.bin_dir = bin_dir
        # Never inherit the host's Herdr variables: the real `hc` must not be reachable.
        self.env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("HERDR_") and k != "HC_TERMINAL_SOCKET"
        }
        self.bash = shutil.which("bash")   # found before PATH changes, never run by bare name
        self.env["PATH"] = f"{bin_dir}{os.pathsep}{self.env['PATH']}"
        self.env["HERDR_STUB_LOG"] = str(self.log)
        self.env["HC_STUB_LOG"] = str(self.hc_log)

    def watch(self, **extra):
        return subprocess.run(
            [self.bash, str(SCRIPT), str(self.run_dir)],
            env={**self.env, **extra}, capture_output=True, text=True, encoding="utf-8",
        )

    def calls(self):
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def test_outside_herdr_prints_fallback(self):
        result = self.watch()
        self.assertEqual(result.returncode, 0)
        self.assertIn("ledger.md", result.stdout)
        self.assertIn("tail -f", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_inside_herdr_opens_two_panes(self):
        result = self.watch(HERDR_PANE_ID="p1")
        self.assertEqual(result.returncode, 0)
        splits = [c for c in self.calls() if c.startswith("pane split")]
        runs = [c for c in self.calls() if c.startswith("pane run")]
        self.assertEqual(len(splits), 2)
        self.assertIn("--current", splits[0])
        self.assertIn("--direction right", splits[0])
        self.assertIn("p2", splits[1])
        self.assertIn("--direction down", splits[1])
        self.assertEqual(len(runs), 2)
        self.assertTrue(any("ledger.md" in c for c in runs))
        self.assertTrue(any("activity.md" in c for c in runs))

    def test_herdr_failure_is_not_fatal(self):
        result = self.watch(HERDR_PANE_ID="p1", HERDR_STUB_FAIL="1")
        self.assertEqual(result.returncode, 0)

    def hc_calls(self):
        return self.hc_log.read_text(encoding="utf-8").splitlines() if self.hc_log.exists() else []

    def test_app_starts_two_terminals(self):
        result = self.watch(HC_TERMINAL_SOCKET="/s")
        self.assertEqual(result.returncode, 0)
        ledger, activity = self.hc_calls()
        for line in (ledger, activity):
            self.assertTrue(line.startswith("7 run --bg --no-notify --label swd="), line)
        self.assertIn("swd=ledger", ledger)
        self.assertIn("ledger.md", ledger)
        self.assertIn("swd=activity", activity)
        self.assertIn("tail -f", activity)
        self.assertIn("activity.md", activity)
        self.assertEqual(self.calls(), [])
        self.assertIn("started the ledger and activity terminals", result.stdout)

    def test_herdr_pane_wins_over_app(self):
        result = self.watch(HERDR_PANE_ID="p1", HC_TERMINAL_SOCKET="/s")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.hc_calls(), [])
        self.assertTrue(self.calls())

    def test_neither_set_does_not_call_hc(self):
        result = self.watch()
        self.assertEqual(self.hc_calls(), [])
        self.assertIn("Not running inside herdr", result.stdout)

    def test_hc_missing(self):
        self.hc_stub.unlink()
        result = self.watch(HC_TERMINAL_SOCKET="/s", PATH=os.pathsep.join([str(self.bin_dir), "/usr/bin", "/bin"]))
        self.assertEqual(result.returncode, 0)
        self.assertIn("hc not found", result.stdout)
        self.assertEqual(self.hc_calls(), [])
        self.assertEqual(self.calls(), [])

    def test_hc_failure_is_not_fatal(self):
        result = self.watch(HC_TERMINAL_SOCKET="/s", HC_STUB_FAIL="1")
        self.assertEqual(result.returncode, 0)
        self.assertIn("warning", result.stdout)
        self.assertEqual(len(self.hc_calls()), 1)

    def test_run_dir_with_space(self):
        self.run_dir = self.run_dir.parent / "my run"
        self.run_dir.mkdir()
        self.watch(HC_TERMINAL_SOCKET="/s")
        ledger = self.hc_calls()[0]
        self.assertTrue(ledger.startswith("7 run "), ledger)
        self.assertIn(f"'{self.run_dir}/ledger.md'", ledger)


if __name__ == "__main__":
    unittest.main()
