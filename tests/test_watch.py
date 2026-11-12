"""Tests for scripts/swd-watch.sh, using a stub `herdr` on PATH."""
import os
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
        stub.write_text(STUB)
        stub.chmod(0o755)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        self.env["HERDR_STUB_LOG"] = str(self.log)

    def watch(self, **extra):
        return subprocess.run(
            ["bash", str(SCRIPT), str(self.run_dir)],
            env={**self.env, **extra}, capture_output=True, text=True,
        )

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

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


if __name__ == "__main__":
    unittest.main()
