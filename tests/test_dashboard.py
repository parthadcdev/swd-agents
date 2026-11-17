"""Tests for scripts/swd-dashboard.py, which renders a run folder as one HTML page."""
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "swd-dashboard.py"
sys.path.insert(0, str(ROOT / "scripts"))

SPEC = "# Spec: cart total\n\nMode: production\n\n## Acceptance criteria\n- It works.\n"

PLAN = """# Plan

Test command: `python3 -m unittest`

### T1: Add <total> to cart
- Role: generalist-engineer
- Wave: 1
- Files: a.py, tests/test_a.py
- Depends: none
- Check: `python3 -m unittest tests.test_a`

### T2: Wire the API
- Role: backend-engineer
- Wave: 2
- Files: b.py
- Depends: T1
- Check: `python3 -m unittest tests.test_b`
"""

LEDGER = """| Task | Role | Status | Attempts |
|---|---|---|---|
| T1 | generalist-engineer | done | 1 |
| T2 | backend-engineer | in-progress | 2 |
"""

ACTIVITY = """- 10:00:00 dispatch T1 generalist-engineer
- 10:05:00 commit T1
- 10:06:00 dispatch T2 backend-engineer
"""


STAFFING = """# Staffing

| For | Agent | Model | Effort | Why |
|---|---|---|---|---|
| T1 | generalist-engineer | opus | medium | The hook and its tests |
| T2 | backend-engineer | <b>sonnet</b> | low | A small change |
| review | code-reviewer, security-reviewer | opus | medium | Review |
| final | qa-engineer | opus | low | Runs commands |
"""


