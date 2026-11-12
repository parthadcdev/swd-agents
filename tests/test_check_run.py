"""Tests for scripts/check_run.py. Run from the repo root: python3 -m unittest tests.test_check_run"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_run.py"
sys.path.insert(0, str(ROOT / "scripts"))

PLAN = """# Plan

Test command: `python3 -m unittest`

### T1: First thing
- Role: generalist-engineer
- Wave: 1
- Files: a.py, tests/test_a.py
- Depends: none
- Check: `python3 -m unittest tests.test_a`

### T2: Second thing
- Role: backend-engineer
- Wave: 2
- Files: b.py
- Depends: T1
- Check: `python3 -m unittest tests.test_b`
"""

LEDGER = """| Task | Role | Status | Attempts |
|---|---|---|---|
| T1 | generalist-engineer | done | 1 |
| T2 | backend-engineer | done | 2 |
"""

BUILDER_REPORT = """## Summary
Did it.
## Files changed
- a.py
## Test first (failing)
FAILED (errors=1)
## Test after (passing)
OK
## Complexity
O(n) time, O(1) space.
## Concerns
None.
"""

CHECKER_REPORT = "Verdict: pass\n\n## Findings\nNone.\n"

ACTIVITY = """- 10:00:00 dispatch T1 generalist-engineer
- 10:05:00 return T1
- 10:06:00 dispatch T2 backend-engineer
- 10:09:00 done all tasks complete
"""


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True,
    )


def commit(repo, subject, files):
    for name in files:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(path.read_text() + "x\n" if path.exists() else "x\n")
    git(repo, "add", "-A", "--", *files)
    git(repo, "commit", "-m", subject)


def make_run(tmp, mode="production", single=False):
    """A valid run in a fresh git repo: two tasks in two waves, or just T1 when single. Returns (repo, run)."""
    repo = Path(tmp)
    run = repo / ".swd" / "runs" / "2026-11-12-demo"
    (run / "reports").mkdir(parents=True)
    (run / "requirement.md").write_text("Do the thing.\n")
    (run / "spec.md").write_text(f"# Spec\n\nMode: {mode}\n\n## Acceptance criteria\n- It works.\n")
    (run / "standards.md").write_text("standards\n")
    (run / "plan.md").write_text(PLAN.split("### T2")[0] if single else PLAN)
    (run / "ledger.md").write_text(LEDGER.split("| T2")[0] if single else LEDGER)
    (run / "decisions.md").write_text("None.\n")
    (run / "activity.md").write_text(ACTIVITY.replace("- 10:06:00 dispatch T2 backend-engineer\n", "") if single else ACTIVITY)
    (run / "dashboard.html").write_text("<html></html>\n")
    (run / "write-check.txt").write_text("edited\n")
    (run / "reports" / "T1-generalist-engineer.md").write_text(BUILDER_REPORT)
    if not single:
        (run / "reports" / "T2-backend-engineer.md").write_text(BUILDER_REPORT)
    (run / "reports" / "final-qa-engineer.md").write_text(CHECKER_REPORT)
    git(repo, "init", "-q")
    # History from before this run, including an old run's task commit, must be ignored.
    commit(repo, "T9: task from an earlier run", ["old/x.py"])
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (run / "decisions.md").write_text(
        f"Base commit: {base}\nBase branch: main\nBranch: swd/demo\nWorktree: {repo}\nHousekeeping: removed 0, kept 0\nFinish: branch\n\n- None.\n")
    if mode == "production":
        names = ["T1-code-reviewer", "T1-security-reviewer"]
        if not single:  # a one-task run needs no final reviews: the task's own reviews covered the whole change
            names += ["T2-code-reviewer", "T2-security-reviewer", "final-code-reviewer", "final-security-reviewer"]
        for name in names:
            (run / "reports" / f"{name}.md").write_text(CHECKER_REPORT)
        commit(repo, "T1: First thing", ["a.py", "tests/test_a.py"])
        if not single:
            commit(repo, "T2: Second thing", ["b.py"])
    else:
        (run / "reports" / "final-code-reviewer.md").write_text(CHECKER_REPORT)
        commit(repo, "W1: first wave", ["a.py", "tests/test_a.py"])
        if not single:
            commit(repo, "W2: second wave", ["b.py"])
    return repo, run


def replace(path, old, new):
    text = path.read_text()
    assert old in text, f"{old!r} not in {path}"
    path.write_text(text.replace(old, new))


class CheckRunTest(unittest.TestCase):
    def setUp(self):
        import check_run
        self.cr = check_run
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name

    def problems(self, repo, run):
        return self.cr.check_run(run, repo)

    def assertProblem(self, problems, *needles):
        self.assertTrue(
            any(all(n in p for n in needles) for p in problems),
            f"no problem mentioning {needles}; got {problems}",
        )

    def test_valid_production_run_has_no_problems(self):
        repo, run = make_run(self.tmp)
        self.assertEqual(self.problems(repo, run), [])

    def test_valid_prototype_run_has_no_problems(self):
        repo, run = make_run(self.tmp, mode="prototype")
        self.assertEqual(self.problems(repo, run), [])

    def test_single_task_plan_is_valid(self):
        repo, run = make_run(self.tmp)
        (run / "plan.md").write_text(PLAN.split("### T2")[0])
        self.assertEqual(self.cr.check_plan(run), [])

    def test_same_wave_shared_file_is_reported(self):
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "- Wave: 2\n- Files: b.py\n- Depends: T1", "- Wave: 1\n- Files: b.py, a.py\n- Depends: none")
        self.assertProblem(self.cr.check_plan(run), "T1", "T2", "a.py")

    def test_dependency_in_same_or_later_wave_is_reported(self):
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "- Wave: 2", "- Wave: 1")
        self.assertProblem(self.cr.check_plan(run), "T2", "T1", "earlier wave")

    def test_missing_test_command_is_reported(self):
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "Test command: `python3 -m unittest`\n", "")
        self.assertProblem(self.cr.check_plan(run), "Test command")

    def test_malformed_task_is_reported_not_raised(self):
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "- Files: b.py\n", "")
        self.assertProblem(self.cr.check_plan(run), "T2", "Files")

    def test_malformed_ledger_row_is_reported_not_raised(self):
        repo, run = make_run(self.tmp)
        replace(run / "ledger.md", "| T2 | backend-engineer | done | 2 |", "| T2 | backend-engineer | finished | x |")
        problems = self.problems(repo, run)
        self.assertProblem(problems, "ledger.md", "finished")
        self.assertProblem(problems, "ledger.md", "Attempts")

    def test_task_not_done_is_reported(self):
        repo, run = make_run(self.tmp)
        replace(run / "ledger.md", "| T2 | backend-engineer | done |", "| T2 | backend-engineer | in-review |")
        self.assertProblem(self.problems(repo, run), "T2", "in-review")

    def test_missing_fail_then_pass_evidence_is_reported(self):
        repo, run = make_run(self.tmp)
        replace(run / "reports" / "T1-generalist-engineer.md", "FAILED (errors=1)\n", "")
        self.assertProblem(self.problems(repo, run), "T1-generalist-engineer.md", "Test first (failing)")

    def test_commit_outside_owned_files_is_reported(self):
        repo, run = make_run(self.tmp)
        commit(repo, "T2: sneaky fix", ["a.py"])
        self.assertProblem(self.problems(repo, run), "T2", "a.py")

    def test_missing_task_review_in_production_is_reported(self):
        repo, run = make_run(self.tmp)
        (run / "reports" / "T2-code-reviewer.md").unlink()
        self.assertProblem(self.problems(repo, run), "T2-code-reviewer.md")

    def test_per_task_review_in_prototype_is_allowed(self):
        # The principal raises the bar for a risky task inside a prototype.
        repo, run = make_run(self.tmp, mode="prototype")
        (run / "reports" / "T1-code-reviewer.md").write_text(CHECKER_REPORT)
        self.assertEqual(self.problems(repo, run), [])

    def test_malformed_task_heading_is_reported(self):
        for heading in ("### T2 - Second thing", "## T2: Second thing", "### Task 2: Second thing"):
            with self.subTest(heading=heading), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                replace(run / "plan.md", "### T2: Second thing", heading)
                self.assertProblem(self.cr.check_plan(run), "plan.md line", "### T<n>: <title>")

    def test_non_decimal_numbers_are_reported_not_raised(self):
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "- Wave: 2", "- Wave: \u00b2")
        replace(run / "ledger.md", "| done | 2 |", "| done | \u00b2 |")
        problems = self.problems(repo, run)
        self.assertProblem(problems, "T2", "Wave")
        self.assertProblem(problems, "ledger.md", "Attempts")

    def test_uncommitted_work_is_reported(self):
        repo, run = make_run(self.tmp)
        (repo / "a.py").write_text("changed\n")
        (repo / "stray.txt").write_text("x\n")
        problems = self.problems(repo, run)
        self.assertProblem(problems, "uncommitted", "a.py")
        self.assertProblem(problems, "uncommitted", "stray.txt")

    def test_any_failing_checker_verdict_is_reported(self):
        for name in ("T1-security-reviewer.md", "final-code-reviewer.md", "wave-1-qa-engineer.md"):
            with self.subTest(report=name), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                (run / "reports" / name).write_text("Verdict: fail\n\n## Findings\n- broken\n")
                self.assertProblem(self.problems(repo, run), name, "Verdict")

    def test_missing_security_and_final_reviews_in_production_are_reported(self):
        for name in ("T2-security-reviewer.md", "final-code-reviewer.md", "final-security-reviewer.md"):
            with self.subTest(report=name), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                (run / "reports" / name).unlink()
                self.assertProblem(self.problems(repo, run), "missing", name)

    def test_non_ascii_file_names_work(self):
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "- Files: b.py", "- Files: b.py, docs/caf\u00e9.md")
        commit(repo, "T2: add docs", ["docs/caf\u00e9.md"])
        self.assertEqual(self.problems(repo, run), [])

    def test_failing_qa_verdict_is_reported(self):
        repo, run = make_run(self.tmp)
        (run / "reports" / "final-qa-engineer.md").write_text("Verdict: fail\n\n## Findings\n- broken\n")
        self.assertProblem(self.problems(repo, run), "final-qa-engineer.md", "Verdict")

    def test_one_task_production_run_needs_no_final_reviews(self):
        repo, run = make_run(self.tmp, single=True)
        self.assertEqual(self.problems(repo, run), [])

    def test_one_task_prototype_run_still_needs_its_one_review(self):
        repo, run = make_run(self.tmp, mode="prototype", single=True)
        self.assertEqual(self.problems(repo, run), [])
        (run / "reports" / "final-code-reviewer.md").unlink()
        self.assertProblem(self.problems(repo, run), "missing", "final-code-reviewer.md")

    def test_same_file_spelled_two_ways_is_one_file(self):
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "- Wave: 2\n- Files: b.py\n- Depends: T1", "- Wave: 1\n- Files: b.py, ./a.py\n- Depends: none")
        self.assertProblem(self.cr.check_plan(run), "T1", "T2", "a.py")

    def test_report_with_two_verdict_lines_is_reported(self):
        repo, run = make_run(self.tmp)
        (run / "reports" / "final-qa-engineer.md").write_text(
            "Verdict: fail\n\n## Findings\n- The builder claimed:\nVerdict: pass\n")
        self.assertProblem(self.problems(repo, run), "final-qa-engineer.md", "exactly one")

    def test_placeholder_test_evidence_is_reported(self):
        for placeholder in ("TODO", "tbd", "N/A", "..."):
            with self.subTest(placeholder=placeholder), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                replace(run / "reports" / "T1-generalist-engineer.md", "FAILED (errors=1)", placeholder)
                self.assertProblem(self.problems(repo, run), "T1-generalist-engineer.md", "Test first (failing)")

    # --- a returned task, checked before review ---------------------------------------------

    def test_returned_task_with_reported_owned_changes_passes(self):
        repo, run = make_run(self.tmp)
        (repo / "a.py").write_text("changed\n")  # BUILDER_REPORT lists a.py under Files changed
        self.assertEqual(self.cr.check_task(run, repo, "T1"), [])

    def test_change_the_report_does_not_claim_is_reported(self):
        # A real run had files brought to the contract by a writer no report accounted for.
        repo, run = make_run(self.tmp)
        (repo / "tests" / "test_a.py").write_text("changed\n")
        self.assertProblem(self.cr.check_task(run, repo, "T1"), "tests/test_a.py", "not listed", "T1-generalist-engineer.md")

    def test_change_no_task_owns_is_reported(self):
        repo, run = make_run(self.tmp)
        (repo / "sub").mkdir()
        (repo / "sub" / "stray.json").write_text("{}\n")
        self.assertProblem(self.cr.check_task(run, repo, "T1"), "sub/stray.json", "no task owns")

    def test_changes_owned_by_another_task_are_left_to_that_task(self):
        repo, run = make_run(self.tmp)
        (repo / "b.py").write_text("changed\n")  # T2's file, T2 may still be running
        self.assertEqual(self.cr.check_task(run, repo, "T1"), [])

    def test_unknown_task_is_reported_not_raised(self):
        repo, run = make_run(self.tmp)
        self.assertProblem(self.cr.check_task(run, repo, "T7"), "T7", "not in plan.md")

    def test_plan_changed_after_sealing_is_reported(self):
        # A real run had plan.md replaced mid-build by a version with no tasks.
        repo, run = make_run(self.tmp)
        self.cr.seal_plan(run)
        self.assertEqual(self.cr.check_task(run, repo, "T1"), [])
        replace(run / "plan.md", "First thing", "Something else")
        self.assertProblem(self.cr.check_task(run, repo, "T1"), "plan.md", "changed since it was sealed")
        self.assertProblem(self.problems(repo, run), "plan.md", "changed since it was sealed")

    def test_resealing_accepts_an_amended_plan(self):
        repo, run = make_run(self.tmp)
        self.cr.seal_plan(run)
        replace(run / "plan.md", "First thing", "First thing, amended")
        self.cr.seal_plan(run)
        self.assertEqual(self.cr.check_task(run, repo, "T1"), [])

    def test_cli_seal_and_task(self):
        repo, run = make_run(self.tmp)
        sealed = self.cli("--seal", str(run))
        self.assertEqual(sealed.returncode, 0, sealed.stdout)
        self.assertIn("Plan checksum: ", (run / "decisions.md").read_text())
        self.assertEqual(self.cli("--task", "T1", str(run)).returncode, 0)
        (repo / "stray.txt").write_text("x\n")
        bad = self.cli("--task", "T1", str(run))
        self.assertEqual(bad.returncode, 1)
        self.assertIn("stray.txt", bad.stdout)

    def test_cli_will_not_seal_a_broken_plan(self):
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "- Files: b.py\n", "")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 1)
        self.assertNotIn("Plan checksum: ", (run / "decisions.md").read_text())

    def test_plan_check_requires_the_worktree_lines(self):
        for line in ("Worktree: ", "Branch: ", "Base branch: ", "Housekeeping: "):
            with self.subTest(line=line), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                text = (run / "decisions.md").read_text()
                (run / "decisions.md").write_text("".join(l for l in text.splitlines(True) if not l.startswith(line)))
                self.assertProblem(self.cr.check_plan(run), "decisions.md", line.strip())

    def test_seal_requires_a_finish_choice(self):
        repo, run = make_run(self.tmp)
        replace(run / "decisions.md", "Finish: branch\n", "")
        refused = self.cli("--seal", str(run))
        self.assertEqual(refused.returncode, 1)
        self.assertIn("Finish:", refused.stdout)
        self.assertNotIn("Plan checksum: ", (run / "decisions.md").read_text())
        with open(run / "decisions.md", "a") as f:
            f.write("Finish: sometime\n")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 1)

    def test_git_checks_run_in_the_worktree_not_the_users_copy(self):
        repo, run = make_run(self.tmp)
        with tempfile.TemporaryDirectory() as elsewhere:
            work = Path(elsewhere) / "work"
            subprocess.run(["git", "clone", "-q", str(repo), str(work)], check=True, capture_output=True)
            replace(run / "decisions.md", f"Worktree: {repo}", f"Worktree: {work}")
            (repo / "notes.txt").write_text("the user's own uncommitted work\n")
            self.assertEqual(self.cli(str(run)).stdout, "")
            (work / "stray.txt").write_text("x\n")
            self.assertIn("stray.txt", self.cli(str(run)).stdout)

    def test_plan_check_requires_the_write_check(self):
        # A pilot showed the principal skipping the write check in prototype mode.
        for content in (None, "written\n"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                (run / "write-check.txt").unlink()
                if content:
                    (run / "write-check.txt").write_text(content)
                self.assertProblem(self.cr.check_plan(run), "write-check.txt")

    def test_missing_dashboard_is_reported(self):
        # A pilot showed the principal skipping the dashboard as if it were optional.
        repo, run = make_run(self.tmp)
        (run / "dashboard.html").unlink()
        self.assertProblem(self.problems(repo, run), "dashboard.html", "swd-dashboard.py")

    def test_missing_dispatch_in_activity_is_reported(self):
        repo, run = make_run(self.tmp)
        replace(run / "activity.md", "- 10:06:00 dispatch T2 backend-engineer\n", "")
        self.assertProblem(self.problems(repo, run), "activity.md", "T2")

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)

    def test_cli_exit_codes(self):
        repo, run = make_run(self.tmp)
        ok = self.cli(str(repo))
        self.assertEqual((ok.returncode, ok.stdout), (0, ""))
        (run / "decisions.md").unlink()
        bad = self.cli(str(repo))
        self.assertEqual(bad.returncode, 1)
        self.assertIn("decisions.md", bad.stdout)
        self.assertNotIn("Traceback", bad.stderr)
        with tempfile.TemporaryDirectory() as empty:
            none = self.cli(empty)
            self.assertEqual(none.returncode, 1)
            self.assertIn("no run folder found", none.stdout)

    def test_cli_accepts_a_run_folder(self):
        repo, run = make_run(self.tmp)
        later = run.parent / "2026-11-12-zebra"  # sorts after the real run, and is empty
        later.mkdir()
        self.assertEqual(self.cli(str(repo)).returncode, 1)
        self.assertEqual(self.cli(str(run)).returncode, 0)

    def test_cli_plan_mode_ignores_missing_ledger(self):
        repo, run = make_run(self.tmp)
        (run / "ledger.md").unlink()
        self.assertEqual(self.cli("--plan", str(repo)).returncode, 0)
        self.assertEqual(self.cli(str(repo)).returncode, 1)


if __name__ == "__main__":
    unittest.main()
