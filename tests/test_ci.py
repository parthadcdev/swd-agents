"""The CI workflow runs the suite on Windows, macOS and Linux (plan C6)."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"

# The record of the workflow: plan C6 plus the T3 ruling in decisions.md
# (job timeout, no persisted credentials). Any edit to the file must be made
# here too, so a change that stops it testing Windows cannot pass silently.
EXPECTED = """\
name: tests

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, macos-latest, ubuntu-latest]
        python: ["3.9", "3.13"]
    runs-on: ${{ matrix.os }}
    timeout-minutes: 15
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0  # v7.1.0
        with:
          python-version: ${{ matrix.python }}
      - name: Run the test suite
        run: python -m unittest discover -s tests
"""


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(WORKFLOW.is_file(), f"missing {WORKFLOW}")
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_on_push_and_pull_request(self):
        self.assertIn("\non:\n  push:\n  pull_request:\n", self.text)

    def test_permissions_are_read_only(self):
        self.assertIn("\npermissions:\n  contents: read\n", self.text)
        self.assertNotIn("write", self.text)

    def test_matrix_has_three_systems_and_two_pythons(self):
        self.assertIn("os: [windows-latest, macos-latest, ubuntu-latest]", self.text)
        self.assertIn('python: ["3.9", "3.13"]', self.text)
        self.assertIn("fail-fast: false", self.text)
        self.assertIn("runs-on: ${{ matrix.os }}", self.text)
        self.assertIn("python-version: ${{ matrix.python }}", self.text)

    def test_runs_the_suite_under_bash(self):
        self.assertIn("defaults:\n      run:\n        shell: bash\n", self.text)
        self.assertIn("run: python -m unittest discover -s tests\n", self.text)

    def test_every_action_is_pinned_by_commit(self):
        uses = re.findall(r"uses:\s*(\S+)", self.text)
        self.assertEqual(
            uses,
            [
                "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0",
            ],
        )
        for use in uses:
            self.assertRegex(use, r"@[0-9a-f]{40}$")

    def test_job_is_bounded_and_checkout_keeps_no_token(self):
        self.assertIn("\n    timeout-minutes: 15\n", self.text)
        self.assertIn("\n          persist-credentials: false\n", self.text)

    def test_whole_file_is_the_expected_text(self):
        self.maxDiff = None  # show the changed lines, not a truncated diff
        self.assertEqual(self.text, EXPECTED)

    def test_no_utf8_override(self):
        for name in ("PYTHONUTF8", "PYTHONIOENCODING", "env:"):
            self.assertNotIn(name, self.text)


if __name__ == "__main__":
    unittest.main()