def load():
    spec = importlib.util.spec_from_file_location("swd_dashboard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name) / "2026-11-12-cart-total"
        self.run_dir.mkdir()
        (self.run_dir / "spec.md").write_text(SPEC, encoding="utf-8")
        (self.run_dir / "plan.md").write_text(PLAN, encoding="utf-8")
        (self.run_dir / "ledger.md").write_text(LEDGER, encoding="utf-8")
        (self.run_dir / "activity.md").write_text(ACTIVITY, encoding="utf-8")
        self.dash = load()

    def test_shows_tasks_by_wave_with_status_and_role(self):
        page = self.dash.render(self.run_dir)
        self.assertLess(page.index("Wave 1"), page.index("Wave 2"))
        self.assertLess(page.index("Wave 1"), page.index("T1"))
        self.assertLess(page.index("Wave 2"), page.index("T2"))
        self.assertIn('class="task status-done"', page)
        self.assertIn('class="task status-in-progress"', page)
        self.assertIn("backend-engineer", page)
        self.assertIn("Wire the API", page)
        self.assertIn("after T1", page)
        self.assertIn("attempt 2", page)

    def test_shows_run_name_mode_and_progress(self):
        page = self.dash.render(self.run_dir)
        self.assertIn("2026-11-12-cart-total", page)
        self.assertIn("production", page)
        self.assertIn("1 of 2 tasks done", page)

    def test_shows_the_timeline_newest_first(self):
        page = self.dash.render(self.run_dir)
        self.assertLess(page.index("10:06:00"), page.index("10:00:00"))
        self.assertIn("dispatch", page)

    def test_escapes_text_from_the_run_folder(self):
        page = self.dash.render(self.run_dir)
        self.assertIn("Add &lt;total&gt; to cart", page)
        self.assertNotIn("<total>", page)

    def test_refreshes_until_the_run_is_done(self):
        self.assertIn('http-equiv="refresh"', self.dash.render(self.run_dir))
        with open(self.run_dir / "activity.md", "a", encoding="utf-8") as f:
            f.write("- 10:09:00 done all tasks complete\n")
        self.assertNotIn('http-equiv="refresh"', self.dash.render(self.run_dir))

    def test_a_task_not_yet_in_the_ledger_is_todo(self):
        (self.run_dir / "ledger.md").unlink()
        page = self.dash.render(self.run_dir)
        self.assertEqual(page.count('class="task status-todo"'), 2)

    def test_renders_before_the_plan_exists(self):
        for name in ("plan.md", "ledger.md", "activity.md", "spec.md"):
            (self.run_dir / name).unlink()
        page = self.dash.render(self.run_dir)
        self.assertIn("No plan yet", page)

    def cli(self, *args):
        env = {**os.environ, "SWD_NO_BROWSER": "1"}
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=30, encoding="utf-8")

    def test_cli_writes_the_page(self):
        result = self.cli(str(self.run_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("T2", (self.run_dir / "dashboard.html").read_text(encoding="utf-8"))
        self.assertIn("dashboard.html", result.stdout)

    def test_watch_stops_when_the_run_is_done(self):
        with open(self.run_dir / "activity.md", "a", encoding="utf-8") as f:
            f.write("- 10:09:00 done all tasks complete\n")
        result = self.cli("--watch", "--open", str(self.run_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('http-equiv="refresh"', (self.run_dir / "dashboard.html").read_text(encoding="utf-8"))

    def test_watch_survives_a_page_it_cannot_replace(self):
        # Windows refuses to replace a file another program has open, such as the page in the browser.
        real_replace, calls = os.replace, []

        def replace_failing_once(source, target):
            calls.append(target)
            if len(calls) == 2:   # the first refresh in the loop; the run finishes meanwhile
                with open(self.run_dir / "activity.md", "a", encoding="utf-8") as f:
                    f.write("- 10:09:00 done all tasks complete\n")
                raise PermissionError(13, "The process cannot access the file", str(target))
            real_replace(source, target)

        self.dash.REFRESH_SECONDS = 0
        self.dash.MAX_WATCH_SECONDS = 5   # a regression fails here instead of hanging the suite
        with mock.patch.object(self.dash.os, "replace", replace_failing_once), \
                mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(self.dash.main(["--watch", str(self.run_dir)]), 0)
        self.assertEqual(len(calls), 3)
        self.assertNotIn('http-equiv="refresh"', (self.run_dir / "dashboard.html").read_text(encoding="utf-8"))

    def test_shows_each_tasks_the_checkers_and_the_conductors_model(self):
        (self.run_dir / "staffing.md").write_text(STAFFING, encoding="utf-8")
        (self.run_dir / "decisions.md").write_text("Base commit: 1a2b3c4\nConductor: Opus 5.5\n", encoding="utf-8")
        page = self.dash.render(self.run_dir)
        self.assertIn('<div class="meta">generalist-engineer · opus medium</div>', page)
        self.assertIn('<div class="meta">backend-engineer · &lt;b&gt;sonnet&lt;/b&gt; low · attempt 2 · after T1</div>', page)
        self.assertNotIn("<b>", page)
        self.assertIn('<span class="badge">Conductor: Opus 5.5</span>', page)
        self.assertLess(page.index("Running"), page.index("Conductor: Opus 5.5"))
        self.assertIn('<p class="summary">Review: opus medium · Final: opus low</p>', page)

    def test_markup_in_effort_and_conductor_is_escaped(self):
        (self.run_dir / "staffing.md").write_text(
            "| T1 | generalist-engineer | opus | <i>high</i> | x |\n"
            "| final | qa-engineer | <script>alert(1)</script> | low | x |\n", encoding="utf-8")
        (self.run_dir / "decisions.md").write_text("Conductor: <img src=x onerror=alert(1)>\n", encoding="utf-8")
        page = self.dash.render(self.run_dir)
        for raw in ("<i>", "<script>alert", "<img"):
            self.assertNotIn(raw, page)
        self.assertIn("generalist-engineer · opus &lt;i&gt;high&lt;/i&gt;</div>", page)
        self.assertIn("Final: &lt;script&gt;alert(1)&lt;/script&gt; low</p>", page)
        self.assertIn("Conductor: &lt;img src=x onerror=alert(1)&gt;</span>", page)

    def test_without_staffing_or_decisions_the_page_shows_no_models(self):
        page = self.dash.render(self.run_dir)
        self.assertIn('<div class="meta">generalist-engineer</div>', page)
        self.assertIn('<div class="meta">backend-engineer · attempt 2 · after T1</div>', page)
        self.assertNotIn("Conductor:", page)
        self.assertNotIn("Review:", page)
        self.assertNotIn("Final:", page)

    def test_a_missing_task_row_and_final_row_are_left_out(self):
        (self.run_dir / "staffing.md").write_text(
            "| For | Agent | Model | Effort | Why |\n|---|---|---|---|---|\n"
            "| T2 | backend-engineer | opus | low | x |\n"
            "| review | code-reviewer | opus | medium | x |\n", encoding="utf-8")
        page = self.dash.render(self.run_dir)
        self.assertIn('<div class="meta">generalist-engineer</div>', page)
        self.assertIn('<div class="meta">backend-engineer · opus low · attempt 2 · after T1</div>', page)
        self.assertIn('<p class="summary">Review: opus medium</p>', page)
        self.assertNotIn("Final:", page)

    def test_only_the_final_row_gives_only_the_final_part(self):
        (self.run_dir / "staffing.md").write_text("| final | qa-engineer | opus | low | x |\n", encoding="utf-8")
        page = self.dash.render(self.run_dir)
        self.assertIn('<p class="summary">Final: opus low</p>', page)
        self.assertNotIn("Review:", page)

    def test_rows_without_five_cells_and_note_lines_are_skipped(self):
        (self.run_dir / "staffing.md").write_text(
            "# Staffing\n\nA note | with a stray bar\n"
            "| T1 | generalist-engineer | opus | medium |\n"
            "final | qa-engineer | haiku | low | a row without a leading bar is still a row\n"
            "| T2 | backend-engineer | opus | low | x |\n"
            "| T2 | backend-engineer | sonnet | high | the last row for a task wins |\n", encoding="utf-8")
        page = self.dash.render(self.run_dir)
        self.assertIn('<div class="meta">generalist-engineer</div>', page)
        self.assertIn("backend-engineer · sonnet high · attempt 2", page)
        self.assertNotIn("opus low", page)
        self.assertIn('<p class="summary">Final: haiku low</p>', page)
        self.assertEqual(
            self.dash.read_staffing(self.run_dir),
            {"T2": ("sonnet", "high"), "final": ("haiku", "low")})

    def test_the_last_conductor_line_shows(self):
        (self.run_dir / "decisions.md").write_text(
            "Conductor: Fable 5.2\nJudge plan: the plan holds\nConductor: Opus 5.5\n", encoding="utf-8")
        page = self.dash.render(self.run_dir)
        self.assertIn("Conductor: Opus 5.5", page)
        self.assertNotIn("Fable 5.2", page)

    def test_read_staffing_never_raises(self):
        self.assertEqual(self.dash.read_staffing(self.run_dir), {})
        (self.run_dir / "staffing.md").mkdir()
        self.assertEqual(self.dash.read_staffing(self.run_dir), {})
        self.assertIn("2026-11-12-cart-total", self.dash.render(self.run_dir))

    def test_cli_writes_the_page_in_every_staffing_case(self):
        cases = {
            "full": (STAFFING, "Conductor: Opus 5.5\n"),
            "no staffing, no decisions": (None, None),
            "rows missing": ("| review | code-reviewer | opus | medium | x |\n", "Base commit: 1\n"),
            "bad rows": ("| T1 | a | b |\nnote | here\n", "Conductor: Fable 5.2\nConductor: Opus 5.5\n"),
        }
        for name, (staffing, decisions) in cases.items():
            with self.subTest(name):
                for file, text in (("staffing.md", staffing), ("decisions.md", decisions)):
                    path = self.run_dir / file
                    if text is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_text(text, encoding="utf-8")
                result = self.cli(str(self.run_dir))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str((self.run_dir / "dashboard.html").resolve()))
                self.assertIn("T2", (self.run_dir / "dashboard.html").read_text(encoding="utf-8"))

    def test_cli_missing_run_folder_is_an_error_not_a_traceback(self):
        result = self.cli(str(self.run_dir / "nope"))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
