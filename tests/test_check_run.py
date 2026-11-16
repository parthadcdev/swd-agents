"""Tests for scripts/check_run.py. Run from the repo root: python3 -m unittest tests.test_check_run"""
import re
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

## Outcome
$ python3 -m unittest
OK

## Tasks

### T1: First thing
- Role: generalist-engineer
- Wave: 1
- Files: a.py, tests/test_a.py
- Depends: none
- Check: `python3 -m unittest tests.test_a`
- Outcome: a.py exists

### T2: Second thing
- Role: backend-engineer
- Wave: 2
- Files: b.py
- Depends: T1
- Check: `python3 -m unittest tests.test_b`
- Outcome: b.py exists
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

STAFFING = """# Staffing

| For | Agent | Model | Effort | Why |
|---|---|---|---|---|
| plan | architect | opus | medium | Design |
| T1 | generalist-engineer | opus | medium | Multistep |
| T2 | backend-engineer | opus | low | Specified |
| review | code-reviewer, security-reviewer | opus | medium | Review |
| final | qa-engineer | opus | low | Runs commands |
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
    # What swd-test.py recorded: each task's check failing and then passing, the suite after
    # wave 1 (production only checks between waves), and the whole suite at the end.
    evidence = {"T1-001": 1, "T1-002": 0, "final-001": 0}
    if not single:
        evidence.update({"T2-001": 1, "T2-002": 0})
        if mode == "production":
            evidence["wave-1-001"] = 0
    (run / "evidence").mkdir()
    for name, code in evidence.items():
        (run / "evidence" / f"{name}.txt").write_text(f"Command: python3 -m unittest\nExit: {code}\nWhen: now\n---\noutput\n")
    (repo / ".swd" / "project.md").write_text("# Project notes\n\n## Commands\nTest command: `python3 -m unittest`\n")
    (run / "reports" / "T1-generalist-engineer.md").write_text(BUILDER_REPORT)
    if not single:
        (run / "reports" / "T2-backend-engineer.md").write_text(BUILDER_REPORT)
    (run / "reports" / "final-qa-engineer.md").write_text(CHECKER_REPORT)
    git(repo, "init", "-q")
    # History from before this run, including an old run's task commit, must be ignored.
    commit(repo, "T9: task from an earlier run", ["old/x.py"])
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (run / "decisions.md").write_text(
        f"Base commit: {base}\nBase branch: main\nBranch: swd/demo\nWorktree: {repo}\nHousekeeping: removed 0, kept 0\nFinish: branch\nPlan judged: the outcome meets the criteria.\n\n- None.\n")
    (run / "staffing.md").write_text(STAFFING)
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

    # --- recorded evidence -------------------------------------------------------------------

    def test_a_task_needs_a_recorded_failing_run_before_its_passing_one(self):
        repo, run = make_run(self.tmp)
        (run / "evidence" / "T1-001.txt").unlink()          # only the passing run is left
        self.assertProblem(self.problems(repo, run), "T1", "failing", "swd-test.py")

    def test_a_tasks_last_recorded_run_must_pass(self):
        repo, run = make_run(self.tmp)
        (run / "evidence" / "T2-003.txt").write_text("Command: x\nExit: 1\nWhen: now\n---\nboom\n")
        self.assertProblem(self.problems(repo, run), "T2", "last recorded run")

    def test_the_whole_suite_must_be_recorded_passing_at_the_end(self):
        repo, run = make_run(self.tmp)
        (run / "evidence" / "final-001.txt").unlink()
        self.assertProblem(self.problems(repo, run), "final", "swd-test.py")
        (run / "evidence" / "final-001.txt").write_text("Command: x\nExit: 1\nWhen: now\n---\nboom\n")
        self.assertProblem(self.problems(repo, run), "final", "did not pass")

    def test_production_records_the_suite_between_waves(self):
        repo, run = make_run(self.tmp)
        (run / "evidence" / "wave-1-001.txt").unlink()
        self.assertProblem(self.problems(repo, run), "wave-1", "swd-test.py")
        with tempfile.TemporaryDirectory() as tmp:           # a prototype runs the suite once, at the end
            repo, run = make_run(tmp, mode="prototype")
            self.assertEqual(self.problems(repo, run), [])

    # --- quick mode, project notes, findings backlog ------------------------------------------

    def quick_run(self):
        """A one-task run in quick mode: one builder, one final review that also does QA's job."""
        repo, run = make_run(self.tmp, mode="prototype", single=True)
        replace(run / "spec.md", "Mode: prototype", "Mode: quick")
        (run / "reports" / "final-qa-engineer.md").unlink()
        return repo, run

    def test_quick_run_needs_only_its_builder_and_one_review(self):
        repo, run = self.quick_run()
        self.assertEqual(self.problems(repo, run), [])
        (run / "reports" / "final-code-reviewer.md").unlink()
        self.assertProblem(self.problems(repo, run), "missing", "final-code-reviewer.md")

    def test_quick_mode_is_for_one_task(self):
        repo, run = make_run(self.tmp)
        replace(run / "spec.md", "Mode: production", "Mode: quick")
        self.assertProblem(self.cr.check_plan(run), "quick", "one task")

    def test_plan_check_requires_project_notes(self):
        repo, run = make_run(self.tmp)
        (repo / ".swd" / "project.md").unlink()
        self.assertProblem(self.cr.check_plan(run), "project.md")

    def test_findings_must_reach_the_project_backlog(self):
        repo, run = make_run(self.tmp)
        with open(run / "decisions.md", "a") as f:
            f.write("Finding: shop/cart.py apply_discount subtracts the percent as an amount. Left: out of scope.\n")
        self.assertProblem(self.problems(repo, run), "findings.md", "swd-findings.py")
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "swd-findings.py"), str(run)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.problems(repo, run), [])

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

    # --- outcome, judgement and staffing ------------------------------------------------------

    def test_plan_needs_an_outcome_section(self):
        for new in ("", "## Outcome\nTODO\n\n", "## Outcome\n\n"):
            with self.subTest(section=new), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                replace(run / "plan.md", "## Outcome\n$ python3 -m unittest\nOK\n\n", new)
                self.assertProblem(self.cr.check_plan(run), "## Outcome", "really appear")

    def test_outcome_is_judged_only_up_to_the_first_task_heading(self):
        # No '## Tasks' heading (the quick-mode plan): the task text must not count as the outcome.
        outcome = "## Outcome\n$ python3 -m unittest\nOK\n\n## Tasks\n\n"
        for new in ("## Outcome\n\n", "## Outcome\nTODO\n\n"):
            with self.subTest(section=new), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                replace(run / "plan.md", outcome, new)
                self.assertProblem(self.cr.check_plan(run), "## Outcome", "really appear")
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", outcome, "## Outcome\n$ python3 -m unittest\nOK\n\n")
        self.assertEqual(self.cr.check_plan(run), [])

    def test_seal_help_says_it_checks_judgement_and_staffing(self):
        self.assertIn("staffing.md", self.cr.__doc__.split("--seal", 1)[1].splitlines()[0])
        self.assertIn("staffing", self.cli("--help").stdout)

    def test_plan_judged_needs_a_real_value(self):
        for line in ("Plan judged:  \n", "Plan judged: TODO\n", "Plan judged: tbd\n"):
            with self.subTest(line=line), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                replace(run / "decisions.md", "Plan judged: the outcome meets the criteria.\n", line)
                self.assertProblem(self.cr.check_staffing(run), "Plan judged")

    def test_a_judgement_before_the_last_seal_is_stale(self):
        repo, run = make_run(self.tmp)
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        replace(run / "plan.md", "First thing", "First thing, amended")
        refused = self.cli("--seal", str(run))
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout.splitlines(), [
            "decisions.md: the 'Plan judged:' line is older than the last 'Plan checksum:'; "
            "judge the amended plan and add a new 'Plan judged: ...' line"])
        self.assertEqual((run / "decisions.md").read_text().count("Plan checksum: "), 1)
        with open(run / "decisions.md", "a") as f:
            f.write("Plan judged: the amended plan still meets the criteria.\n")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        self.assertEqual((run / "decisions.md").read_text().count("Plan checksum: "), 2)

    def test_seal_is_readable_when_decisions_has_no_trailing_newline(self):
        repo, run = make_run(self.tmp)
        decisions = run / "decisions.md"
        decisions.write_text(decisions.read_text().rstrip("\n"))
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        self.assertEqual(len(self.cr.SEAL_RE.findall(decisions.read_text())), 1)
        self.assertEqual(self.cr.check_seal(run), [])
        # The re-seal: a new judgement appended without a newline.
        replace(run / "plan.md", "First thing", "First thing, amended")
        with open(decisions, "a") as f:
            f.write("Plan judged: the amended plan still meets the criteria.")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        self.assertEqual(len(self.cr.SEAL_RE.findall(decisions.read_text())), 2)
        self.assertEqual(self.cr.check_seal(run), [])

    def test_task_needs_an_outcome_line(self):
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "- Outcome: b.py exists\n", "")
        self.assertEqual(self.cr.check_plan(run), ["plan.md: T2 is missing '- Outcome:'"])

    def test_cli_plan_reports_both_outcome_problems_and_passes_when_present(self):
        repo, run = make_run(self.tmp)
        good = (run / "plan.md").read_text()
        replace(run / "plan.md", "## Outcome\n$ python3 -m unittest\nOK\n\n", "")
        replace(run / "plan.md", "- Outcome: b.py exists\n", "")
        bad = self.cli("--plan", str(run))
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(bad.stdout.splitlines(), [
            "plan.md: needs a '## Outcome' section showing the finished result as it will really appear",
            "plan.md: T2 is missing '- Outcome:'"])
        (run / "plan.md").write_text(good)
        ok = self.cli("--plan", str(run))
        self.assertEqual((ok.returncode, ok.stdout), (0, ""))

    def test_seal_needs_plan_judged_and_staffing(self):
        repo, run = make_run(self.tmp)
        replace(run / "decisions.md", "Plan judged: the outcome meets the criteria.\n", "")
        (run / "staffing.md").unlink()
        refused = self.cli("--seal", str(run))
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout.splitlines(), [
            "decisions.md: needs a line 'Plan judged: ...'; the principal judges the plan against the spec before the gate",
            "missing staffing.md: the agent, model and effort for each task"])
        self.assertNotIn("Plan checksum: ", (run / "decisions.md").read_text())

    def test_staffing_rows_are_checked(self):
        cases = [
            ("| T2 | backend-engineer | opus | low | Specified |\n", "", ["staffing.md: no row for T2"]),
            ("| T1 | generalist-engineer | opus | medium |", "| T1 | generalist-engineer | opus | max |",
             ["staffing.md line 6: Effort must be one of low, medium, high, xhigh, got 'max'"]),
            ("| opus | low | Runs", "| gpt | low | Runs", ["staffing.md line 9: Model must be one of haiku, sonnet, opus, fable, got 'gpt'"]),
            ("| T1 | generalist-engineer | opus | medium | Multistep |", "| T1 | generalist-engineer | opus | medium |",
             ["staffing.md line 6: expected 5 columns, got 4", "staffing.md: no row for T1"]),
            ("| T2 | backend-engineer |", "| T2 | docs-writer |",
             ["staffing.md: T2 Agent 'docs-writer' is not the plan's Role 'backend-engineer'"]),
        ]
        for old, new, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                text = (run / "staffing.md").read_text()
                assert old in text, old
                (run / "staffing.md").write_text(text.replace(old, new, 1))
                self.assertEqual(self.cr.check_staffing(run), expected)

    # --- required checker rows, the floor, and the staffing seal ------------------------------

    def staffing(self, run, review="opus", final="opus", extra=""):
        rows = ["| T1 | generalist-engineer | sonnet | medium | Multistep |",
                "| T2 | backend-engineer | haiku | low | Mechanical |"]
        if review:
            rows.append(f"| review | code-reviewer, security-reviewer | {review} | medium | Review |")
        if final:
            rows.append(f"| final | qa-engineer | {final} | medium | Runs commands |")
        (run / "staffing.md").write_text(
            "# Staffing\n\n| For | Agent | Model | Effort | Why |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n" + extra)

    def test_seal_requires_the_checkers_rows(self):
        cases = [("production", False, ["staffing.md: no row for review", "staffing.md: no row for final"]),
                 ("prototype", False, ["staffing.md: no row for review", "staffing.md: no row for final"]),
                 ("quick", True, ["staffing.md: no row for final"])]
        for mode, single, expected in cases:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp, mode=mode if mode != "quick" else "prototype", single=single)
                if mode == "quick":
                    replace(run / "spec.md", "Mode: prototype", "Mode: quick")
                self.staffing(run, review=None, final=None)
                if single:
                    replace(run / "staffing.md", "| T2 | backend-engineer | haiku | low | Mechanical |\n", "")
                refused = self.cli("--seal", str(run))
                self.assertEqual((refused.returncode, refused.stdout.splitlines()), (1, expected))
                self.assertNotIn("Plan checksum: ", (run / "decisions.md").read_text())

    def test_a_checker_may_not_rank_below_a_builder(self):
        repo, run = make_run(self.tmp)
        self.staffing(run, review="haiku", final="haiku")
        refused = self.cli("--seal", str(run))
        self.assertEqual((refused.returncode, refused.stdout.splitlines()), (1, [
            "staffing.md line 7: the review row is on haiku, below T1 on sonnet; a checker's model may not rank below any builder's",
            "staffing.md line 8: the final row is on haiku, below T1 on sonnet; a checker's model may not rank below any builder's"]))
        for review, final in (("sonnet", "sonnet"), ("fable", "opus")):
            self.staffing(run, review=review, final=final)
            self.assertEqual(self.cr.check_staffing(run), [])

    def test_a_second_low_review_row_is_still_caught(self):
        repo, run = make_run(self.tmp)
        self.staffing(run, review="opus", extra="| review | code-reviewer | haiku | low | Again |\n")
        self.assertEqual(self.cr.check_staffing(run), [
            "staffing.md line 9: the review row is on haiku, below T1 on sonnet; a checker's model may not rank below any builder's"])

    def test_the_highest_builder_row_counts_even_when_duplicated_low(self):
        repo, run = make_run(self.tmp)
        self.staffing(run, review="sonnet", final="opus", extra="| T1 | generalist-engineer | haiku | low | Again |\n")
        self.assertEqual(self.cr.check_staffing(run), [])

    def test_a_checker_row_with_an_unknown_model_gets_only_the_model_problem(self):
        repo, run = make_run(self.tmp)
        self.staffing(run, review="gpt", final="opus")
        self.assertEqual(self.cr.check_staffing(run), [
            "staffing.md line 7: Model must be one of haiku, sonnet, opus, fable, got 'gpt'"])

    def test_a_staffing_change_after_the_seal_is_reported_until_sealed_again(self):
        repo, run = make_run(self.tmp)
        sealed = self.cli("--seal", str(run))
        self.assertEqual(sealed.returncode, 0, sealed.stdout)
        lines = sealed.stdout.splitlines()
        self.assertEqual([l.split(":")[0] for l in lines], ["sealed plan.md", "sealed staffing.md"])
        tail = (run / "decisions.md").read_text().splitlines()[-2:]
        self.assertEqual([l.split(":")[0] for l in tail], ["Plan checksum", "Staffing checksum"])
        message = "staffing.md: changed since it was sealed; only the principal changes it, and seals the run again"
        replace(run / "staffing.md", "| T1 | generalist-engineer | opus | medium |", "| T1 | generalist-engineer | opus | high |")
        for args in (("--task", "T1", str(run)), (str(run),)):
            changed = self.cli(*args)
            self.assertEqual((changed.returncode, changed.stdout.splitlines()), (1, [message]))
        again = self.cli("--seal", str(run))  # no new 'Plan judged:' line needed: plan.md is unchanged
        self.assertEqual(again.returncode, 0, again.stdout)
        for args in (("--task", "T1", str(run)), (str(run),)):
            self.assertEqual((self.cli(*args).returncode, self.cli(*args).stdout), (0, ""))

    def test_a_deleted_staffing_file_is_reported_after_the_seal(self):
        repo, run = make_run(self.tmp)
        self.cr.seal_plan(run)
        (run / "staffing.md").unlink()
        self.assertProblem(self.cr.check_seal(run), "staffing.md", "changed since it was sealed")

    def test_an_amended_plan_is_still_refused_without_a_new_judgement(self):
        repo, run = make_run(self.tmp)
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        replace(run / "plan.md", "First thing", "First thing, amended")
        replace(run / "staffing.md", "| T1 | generalist-engineer | opus | medium |", "| T1 | generalist-engineer | opus | high |")
        refused = self.cli("--seal", str(run))
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(len(refused.stdout.splitlines()), 1)
        self.assertIn("the 'Plan judged:' line is older than the last 'Plan checksum:'", refused.stdout)

    def test_a_run_sealed_before_the_staffing_checksum_compares_nothing(self):
        repo, run = make_run(self.tmp)
        with open(run / "decisions.md", "a") as f:
            f.write(f"Plan checksum: {self.cr.plan_checksum(run)}\n")
        replace(run / "staffing.md", "| T1 | generalist-engineer | opus | medium |", "| T1 | generalist-engineer | opus | high |")
        self.assertEqual(self.problems(repo, run), [])
        (run / "staffing.md").unlink()
        self.assertEqual(self.problems(repo, run), [])

    def test_a_row_whose_for_cell_is_not_understood_is_reported(self):
        for label in ("Review", "review (security)", "qa", "T1 (fix)", "T9", ""):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.staffing(run, extra=f"| {label} | code-reviewer | haiku | low | Odd |\n")
                self.assertEqual(self.cr.check_staffing(run), [
                    f"staffing.md line 9: For must be a task id, plan, review or final, got '{label}'"])
        repo, run = make_run(self.tmp)
        self.staffing(run, extra="| plan | architect | opus | low | Plans |\n")
        self.assertEqual(self.cr.check_staffing(run), [])

    def test_a_row_that_only_starts_like_a_header_or_a_separator_is_reported(self):
        for label in ("-", "--", "---", ":", ":-:", "- -", "For"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.staffing(run, extra=f"| {label} | code-reviewer | haiku | low | Odd |\n")
                self.assertEqual(self.cr.check_staffing(run), [
                    f"staffing.md line 9: For must be a task id, plan, review or final, got '{label}'"])
        # the builder side: a dash for "as above" on fable over sonnet checkers
        repo, run = make_run(self.tmp)
        self.staffing(run, review="sonnet", final="sonnet", extra="| --- | generalist-engineer | fable | high | T1 again |\n")
        self.assertEqual(self.cr.check_staffing(run), [
            "staffing.md line 9: For must be a task id, plan, review or final, got '---'"])

    def test_a_row_without_a_leading_pipe_is_read_as_a_row(self):
        floor = "; a checker's model may not rank below any builder's"
        cases = [
            ("final review | code-reviewer | haiku | low | x |",
             ["staffing.md line 9: For must be a task id, plan, review or final, got 'final review'"]),
            ("review | code-reviewer, security-reviewer | haiku | low | x",
             ["staffing.md line 9: the review row is on haiku, below T1 on sonnet" + floor]),
            ("T1 | generalist-engineer | fable | high | moved up",
             ["staffing.md line 7: the review row is on opus, below T1 on fable" + floor,
              "staffing.md line 8: the final row is on opus, below T1 on fable" + floor]),
            ("> | review | code-reviewer | haiku | low | x |", ["staffing.md line 9: expected 5 columns, got 6"]),
            ("﻿| review | code-reviewer | haiku | low | x |", ["staffing.md line 9: expected 5 columns, got 6"]),
            ("Use a | b here.", ["staffing.md line 9: expected 5 columns, got 2"]),
        ]
        for row, want in cases:
            with self.subTest(row=row), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.staffing(run, extra=row + "\n")
                self.assertEqual(self.cr.check_staffing(run), want)
                self.assertEqual(self.cli("--seal", str(run)).returncode, 1)
                self.assertNotIn("checksum", (run / "decisions.md").read_text())

    def test_real_headers_separators_and_prose_are_still_skipped(self):
        header, sep = "| For | Agent | Model | Effort | Why |", "|---|---|---|---|---|"
        headers = [header, "|For|Agent|Model|Effort|Why|", "|  For  |  Agent  |  Model  |  Effort  |  Why  |",
                   header + "   ", "|\tFor\t| Agent | Model | Effort | Why |", "   " + header,
                   "| For | Agent | Model | Effort | Reason |"]
        seps = [sep, "| --- | --- | --- | --- | --- |", "|:---|:---:|---:|---|---|", "| :--- | :---: | ---: | --- | --- |",
                "|-----|---------------------|-------|--------|-----|", "|-|-|-|-|-|", "|:-:|:-:|:-:|:-:|:-:|",
                "   " + sep, sep + "  ", "| - - - | --- | --- | --- | --- |", "|---|---|---|---|"]
        rows = STAFFING.split(sep + "\n")[1]
        tables = [(h, sep) for h in headers] + [(header, s) for s in seps]
        repo, run = make_run(self.tmp)
        for h, s in tables:
            with self.subTest(header=h, separator=s):
                (run / "staffing.md").write_text(f"# Staffing\n\n{h}\n{s}\n{rows}")
                self.assertEqual(self.cr.check_staffing(run), [])
        # a title, blank lines, a sentence without a pipe, and a second header and separator further down
        (run / "staffing.md").write_text(
            f"# Staffing\n\nWho runs what, and on which model.\n\n{header}\n{sep}\n{rows}\n\n{header}\n{sep}\n\nRaise effort first.\n")
        self.assertEqual(self.cr.check_staffing(run), [])
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)

    def test_the_documented_staffing_tables_seal(self):
        for path in ("standards/run-folder.md", "skills/build/SKILL.md"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                block = re.search(r"```markdown\n(\s*# Staffing\n.*?)```", (ROOT / path).read_text(), re.S).group(1)
                replace(run / "plan.md", "- Role: backend-engineer", "- Role: docs-writer")
                (run / "staffing.md").write_text(block)
                self.assertEqual(self.cr.check_staffing(run), [])

    def test_a_tie_for_the_top_builder_names_the_first_in_file_order(self):
        repo, run = make_run(self.tmp)
        self.staffing(run, review="sonnet", final="opus")
        replace(run / "staffing.md", "| T1 | generalist-engineer | sonnet", "| T1 | generalist-engineer | opus")
        replace(run / "staffing.md", "| T2 | backend-engineer | haiku", "| T2 | backend-engineer | opus")
        self.assertEqual(self.cr.check_staffing(run), [
            "staffing.md line 7: the review row is on sonnet, below T1 on opus; a checker's model may not rank below any builder's"])

    def test_the_staffing_checksum_follows_on_its_own_line_without_a_trailing_newline(self):
        repo, run = make_run(self.tmp)
        decisions = run / "decisions.md"
        decisions.write_text(decisions.read_text().rstrip("\n"))
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        tail = decisions.read_text().splitlines()[-2:]
        self.assertEqual([l.split(":")[0] for l in tail], ["Plan checksum", "Staffing checksum"])
        self.assertEqual(self.cr.check_seal(run), [])

    def test_a_run_sealed_before_the_staffing_checksum_compares_nothing_for_task(self):
        repo, run = make_run(self.tmp)
        with open(run / "decisions.md", "a") as f:
            f.write(f"Plan checksum: {self.cr.plan_checksum(run)}\n")
        replace(run / "staffing.md", "| T1 | generalist-engineer | opus | medium |", "| T1 | generalist-engineer | opus | high |")
        self.assertEqual(self.cli("--task", "T1", str(run)).stdout, "")

    def test_sealing_and_checking_without_files_do_not_raise(self):
        repo, run = make_run(self.tmp)
        (run / "staffing.md").unlink()
        self.cr.seal_plan(run)
        self.assertNotIn("Staffing checksum", (run / "decisions.md").read_text())
        (run / "plan.md").unlink()
        self.assertProblem(self.cr.check_seal(run), "missing plan.md")
        self.staffing(run)
        (run / "plan.md").write_text(PLAN)
        self.cr.seal_plan(run)
        (run / "plan.md").unlink()
        self.staffing(run, final="fable")
        self.assertEqual(self.cr.check_seal(run), ["missing plan.md",
            "staffing.md: changed since it was sealed; only the principal changes it, and seals the run again"])
        self.cr.check_staffing(run)
        replace(run / "decisions.md", "Plan judged: the outcome meets the criteria.\n", "")
        self.assertProblem(self.cr.check_staffing(run), "Plan judged")

    def test_seal_succeeds_with_judgement_and_full_staffing(self):
        repo, run = make_run(self.tmp)
        self.assertEqual(self.cr.check_staffing(run), [])
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)

    def test_finished_run_without_staffing_still_checks_clean(self):
        repo, run = make_run(self.tmp)
        (run / "staffing.md").unlink()
        self.assertEqual(self.problems(repo, run), [])

    def old_run(self):
        """A run shaped like one that finished under 0.7.1: no outcome, no judgement, no staffing.md."""
        repo, run = make_run(self.tmp)
        plan = (run / "plan.md").read_text()
        plan = plan.replace("## Outcome\n$ python3 -m unittest\nOK\n\n", "")
        plan = plan.replace("- Outcome: a.py exists\n", "").replace("- Outcome: b.py exists\n", "")
        (run / "plan.md").write_text(plan)
        replace(run / "decisions.md", "Plan judged: the outcome meets the criteria.\n", "")
        (run / "staffing.md").unlink()
        self.cr.seal_plan(run)
        return repo, run

    def test_run_from_before_outcome_still_checks_clean(self):
        repo, run = self.old_run()
        self.assertNotIn("Outcome", (run / "plan.md").read_text())
        self.assertEqual(self.problems(repo, run), [])
        done = self.cli(str(run))
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_unsealed_run_without_outcome_is_refused_by_the_finished_run_check(self):
        repo, run = self.old_run()
        replace(run / "decisions.md", f"Plan checksum: {self.cr.plan_checksum(run)}\n", "")
        self.assertEqual(self.problems(repo, run), [
            "plan.md: needs a '## Outcome' section showing the finished result as it will really appear",
            "plan.md: T1 is missing '- Outcome:'",
            "plan.md: T2 is missing '- Outcome:'"])
        self.assertEqual(self.cli(str(run)).returncode, 1)

    def test_plan_still_asks_for_outcome_on_an_old_run(self):
        repo, run = self.old_run()
        plan = self.cli("--plan", str(run))
        self.assertEqual(plan.returncode, 1)
        self.assertEqual(plan.stdout.splitlines(), [
            "plan.md: needs a '## Outcome' section showing the finished result as it will really appear",
            "plan.md: T1 is missing '- Outcome:'",
            "plan.md: T2 is missing '- Outcome:'"])
        before = (run / "decisions.md").read_text()
        seal = self.cli("--seal", str(run))
        self.assertEqual(seal.returncode, 1)
        self.assertEqual((run / "decisions.md").read_text(), before)

    def test_other_plan_rules_still_reach_a_finished_run_without_outcome(self):
        repo, run = self.old_run()
        replace(run / "plan.md", "- Check: `python3 -m unittest tests.test_b`\n", "")
        self.cr.seal_plan(run)
        self.assertEqual(self.problems(repo, run), ["plan.md: T2 is missing '- Check:'"])

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
