"""Tests for scripts/check_run.py. Run from the repo root: python3 -m unittest tests.test_check_run"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
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
        path.write_text(path.read_text(encoding="utf-8") + "x\n" if path.exists() else "x\n", encoding="utf-8")
    git(repo, "add", "-A", "--", *files)
    git(repo, "commit", "-m", subject)


def make_run(tmp, mode="production", single=False):
    """A valid run in a fresh git repo: two tasks in two waves, or just T1 when single. Returns (repo, run)."""
    repo = Path(tmp)
    run = repo / ".swd" / "runs" / "2026-11-12-demo"
    (run / "reports").mkdir(parents=True)
    (run / "requirement.md").write_text("Do the thing.\n", encoding="utf-8")
    (run / "spec.md").write_text(f"# Spec\n\nMode: {mode}\n\n## Acceptance criteria\n- It works.\n", encoding="utf-8")
    (run / "standards.md").write_text("standards\n", encoding="utf-8")
    (run / "plan.md").write_text(PLAN.split("### T2")[0] if single else PLAN, encoding="utf-8")
    (run / "ledger.md").write_text(LEDGER.split("| T2")[0] if single else LEDGER, encoding="utf-8")
    (run / "decisions.md").write_text("None.\n", encoding="utf-8")
    (run / "activity.md").write_text(ACTIVITY.replace("- 10:06:00 dispatch T2 backend-engineer\n", "") if single else ACTIVITY, encoding="utf-8")
    (run / "dashboard.html").write_text("<html></html>\n", encoding="utf-8")
    (run / "write-check.txt").write_text("edited\n", encoding="utf-8")
    # What swd-test.py recorded: each task's check failing and then passing, the suite after
    # wave 1 (production only checks between waves), and the whole suite at the end.
    evidence = {"T1-001": 1, "T1-002": 0, "final-001": 0}
    if not single:
        evidence.update({"T2-001": 1, "T2-002": 0})
        if mode == "production":
            evidence["wave-1-001"] = 0
    (run / "evidence").mkdir()
    for name, code in evidence.items():
        (run / "evidence" / f"{name}.txt").write_text(f"Command: python3 -m unittest\nExit: {code}\nWhen: now\n---\noutput\n", encoding="utf-8")
    (repo / ".swd" / "project.md").write_text("# Project notes\n\n## Commands\nTest command: `python3 -m unittest`\n", encoding="utf-8")
    (run / "reports" / "T1-generalist-engineer.md").write_text(BUILDER_REPORT, encoding="utf-8")
    if not single:
        (run / "reports" / "T2-backend-engineer.md").write_text(BUILDER_REPORT, encoding="utf-8")
    (run / "reports" / "final-qa-engineer.md").write_text(CHECKER_REPORT, encoding="utf-8")
    git(repo, "init", "-q")
    # History from before this run, including an old run's task commit, must be ignored.
    commit(repo, "T9: task from an earlier run", ["old/x.py"])
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8").stdout.strip()
    (run / "decisions.md").write_text(
        f"Base commit: {base}\nBase branch: main\nBranch: swd/demo\nWorktree: {repo}\nConductor: Fable 5.2\nHousekeeping: removed 0, kept 0\nFinish: branch\nPlan judged: the outcome meets the criteria.\n\n- None.\n", encoding="utf-8")
    (run / "staffing.md").write_text(STAFFING, encoding="utf-8")
    if mode == "production":
        names = ["T1-code-reviewer", "T1-security-reviewer"]
        if not single:  # a one-task run needs no final reviews: the task's own reviews covered the whole change
            names += ["T2-code-reviewer", "T2-security-reviewer", "final-code-reviewer", "final-security-reviewer"]
        for name in names:
            (run / "reports" / f"{name}.md").write_text(CHECKER_REPORT, encoding="utf-8")
        commit(repo, "T1: First thing", ["a.py", "tests/test_a.py"])
        if not single:
            commit(repo, "T2: Second thing", ["b.py"])
    else:
        (run / "reports" / "final-code-reviewer.md").write_text(CHECKER_REPORT, encoding="utf-8")
        commit(repo, "W1: first wave", ["a.py", "tests/test_a.py"])
        if not single:
            commit(repo, "W2: second wave", ["b.py"])
    return repo, run


def replace(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path}"
    path.write_text(text.replace(old, new), encoding="utf-8")


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
        (run / "plan.md").write_text(PLAN.split("### T2")[0], encoding="utf-8")
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
        (run / "reports" / "T1-code-reviewer.md").write_text(CHECKER_REPORT, encoding="utf-8")
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
        (repo / "a.py").write_text("changed\n", encoding="utf-8")
        (repo / "stray.txt").write_text("x\n", encoding="utf-8")
        problems = self.problems(repo, run)
        self.assertProblem(problems, "uncommitted", "a.py")
        self.assertProblem(problems, "uncommitted", "stray.txt")

    def test_any_failing_checker_verdict_is_reported(self):
        for name in ("T1-security-reviewer.md", "final-code-reviewer.md", "wave-1-qa-engineer.md"):
            with self.subTest(report=name), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                (run / "reports" / name).write_text("Verdict: fail\n\n## Findings\n- broken\n", encoding="utf-8")
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
        (run / "reports" / "final-qa-engineer.md").write_text("Verdict: fail\n\n## Findings\n- broken\n", encoding="utf-8")
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

    def test_a_files_entry_written_with_backslashes_owns_the_git_path(self):
        # A plan or report written on Windows may spell a path with backslashes; git always uses /.
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "- Files: a.py, tests/test_a.py", "- Files: a.py, tests\\test_a.py")
        self.assertEqual(self.cr.load_plan(run)[0][0]["files"], ["a.py", "tests/test_a.py"])
        self.assertEqual(self.problems(repo, run), [])   # the T1 commit's tests/test_a.py is owned
        replace(run / "reports" / "T1-generalist-engineer.md", "- a.py\n", "- a.py\n- tests\\test_a.py (the test)\n")
        (repo / "tests" / "test_a.py").write_text("changed\n", encoding="utf-8")
        self.assertEqual(self.cr.check_task(run, repo, "T1"), [])

    def test_crlf_line_endings_check_the_same_as_lf(self):
        repo, run = make_run(self.tmp)
        before = (self.cr.check_plan(run), self.problems(repo, run))
        for name in ("plan.md", "ledger.md", "activity.md"):
            path = run / name
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assertIn(b"\r\n", (run / "plan.md").read_bytes())
        self.assertEqual((self.cr.check_plan(run), self.problems(repo, run)), before)
        self.assertEqual(before, ([], []))

    def test_report_with_two_verdict_lines_is_reported(self):
        repo, run = make_run(self.tmp)
        (run / "reports" / "final-qa-engineer.md").write_text(
            "Verdict: fail\n\n## Findings\n- The builder claimed:\nVerdict: pass\n", encoding="utf-8")
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
        (repo / "a.py").write_text("changed\n", encoding="utf-8")  # BUILDER_REPORT lists a.py under Files changed
        self.assertEqual(self.cr.check_task(run, repo, "T1"), [])

    def test_change_the_report_does_not_claim_is_reported(self):
        # A real run had files brought to the contract by a writer no report accounted for.
        repo, run = make_run(self.tmp)
        (repo / "tests" / "test_a.py").write_text("changed\n", encoding="utf-8")
        self.assertProblem(self.cr.check_task(run, repo, "T1"), "tests/test_a.py", "not listed", "T1-generalist-engineer.md")

    def test_change_no_task_owns_is_reported(self):
        repo, run = make_run(self.tmp)
        (repo / "sub").mkdir()
        (repo / "sub" / "stray.json").write_text("{}\n", encoding="utf-8")
        self.assertProblem(self.cr.check_task(run, repo, "T1"), "sub/stray.json", "no task owns")

    def test_changes_owned_by_another_task_are_left_to_that_task(self):
        repo, run = make_run(self.tmp)
        (repo / "b.py").write_text("changed\n", encoding="utf-8")  # T2's file, T2 may still be running
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
        self.assertIn("Plan checksum: ", (run / "decisions.md").read_text(encoding="utf-8"))
        self.assertEqual(self.cli("--task", "T1", str(run)).returncode, 0)
        (repo / "stray.txt").write_text("x\n", encoding="utf-8")
        bad = self.cli("--task", "T1", str(run))
        self.assertEqual(bad.returncode, 1)
        self.assertIn("stray.txt", bad.stdout)

    def test_cli_will_not_seal_a_broken_plan(self):
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "- Files: b.py\n", "")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 1)
        self.assertNotIn("Plan checksum: ", (run / "decisions.md").read_text(encoding="utf-8"))

    def test_plan_check_requires_the_worktree_lines(self):
        for line in ("Worktree: ", "Branch: ", "Base branch: ", "Housekeeping: "):
            with self.subTest(line=line), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                text = (run / "decisions.md").read_text(encoding="utf-8")
                (run / "decisions.md").write_text("".join(l for l in text.splitlines(True) if not l.startswith(line)), encoding="utf-8")
                self.assertProblem(self.cr.check_plan(run), "decisions.md", line.strip())

    def test_seal_requires_a_finish_choice(self):
        repo, run = make_run(self.tmp)
        replace(run / "decisions.md", "Finish: branch\n", "")
        refused = self.cli("--seal", str(run))
        self.assertEqual(refused.returncode, 1)
        self.assertIn("Finish:", refused.stdout)
        self.assertNotIn("Plan checksum: ", (run / "decisions.md").read_text(encoding="utf-8"))
        with open(run / "decisions.md", "a", encoding="utf-8") as f:
            f.write("Finish: sometime\n")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 1)

    def test_git_checks_run_in_the_worktree_not_the_users_copy(self):
        repo, run = make_run(self.tmp)
        with tempfile.TemporaryDirectory() as elsewhere:
            work = Path(elsewhere) / "work"
            subprocess.run(["git", "clone", "-q", str(repo), str(work)], check=True, capture_output=True)
            replace(run / "decisions.md", f"Worktree: {repo}", f"Worktree: {work}")
            (repo / "notes.txt").write_text("the user's own uncommitted work\n", encoding="utf-8")
            self.assertEqual(self.cli(str(run)).stdout, "")
            (work / "stray.txt").write_text("x\n", encoding="utf-8")
            self.assertIn("stray.txt", self.cli(str(run)).stdout)

    # --- recorded evidence -------------------------------------------------------------------

    def test_a_task_needs_a_recorded_failing_run_before_its_passing_one(self):
        repo, run = make_run(self.tmp)
        (run / "evidence" / "T1-001.txt").unlink()          # only the passing run is left
        self.assertProblem(self.problems(repo, run), "T1", "failing", "swd-test.py")

    def test_a_tasks_last_recorded_run_must_pass(self):
        repo, run = make_run(self.tmp)
        (run / "evidence" / "T2-003.txt").write_text("Command: x\nExit: 1\nWhen: now\n---\nboom\n", encoding="utf-8")
        self.assertProblem(self.problems(repo, run), "T2", "last recorded run")

    def test_the_whole_suite_must_be_recorded_passing_at_the_end(self):
        repo, run = make_run(self.tmp)
        (run / "evidence" / "final-001.txt").unlink()
        self.assertProblem(self.problems(repo, run), "final", "swd-test.py")
        (run / "evidence" / "final-001.txt").write_text("Command: x\nExit: 1\nWhen: now\n---\nboom\n", encoding="utf-8")
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
        with open(run / "decisions.md", "a", encoding="utf-8") as f:
            f.write("Finding: shop/cart.py apply_discount subtracts the percent as an amount. Left: out of scope.\n")
        self.assertProblem(self.problems(repo, run), "findings.md", "swd-findings.py")
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "swd-findings.py"), str(run)],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.problems(repo, run), [])

    def test_plan_check_requires_the_write_check(self):
        # A pilot showed the principal skipping the write check in prototype mode.
        for content in (None, "written\n"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                (run / "write-check.txt").unlink()
                if content:
                    (run / "write-check.txt").write_text(content, encoding="utf-8")
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
        self.assertEqual((run / "decisions.md").read_text(encoding="utf-8").count("Plan checksum: "), 1)
        with open(run / "decisions.md", "a", encoding="utf-8") as f:
            f.write("Plan judged: the amended plan still meets the criteria.\n")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        self.assertEqual((run / "decisions.md").read_text(encoding="utf-8").count("Plan checksum: "), 2)

    def test_seal_is_readable_when_decisions_has_no_trailing_newline(self):
        repo, run = make_run(self.tmp)
        decisions = run / "decisions.md"
        decisions.write_text(decisions.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        self.assertEqual(len(self.cr.SEAL_RE.findall(decisions.read_text(encoding="utf-8"))), 1)
        self.assertEqual(self.cr.check_seal(run), [])
        # The re-seal: a new judgement appended without a newline.
        replace(run / "plan.md", "First thing", "First thing, amended")
        with open(decisions, "a", encoding="utf-8") as f:
            f.write("Plan judged: the amended plan still meets the criteria.")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        self.assertEqual(len(self.cr.SEAL_RE.findall(decisions.read_text(encoding="utf-8"))), 2)
        self.assertEqual(self.cr.check_seal(run), [])

    def test_task_needs_an_outcome_line(self):
        repo, run = make_run(self.tmp)
        replace(run / "plan.md", "- Outcome: b.py exists\n", "")
        self.assertEqual(self.cr.check_plan(run), ["plan.md: T2 is missing '- Outcome:'"])

    def test_cli_plan_reports_both_outcome_problems_and_passes_when_present(self):
        repo, run = make_run(self.tmp)
        good = (run / "plan.md").read_text(encoding="utf-8")
        replace(run / "plan.md", "## Outcome\n$ python3 -m unittest\nOK\n\n", "")
        replace(run / "plan.md", "- Outcome: b.py exists\n", "")
        bad = self.cli("--plan", str(run))
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(bad.stdout.splitlines(), [
            "plan.md: needs a '## Outcome' section showing the finished result as it will really appear",
            "plan.md: T2 is missing '- Outcome:'"])
        (run / "plan.md").write_text(good, encoding="utf-8")
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
        self.assertNotIn("Plan checksum: ", (run / "decisions.md").read_text(encoding="utf-8"))

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
                text = (run / "staffing.md").read_text(encoding="utf-8")
                assert old in text, old
                (run / "staffing.md").write_text(text.replace(old, new, 1), encoding="utf-8")
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
            "# Staffing\n\n| For | Agent | Model | Effort | Why |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n" + extra, encoding="utf-8")

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
                self.assertNotIn("Plan checksum: ", (run / "decisions.md").read_text(encoding="utf-8"))

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
        tail = (run / "decisions.md").read_text(encoding="utf-8").splitlines()[-2:]
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
        with open(run / "decisions.md", "a", encoding="utf-8") as f:
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
                self.assertNotIn("checksum", (run / "decisions.md").read_text(encoding="utf-8"))

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
                (run / "staffing.md").write_text(f"# Staffing\n\n{h}\n{s}\n{rows}", encoding="utf-8")
                self.assertEqual(self.cr.check_staffing(run), [])
        # a title, blank lines, a sentence without a pipe, and a second header and separator further down
        (run / "staffing.md").write_text(
            f"# Staffing\n\nWho runs what, and on which model.\n\n{header}\n{sep}\n{rows}\n\n{header}\n{sep}\n\nRaise effort first.\n", encoding="utf-8")
        self.assertEqual(self.cr.check_staffing(run), [])
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)

    def test_the_documented_staffing_tables_seal(self):
        for path in ("standards/run-folder.md", "skills/build/SKILL.md"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                block = re.search(r"```markdown\n(\s*# Staffing\n.*?)```", (ROOT / path).read_text(encoding="utf-8"), re.S).group(1)
                replace(run / "plan.md", "- Role: backend-engineer", "- Role: docs-writer")
                (run / "staffing.md").write_text(block, encoding="utf-8")
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
        decisions.write_text(decisions.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        tail = decisions.read_text(encoding="utf-8").splitlines()[-2:]
        self.assertEqual([l.split(":")[0] for l in tail], ["Plan checksum", "Staffing checksum"])
        self.assertEqual(self.cr.check_seal(run), [])

    def test_a_run_sealed_before_the_staffing_checksum_compares_nothing_for_task(self):
        repo, run = make_run(self.tmp)
        with open(run / "decisions.md", "a", encoding="utf-8") as f:
            f.write(f"Plan checksum: {self.cr.plan_checksum(run)}\n")
        replace(run / "staffing.md", "| T1 | generalist-engineer | opus | medium |", "| T1 | generalist-engineer | opus | high |")
        self.assertEqual(self.cli("--task", "T1", str(run)).stdout, "")

    def test_sealing_and_checking_without_files_do_not_raise(self):
        repo, run = make_run(self.tmp)
        (run / "staffing.md").unlink()
        self.cr.seal_plan(run)
        self.assertNotIn("Staffing checksum", (run / "decisions.md").read_text(encoding="utf-8"))
        (run / "plan.md").unlink()
        self.assertProblem(self.cr.check_seal(run), "missing plan.md")
        self.staffing(run)
        (run / "plan.md").write_text(PLAN, encoding="utf-8")
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
        plan = (run / "plan.md").read_text(encoding="utf-8")
        plan = plan.replace("## Outcome\n$ python3 -m unittest\nOK\n\n", "")
        plan = plan.replace("- Outcome: a.py exists\n", "").replace("- Outcome: b.py exists\n", "")
        (run / "plan.md").write_text(plan, encoding="utf-8")
        replace(run / "decisions.md", "Plan judged: the outcome meets the criteria.\n", "")
        (run / "staffing.md").unlink()
        self.cr.seal_plan(run)
        return repo, run

    def test_run_from_before_outcome_still_checks_clean(self):
        repo, run = self.old_run()
        self.assertNotIn("Outcome", (run / "plan.md").read_text(encoding="utf-8"))
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
        before = (run / "decisions.md").read_text(encoding="utf-8")
        seal = self.cli("--seal", str(run))
        self.assertEqual(seal.returncode, 1)
        self.assertEqual((run / "decisions.md").read_text(encoding="utf-8"), before)

    def test_other_plan_rules_still_reach_a_finished_run_without_outcome(self):
        repo, run = self.old_run()
        replace(run / "plan.md", "- Check: `python3 -m unittest tests.test_b`\n", "")
        self.cr.seal_plan(run)
        self.assertEqual(self.problems(repo, run), ["plan.md: T2 is missing '- Check:'"])

    # --- the conductor and the Fable judge (0.10.0) --------------------------------------------

    CONDUCTOR = ("decisions.md: needs a line 'Conductor: Fable 5.2' or 'Conductor: Opus 5.5'; "
                 "the principal records the model it conducts on")

    def judge_message(self, value="Opus 5.5"):
        return (f"decisions.md: the conductor is on {value}, so the plan needs the Fable judge: "
                "a 'Judge plan: ...' line, or 'Judge unreachable: ...', below the last 'Plan checksum:' line")

    def append(self, run, text):
        with open(run / "decisions.md", "a", encoding="utf-8") as f:
            f.write(text)

    def on_opus(self, run):
        replace(run / "decisions.md", "Conductor: Fable 5.2\n", "Conductor: Opus 5.5\n")

    def seals(self, run):
        return len(self.cr.SEAL_RE.findall((run / "decisions.md").read_text(encoding="utf-8")))

    def test_plan_needs_a_real_conductor_line(self):
        lines = {"missing": "", "empty": "Conductor: \n", "spaces": "Conductor:    \n",
                 "placeholder": "Conductor: TODO\n", "another model": "Conductor: Sonnet 5.5\n",
                 "lower case": "Conductor: opus 5.5\n"}
        for name, line in lines.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                replace(run / "decisions.md", "Conductor: Fable 5.2\n", line)
                plan = self.cli("--plan", str(run))
                self.assertEqual((plan.returncode, plan.stdout.splitlines()), (1, [self.CONDUCTOR]))
                self.assertEqual(self.cr.check_conductor(run), [self.CONDUCTOR])

    def test_plan_accepts_either_conductor(self):
        repo, run = make_run(self.tmp)
        for value in ("Fable 5.2", "Opus 5.5"):
            with self.subTest(value):
                (run / "decisions.md").write_text(
                    re.sub(r"(?m)^Conductor: .*$", f"Conductor: {value}  ", (run / "decisions.md").read_text(encoding="utf-8")),
                    encoding="utf-8")
                self.assertEqual(self.cr.check_conductor(run), [])
                plan = self.cli("--plan", str(run))
                self.assertEqual((plan.returncode, plan.stdout), (0, ""))

    def test_the_last_conductor_line_counts(self):
        repo, run = make_run(self.tmp)
        self.append(run, "Conductor: Sonnet 5.5\n")
        self.assertEqual(self.cli("--plan", str(run)).stdout.splitlines(), [self.CONDUCTOR])
        self.append(run, "Conductor: Opus 5.5\n")
        self.assertEqual(self.cli("--plan", str(run)).stdout, "")
        self.assertEqual(self.cr.check_judge(run), [self.judge_message()])
        self.append(run, "Conductor: Fable 5.2\n")
        self.assertEqual(self.cr.check_judge(run), [])

    def test_seal_on_opus_needs_the_judge(self):
        repo, run = make_run(self.tmp)
        self.on_opus(run)
        refused = self.cli("--seal", str(run))
        self.assertEqual((refused.returncode, refused.stdout.splitlines()), (1, [self.judge_message()]))
        self.assertEqual(self.seals(run), 0)

    def test_seal_on_opus_with_a_judge_line(self):
        for line in ("Judge plan: the plan holds (reports/judge-1.md)\n",
                     "Judge unreachable: Agent terminated early due to an API error\n"):
            with self.subTest(line), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.on_opus(run)
                self.append(run, line)
                sealed = self.cli("--seal", str(run))
                self.assertEqual(sealed.returncode, 0, sealed.stdout)
                self.assertEqual([l.split(":")[0] for l in sealed.stdout.splitlines()], ["sealed plan.md", "sealed staffing.md"])
                self.assertEqual(self.seals(run), 1)

    def test_a_placeholder_judge_line_does_not_count(self):
        for line in ("Judge plan: TODO\n", "Judge plan:\n", "Judge unreachable:   \n", "Judge unreachable: n/a\n",
                     "Judge ruling: the ruling holds (reports/judge-1.md)\n",
                     "Judge overruled: reports/judge-1.md, because the spec says so\n"):
            with self.subTest(line), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.on_opus(run)
                self.append(run, line)
                refused = self.cli("--seal", str(run))
                self.assertEqual((refused.returncode, refused.stdout.splitlines()), (1, [self.judge_message()]))
                self.assertEqual(self.seals(run), 0)

    def test_a_judge_or_seal_line_hidden_inside_another_line_does_not_count(self):
        # str.splitlines() also breaks at these; decision() and Markdown viewers break only at \n.
        for sep in ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " "):
            for hidden in ("Judge plan: the plan holds (reports/judge-1.md)", "Judge unreachable: quota"):
                with self.subTest(sep=repr(sep), hidden=hidden), tempfile.TemporaryDirectory() as tmp:
                    repo, run = make_run(tmp)
                    self.on_opus(run)
                    self.append(run, f"- Ruling: kept the plan.{sep}{hidden}\n")
                    refused = self.cli("--seal", str(run))
                    self.assertEqual((refused.returncode, refused.stdout.splitlines()), (1, [self.judge_message()]))
                    self.assertEqual(self.seals(run), 0)
            with self.subTest(sep=repr(sep), hidden="Plan checksum:"), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.on_opus(run)
                self.append(run, f"- note{sep}Plan checksum: {self.cr.plan_checksum(run, missing='')}\n")
                self.assertEqual(self.cr.check_judge(run), [self.judge_message()])

    def test_a_judge_line_before_the_last_seal_does_not_cover_an_amended_plan(self):
        repo, run = make_run(self.tmp)
        self.on_opus(run)
        self.append(run, "Judge plan: the plan holds (reports/judge-1.md)\n")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        replace(run / "plan.md", "First thing", "First thing, amended")
        self.append(run, "Plan judged: the amended plan still meets the criteria.\n")
        refused = self.cli("--seal", str(run))
        self.assertEqual((refused.returncode, refused.stdout.splitlines()), (1, [self.judge_message()]))
        self.assertEqual(self.seals(run), 1)
        self.append(run, "Judge unreachable: This agent switched to claude-opus-5-5\n")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        self.assertEqual(self.seals(run), 2)

    def test_a_staffing_change_alone_reseals_on_opus_without_a_new_judge_line(self):
        repo, run = make_run(self.tmp)
        self.on_opus(run)
        self.append(run, "Judge plan: the plan holds (reports/judge-1.md)\n")
        self.assertEqual(self.cli("--seal", str(run)).returncode, 0)
        replace(run / "staffing.md", "| T1 | generalist-engineer | opus | medium |", "| T1 | generalist-engineer | opus | high |")
        again = self.cli("--seal", str(run))
        self.assertEqual(again.returncode, 0, again.stdout)
        self.assertEqual(self.seals(run), 2)

    def test_fable_seals_without_a_judge_line(self):
        repo, run = make_run(self.tmp)
        self.assertEqual(self.cr.check_judge(run), [])
        sealed = self.cli("--seal", str(run))
        self.assertEqual(sealed.returncode, 0, sealed.stdout)
        self.assertNotIn("Judge", (run / "decisions.md").read_text(encoding="utf-8"))

    def test_seal_reports_a_missing_conductor_and_an_unknown_one(self):
        repo, run = make_run(self.tmp)
        replace(run / "decisions.md", "Conductor: Fable 5.2\n", "")
        refused = self.cli("--seal", str(run))
        self.assertEqual((refused.returncode, refused.stdout.splitlines()), (1, [self.CONDUCTOR]))
        self.append(run, "Conductor: Sonnet 5.5\n")
        refused = self.cli("--seal", str(run))
        self.assertEqual((refused.returncode, refused.stdout.splitlines()), (1, [self.CONDUCTOR, self.judge_message("Sonnet 5.5")]))
        self.assertEqual(self.seals(run), 0)

    def test_a_run_sealed_before_the_conductor_line_still_checks_clean(self):
        repo, run = make_run(self.tmp)
        replace(run / "decisions.md", "Conductor: Fable 5.2\n", "")
        self.cr.seal_plan(run)
        for args in ((str(run),), ("--task", "T1", str(run))):
            done = self.cli(*args)
            self.assertEqual((done.returncode, done.stdout), (0, ""))
        self.assertEqual(self.problems(repo, run), [])
        self.assertEqual(self.cr.check_judge(run), [])

    def test_plan_and_seal_help_name_the_conductor_and_the_judge(self):
        doc = self.cr.__doc__
        self.assertIn("Conductor:", doc.split("--plan", 1)[1].splitlines()[0])
        self.assertIn("judge", doc.split("--seal", 1)[1].splitlines()[0])
        help_text = " ".join(self.cli("--help").stdout.split())
        self.assertIn("Conductor line", help_text)
        self.assertIn("the Fable judge", help_text)

    # --- a run /swd:queue started: SWD_UNATTENDED=<model> (0.11.0, contract C4) -----------------

    UNATTENDED = ("decisions.md: this run was started by /swd:queue and the conductor is on Opus 5.5, so the plan needs "
                  "the Fable judge's verdict: the last 'Judge plan:' or 'Judge unreachable:' line below the last "
                  "'Plan checksum:' line must be 'Judge plan: ...'; 'Judge unreachable:' is not enough, "
                  "and the run stops as blocked")
    NOT_HOLDING = ("decisions.md: this run was started by /swd:queue and the conductor is on Opus 5.5, so the plan needs "
                   "the Fable judge's verdict that it holds: the last 'Judge plan:' line below the last 'Plan checksum:' "
                   "line does not say 'the plan holds', and the conductor of such a run does not overrule it; "
                   "the plan goes back to the architect")
    UNSEALED = ("decisions.md: this run was started by /swd:queue and has no 'Plan checksum:' line: its plan was never "
                "sealed, so no builder may work on it, and the run stops as blocked")

    def assertSealRefused(self, run, unattended, *lines):
        before = self.seals(run)
        refused = self.cli("--seal", str(run), unattended=unattended)
        self.assertEqual((refused.returncode, refused.stdout.splitlines()), (1, list(lines)))
        self.assertEqual(self.seals(run), before)

    def assertSeals(self, run, unattended=None):
        before = self.seals(run)
        sealed = self.cli("--seal", str(run), unattended=unattended)
        self.assertEqual(sealed.returncode, 0, sealed.stdout)
        self.assertEqual([l.split(":")[0] for l in sealed.stdout.splitlines()], ["sealed plan.md", "sealed staffing.md"])
        self.assertEqual(self.seals(run), before + 1)

    def test_unattended_seal_on_opus_refuses_judge_unreachable(self):
        repo, run = make_run(self.tmp)
        self.on_opus(run)
        self.append(run, "Judge unreachable: Agent terminated early due to an API error\n")
        self.assertSealRefused(run, "opus", self.UNATTENDED)
        self.assertSeals(run)   # the same run, started by hand, seals as in 0.10.0

    def test_unattended_seal_on_opus_with_no_judge_line_gives_only_the_unattended_line(self):
        repo, run = make_run(self.tmp)
        self.on_opus(run)
        self.assertSealRefused(run, "opus", self.UNATTENDED)

    def test_unattended_the_last_judge_line_since_the_seal_must_be_the_verdict(self):
        # The judge's verdict on an earlier version of the plan does not cover one it could not be reached for.
        refused = {"verdict, plan amended, then unreachable": ("Judge plan: the plan holds (reports/judge-1.md)\n", True,
                                                               "Judge unreachable: quota\n"),
                   "verdict, then unreachable": ("Judge plan: the plan holds (reports/judge-1.md)\n", False,
                                                 "Judge unreachable: quota\n")}
        # Unattended, every unreachable line counts, whatever its value: a re-dispatch that returned nothing, written
        # down as an empty or placeholder value, must not leave the old verdict in force. Attended, it is skipped.
        for then in ("Judge unreachable:\n", "Judge unreachable:   \n", "Judge unreachable: none\n", "Judge unreachable: -\n",
                     "Judge unreachable: n/a\n", "Judge unreachable: TBD\n"):
            for amend in (True, False):
                refused[f"verdict, {'plan amended, ' if amend else ''}then {then!r}"] = (
                    "Judge plan: the plan holds (reports/judge-1.md)\n", amend, then)
        for name, (first, amend, then) in refused.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.on_opus(run)
                self.append(run, first)
                if amend:
                    replace(run / "plan.md", "First thing", "First thing, amended")
                self.append(run, then)
                self.assertSealRefused(run, "opus", self.UNATTENDED)
                self.assertSeals(run)
        sealed = {"unreachable, then the verdict": "Judge unreachable: quota\nJudge plan: the plan holds (reports/judge-2.md)\n",
                  "a placeholder unreachable, then the verdict": "Judge unreachable: n/a\nJudge plan: the plan holds (reports/judge-2.md)\n",
                  "a ruling's line after the verdict": "Judge plan: the plan holds (reports/judge-1.md)\n"
                                                       "Judge ruling: keep T2 (reports/judge-2.md)\n"}
        for name, lines in sealed.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.on_opus(run)
                self.append(run, lines)
                self.assertSeals(run, "opus")

    def test_unattended_the_verdict_must_say_the_plan_holds(self):
        for verdict in ("the plan does not hold: T3 must own tests/test_x.py (reports/judge-1.md)",
                        "the plan holds, mostly", "The plan holds", "the plan holds (reports/judge-1.md) mostly",
                        "the plan holds (judge-1.md)"):
            with self.subTest(verdict), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.on_opus(run)
                self.append(run, f"Judge plan: {verdict}\n")
                self.assertSealRefused(run, "opus", self.NOT_HOLDING)
                self.assertSeals(run)   # attended, the conductor may overrule it, as in 0.10.0
        for verdict in ("the plan holds", "the plan holds.", "the plan holds (reports/judge-3.md)", "  the plan holds  "):
            with self.subTest(verdict), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.on_opus(run)
                self.append(run, f"Judge plan: {verdict}\n")
                self.assertSeals(run, "opus")

    def test_unattended_a_placeholder_judge_plan_does_not_count(self):
        for line in ("Judge plan: TODO\n", "Judge plan:\n", "Judge plan:   n/a\n"):
            with self.subTest(line), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.on_opus(run)
                self.append(run, line)
                self.assertSealRefused(run, "opus", self.UNATTENDED)

    def test_unattended_a_judge_plan_before_the_last_seal_does_not_cover_an_amended_plan(self):
        repo, run = make_run(self.tmp)
        self.on_opus(run)
        self.append(run, "Judge plan: the plan holds (reports/judge-1.md)\n")
        self.assertSeals(run, "opus")
        replace(run / "plan.md", "First thing", "First thing, amended")
        self.append(run, "Plan judged: the amended plan still meets the criteria.\n")
        self.assertSealRefused(run, "opus", self.UNATTENDED)   # the verdict above the seal was for the old plan
        self.append(run, "Judge unreachable: This agent switched to claude-opus-5-5\n")
        self.assertSealRefused(run, "opus", self.UNATTENDED)
        self.append(run, "Judge plan: the plan holds (reports/judge-2.md)\n")
        self.assertSeals(run, "opus")

    def test_unattended_a_staffing_change_alone_reseals_without_a_new_judge_line(self):
        repo, run = make_run(self.tmp)
        self.on_opus(run)
        self.assertSealRefused(run, "opus", self.UNATTENDED)
        self.append(run, "Judge plan: the plan holds (reports/judge-1.md)\n")
        self.assertSeals(run, "opus")
        # A ruling the judge could not be reached for, after the seal, does not touch an unchanged plan.
        self.append(run, "Judge unreachable: quota\n")
        replace(run / "staffing.md", "| T1 | generalist-engineer | opus | medium |", "| T1 | generalist-engineer | opus | high |")
        self.assertSeals(run, "opus")

    def test_unattended_the_model_comes_from_the_queue_not_the_conductor_line(self):
        repo, run = make_run(self.tmp)   # <r7>: <r1> with a later 'Conductor: Fable 5.2' line
        self.on_opus(run)
        self.append(run, "Judge unreachable: Agent terminated early due to an API error\nConductor: Fable 5.2\n")
        for value in ("opus", "1"):
            with self.subTest(value):
                self.assertSealRefused(run, value, self.UNATTENDED)
        self.assertSeals(run)
        with tempfile.TemporaryDirectory() as tmp:   # the message names Opus 5.5, whatever the Conductor: line says
            repo, run = make_run(tmp)
            self.append(run, "Conductor: Sonnet 5.5\nJudge unreachable: quota\n")
            self.assertSealRefused(run, "opus", self.CONDUCTOR, self.UNATTENDED)
        with tempfile.TemporaryDirectory() as tmp:   # a run the queue started on Fable 5.2 needs no judge line
            repo, run = make_run(tmp)
            self.on_opus(run)
            self.assertSeals(run, "fable")
            self.assertNotIn("Judge", (run / "decisions.md").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:   # --plan still asks for the Conductor: line
            repo, run = make_run(tmp)
            replace(run / "decisions.md", "Conductor: Fable 5.2\n", "")
            for value in ("opus", "fable"):
                plan = self.cli("--plan", str(run), unattended=value)
                self.assertEqual((plan.returncode, plan.stdout.splitlines()), (1, [self.CONDUCTOR]))

    def test_unattended_seal_on_fable_needs_no_judge_line(self):
        repo, run = make_run(self.tmp)   # <r3>
        self.assertSealRefused(run, "opus", self.UNATTENDED)
        self.assertSeals(run, "fable")
        self.assertNotIn("Judge", (run / "decisions.md").read_text(encoding="utf-8"))

    def test_only_unset_or_empty_is_attended_and_any_other_value_is_opus(self):
        for value in (None, ""):   # attended: as in 0.10.0
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.on_opus(run)
                self.assertSealRefused(run, value, self.judge_message())
                self.append(run, "Judge unreachable: Agent terminated early due to an API error\n")
                self.assertSeals(run, value)
        for value in ("1", "0", "true", "yes", " 1", "Opus", "FABLE", "fable ", "sonnet"):   # a typo fails closed
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)
                self.on_opus(run)
                self.append(run, "Judge unreachable: Agent terminated early due to an API error\n")
                self.assertSealRefused(run, value, self.UNATTENDED)

    def test_check_judge_in_process_ignores_the_environment(self):
        repo, run = make_run(self.tmp)
        self.on_opus(run)
        self.append(run, "Judge unreachable: quota\n")
        with unittest.mock.patch.dict(os.environ, {"SWD_UNATTENDED": "opus"}):
            self.assertEqual(self.cr.check_judge(run), [])
            self.assertEqual(self.cr.check_judge(run, unattended=None), [])
            self.assertEqual(self.cr.check_judge(run, unattended="Opus 5.5"), [self.UNATTENDED])
            self.assertEqual(self.cr.check_judge(run, unattended="Fable 5.2"), [])

    def test_a_finished_run_sealed_before_0_10_0_checks_clean_unattended(self):
        repo, run = make_run(self.tmp)
        replace(run / "decisions.md", "Conductor: Fable 5.2\n", "")
        self.cr.seal_plan(run)
        for value in ("opus", "fable"):
            for args in ((str(run),), ("--task", "T1", str(run))):
                done = self.cli(*args, unattended=value)
                self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_the_queue_changes_only_the_seal_and_the_unsealed_check(self):
        # A sealed Opus run whose plan changed since the seal, with only 'Judge unreachable:': the judge rule would
        # print something here, so equal output with and without the variable shows it is applied by --seal alone.
        repo, run = make_run(self.tmp)
        self.on_opus(run)
        self.append(run, "Judge unreachable: quota\n")
        self.cr.seal_plan(run)
        replace(run / "plan.md", "First thing", "First thing, amended")
        for args in ((str(run),), (str(repo),), ("--task", "T1", str(run)), ("--plan", str(run)), ("--finish", str(run))):
            attended = self.cli(*args)
            for value in ("opus", "fable"):
                with self.subTest(args=args[:-1], value=value):
                    queued = self.cli(*args, unattended=value)
                    self.assertEqual((queued.returncode, queued.stdout), (attended.returncode, attended.stdout))
                    self.assertNotIn("started by /swd:queue", queued.stdout)

    def test_an_unsealed_run_the_queue_started_is_reported_by_task_and_the_finished_run_check(self):
        for value in ("opus", "fable"):
            with self.subTest(value), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)   # <r4>: never sealed, and nothing else wrong
                for args in (("--task", "T1", str(run)), (str(run),), (str(repo),)):
                    attended = self.cli(*args)
                    self.assertEqual((attended.returncode, attended.stdout), (0, ""))   # as in 0.10.0
                    done = self.cli(*args, unattended=value)
                    self.assertEqual((done.returncode, done.stdout.splitlines()), (1, [self.UNSEALED]))
                (repo / "stray.txt").write_text("x\n", encoding="utf-8")   # first, before what check_task finds
                task = self.cli("--task", "T1", str(run), unattended=value)
                self.assertEqual((task.returncode, task.stdout.splitlines()),
                                 (1, [self.UNSEALED, "stray.txt changed, but no task owns it"]))
                done = self.cli(str(run), unattended=value)
                self.assertEqual(done.returncode, 1)
                self.assertEqual(done.stdout.splitlines()[0], self.UNSEALED)
                self.assertIn("uncommitted change: stray.txt", done.stdout)
                (repo / "stray.txt").unlink()
                with unittest.mock.patch.dict(os.environ, {"SWD_UNATTENDED": value}):   # in-process: as in 0.10.0
                    self.assertEqual(self.cr.check_task(run, repo, "T1"), [])
                    self.assertEqual(self.cr.check_run(run, repo), [])
                for args in (("--plan", str(run)), ("--finish", str(run)), ("--seal", str(run))):
                    self.assertNotIn(self.UNSEALED, self.cli(*args, unattended=value).stdout)
                self.cr.seal_plan(run)
                for args in (("--task", "T1", str(run)), (str(run),), (str(repo),)):
                    done = self.cli(*args, unattended=value)
                    self.assertEqual((done.returncode, done.stdout), (0, ""))
            with self.subTest(value, line="Plan checksum: none"), tempfile.TemporaryDirectory() as tmp:
                repo, run = make_run(tmp)   # a line that names the seal but is not one does not seal the run
                self.append(run, "Plan checksum: none\n")
                for args in (("--task", "T1", str(run)), (str(run),), (str(repo),)):
                    attended = self.cli(*args)
                    self.assertEqual((attended.returncode, attended.stdout), (0, ""))
                    done = self.cli(*args, unattended=value)
                    self.assertEqual((done.returncode, done.stdout.splitlines()), (1, [self.UNSEALED]))

    def test_docstring_and_help_say_what_a_run_the_queue_started_adds(self):
        doc = self.cr.__doc__
        verdict = "in a run /swd:queue started, the judge's own verdict that the plan holds"
        sealed = "in a run /swd:queue started, a sealed plan"
        self.assertIn(verdict, doc.split("--seal", 1)[1].splitlines()[0])
        self.assertIn(sealed, doc.split("--task T1", 1)[1].splitlines()[0])
        self.assertIn(sealed, next(l for l in doc.splitlines() if "check_run.py <run_dir>" in l))
        self.assertIn(verdict, " ".join(self.cli("--help").stdout.split()))

    def cli(self, *args, unattended=None):
        """Run the script with SWD_UNATTENDED as given, and without it otherwise, so a queue run of this suite passes."""
        env = {k: v for k, v in os.environ.items() if k != "SWD_UNATTENDED"}
        if unattended is not None:
            env["SWD_UNATTENDED"] = unattended
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8", env=env)

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


SLICE_PLAN = """# Plan: slices

Test command: `python3 -m unittest`

## Outcome
OUTCOME-LINE

## Design
DESIGN-LINE

## Contracts
### C1: the contract
CONTRACT-LINE

## Performance
PERFORMANCE-LINE

## Tasks

### T1: First
- Role: generalist-engineer
- Wave: 1
- Files: a.py
- Depends: none
- Check: `true`
- Outcome: TASK1-LINE

#### Detail of T1
TASK1-DETAIL

### T2: Second
- Role: generalist-engineer
- Wave: 1
- Files: b.py
- Depends: none
- Check: `true`
- Outcome: TASK2-LINE
"""

QUICK_PLAN = """# Plan: quick

Test command: `true`

## Outcome
OUTCOME-LINE

### T1: Only
- Role: generalist-engineer
- Wave: 1
- Files: a.py
- Depends: none
- Check: `true`
- Outcome: TASK1-LINE
"""


class SliceTest(unittest.TestCase):
    def setUp(self):
        import check_run
        self.cr = check_run
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo, self.run_dir = make_run(self._tmp.name)

    def slice(self, who, plan=SLICE_PLAN, path=None, unattended=None):
        (self.run_dir / "plan.md").unlink(missing_ok=True)
        if plan is not None:
            (self.run_dir / "plan.md").write_text(plan, encoding="utf-8")
        return self.cli(who, path, unattended)

    def cli(self, who, path=None, unattended=None):
        """--slice on the run as it is, without writing plan.md first."""
        env = {k: v for k, v in os.environ.items() if k != "SWD_UNATTENDED"}
        if unattended:
            env["SWD_UNATTENDED"] = unattended
        return subprocess.run([sys.executable, str(SCRIPT), "--slice", who, str(path or self.run_dir)],
                              capture_output=True, text=True, encoding="utf-8", env=env)

    def assertSlice(self, result, present, absent):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        for word in present + ["Test command:"]:
            self.assertIn(word, result.stdout)
        for word in absent:
            self.assertNotIn(word, result.stdout)

    def test_builder_slice(self):
        self.assertSlice(self.slice("builder:T1"),
                         ["# Plan: slices", "DESIGN-LINE", "CONTRACT-LINE", "### C1", "PERFORMANCE-LINE", "TASK1-LINE", "TASK1-DETAIL"],
                         ["OUTCOME-LINE", "TASK2-LINE", "## Tasks"])

    def test_review_task_slice(self):
        self.assertSlice(self.slice("review:T2"),
                         ["CONTRACT-LINE", "PERFORMANCE-LINE", "TASK2-LINE"],
                         ["DESIGN-LINE", "OUTCOME-LINE", "TASK1-LINE", "TASK1-DETAIL"])

    def test_review_final_slice(self):
        self.assertSlice(self.slice("review:final"),
                         ["OUTCOME-LINE", "CONTRACT-LINE", "PERFORMANCE-LINE", "TASK1-LINE", "TASK1-DETAIL", "TASK2-LINE"],
                         ["DESIGN-LINE", "## Tasks"])

    def test_qa_slice(self):
        self.assertSlice(self.slice("qa"), ["OUTCOME-LINE"],
                         ["DESIGN-LINE", "CONTRACT-LINE", "PERFORMANCE-LINE", "TASK1-LINE", "TASK2-LINE"])

    def test_lines_are_plan_lines_in_order_once(self):
        lines = SLICE_PLAN.splitlines()
        for who in ("builder:T1", "review:final", "qa"):
            out = self.slice(who).stdout.splitlines()
            rest = iter(lines)  # every printed line is found, unchanged, after the one before it
            self.assertTrue(all(l in rest for l in out), who)

    def test_missing_performance_is_left_out(self):
        plan = SLICE_PLAN.replace("## Performance\nPERFORMANCE-LINE\n\n", "")
        self.assertSlice(self.slice("builder:T1", plan), ["TASK1-LINE"], ["PERFORMANCE-LINE"])

    def test_quick_plan(self):
        self.assertSlice(self.slice("builder:T1", QUICK_PLAN), ["TASK1-LINE"], ["OUTCOME-LINE"])
        self.assertSlice(self.slice("review:final", QUICK_PLAN), ["OUTCOME-LINE", "TASK1-LINE"], [])
        self.assertSlice(self.slice("qa", QUICK_PLAN), ["OUTCOME-LINE"], ["TASK1-LINE"])

    def test_project_folder_resolves_the_last_run(self):
        self.assertSlice(self.slice("qa", path=self.run_dir.parents[2]), ["OUTCOME-LINE"], [])

    def test_errors_are_one_line_on_stderr(self):
        cases = [
            ("builder:T9", SLICE_PLAN, "plan.md: no task T9"),
            ("review:T9", SLICE_PLAN, "plan.md: no task T9"),
            ("tester", SLICE_PLAN, "--slice: 'tester' is not one of builder:T<n>, review:T<n>, review:final, qa"),
            ("builder:", SLICE_PLAN, "--slice: 'builder:' is not one of builder:T<n>, review:T<n>, review:final, qa"),
            ("builder:T1", None, "missing plan.md"),
        ]
        for who, plan, message in cases:
            result = self.slice(who, plan)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (1, "", message + "\n"), who)

    def test_error_order_who_before_run_folder(self):
        empty = Path(self._tmp.name) / "empty"
        empty.mkdir()
        self.assertIn("is not one of", self.slice("nope", path=empty).stderr)
        result = self.slice("qa", path=empty)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, "", "no run folder found under .swd/runs/\n"))

    def state(self):
        """Every file under the repo (outside .git) with its bytes, and git status --short."""
        files = {p: p.read_bytes() for p in self.repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(self.repo).parts}
        status = subprocess.run(["git", "-C", str(self.repo), "status", "--short", "--untracked-files=all"],
                                capture_output=True, text=True, encoding="utf-8", check=True).stdout
        return files, status

    def test_changes_nothing_and_ignores_the_queue(self):
        for plan in (SLICE_PLAN, QUICK_PLAN):
            (self.run_dir / "plan.md").write_text(plan, encoding="utf-8")
            before = self.state()
            for env in (None, "fable", "opus"):
                for who in ("builder:T1", "review:T1", "review:final", "qa", "builder:T9", "tester"):
                    self.cli(who, unattended=env)
            self.assertEqual(self.state(), before)

    def test_sealed_and_unsealed_print_the_same(self):
        for plan in (SLICE_PLAN, QUICK_PLAN):
            (self.run_dir / "plan.md").write_text(plan, encoding="utf-8")
            decisions = (self.run_dir / "decisions.md").read_text(encoding="utf-8")
            self.assertNotIn("Plan checksum:", decisions)
            whos = ("builder:T1", "review:T1", "review:final", "qa")
            unsealed = {who: self.cli(who) for who in whos}
            queued = {who: self.cli(who, unattended="opus") for who in whos}
            with open(self.run_dir / "decisions.md", "a", encoding="utf-8") as f:
                f.write(f"Plan checksum: {self.cr.plan_checksum(self.run_dir)}\n")
            for who in whos:
                sealed = self.cli(who)
                self.assertEqual((sealed.returncode, sealed.stderr), (0, ""), who)
                self.assertEqual(sealed.stdout, unsealed[who].stdout, who)
                self.assertEqual(sealed.stdout, queued[who].stdout, who)
                self.assertEqual(self.cli(who, unattended="opus").stdout, sealed.stdout, who)
            (self.run_dir / "decisions.md").write_text(decisions, encoding="utf-8")


GB = 2 ** 30
BAD_PARALLEL = "SWD_PARALLEL={!r} ignored: use a whole number of 1 or more, or none\n"


class CapTest(unittest.TestCase):
    """--cap: how many agents may work at once. Memory is replaced in a child process, never read from this machine."""

    def cap(self, parallel, setup="check_run.total_memory = lambda: None", args=("--cap",)):
        """Run check_run.main(args) in a child with SWD_PARALLEL set to `parallel` (None removes it); `setup` runs first.
        The child switches its output to UTF-8 as check_run.py's __main__ does, which `-c` skips (a piped stream on
        Windows is otherwise in the ANSI code page)."""
        code = (f"import os, sys; sys.path.insert(0, {str(ROOT / 'scripts')!r}); import check_run\n"
                "sys.stdout.reconfigure(encoding='utf-8', errors='replace')\n"
                "sys.stderr.reconfigure(encoding='utf-8', errors='replace')\n"
                f"{setup}\nsys.exit(check_run.main({list(args)!r}))")
        env = {k: v for k, v in os.environ.items() if k != "SWD_PARALLEL"}
        if parallel is not None:
            env["SWD_PARALLEL"] = parallel
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", env=env)

    def memory(self, nbytes, parallel=None):
        return self.cap(parallel, f"check_run.total_memory = lambda: {nbytes}")

    def assertCap(self, result, line, stderr=""):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, line + "\n", stderr))

    def test_memory_bands_and_their_boundaries(self):
        cases = [(1 * GB, "1 (total memory 1.0 GB)"), (8 * GB, "1 (total memory 8.0 GB)"),
                 (8 * GB + 1, "2 (total memory 8.0 GB)"), (12 * GB, "2 (total memory 12.0 GB)"),
                 (16 * GB, "2 (total memory 16.0 GB)"), (16 * GB + 1, "none (total memory 16.0 GB)"),
                 (64 * GB, "none (total memory 64.0 GB)")]
        for nbytes, line in cases:
            with self.subTest(nbytes=nbytes):
                self.assertCap(self.memory(nbytes), "Cap: " + line)

    def test_unreadable_memory_is_no_cap(self):
        line = "Cap: none (total memory could not be read)"
        self.assertCap(self.cap(None), line)
        if hasattr(os, "sysconf"):
            boom = "def boom(name): raise ValueError(name)\nos.sysconf = boom"
            self.assertCap(self.cap(None, boom), line)

    def test_the_override_beats_memory(self):
        for value, line in (("1", "Cap: 1 (SWD_PARALLEL=1)"), ("3", "Cap: 3 (SWD_PARALLEL=3)"),
                            ("12", "Cap: 12 (SWD_PARALLEL=12)"), ("999999", "Cap: 999999 (SWD_PARALLEL=999999)"),
                            ("none", "Cap: none (SWD_PARALLEL=none)")):
            with self.subTest(value=value):
                self.assertCap(self.memory(4 * GB, value), line)

    def test_a_bad_override_is_named_on_stderr_and_memory_decides(self):
        for value in ("0", "-1", "2.5", " 2", "2 ", "01", "None", "NONE", "two", "٢", "1000000", "9" * 5000):
            with self.subTest(value=value[:20], length=len(value)):
                self.assertCap(self.memory(4 * GB, value), "Cap: 1 (total memory 4.0 GB)", BAD_PARALLEL.format(value))

    def test_an_empty_override_is_unset(self):
        self.assertCap(self.memory(4 * GB, ""), "Cap: 1 (total memory 4.0 GB)")

    def test_a_path_given_with_cap_is_ignored(self):
        self.assertCap(self.cap("2", args=("--cap", str(ROOT / "nowhere"))), "Cap: 2 (SWD_PARALLEL=2)")

    def test_total_memory_here_is_a_positive_int(self):
        import check_run
        total = check_run.total_memory()
        self.assertIsInstance(total, int)
        self.assertGreater(total, 0)
        if sys.platform == "darwin":
            sysctl = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True)
            self.assertEqual(total, int(sysctl.stdout))

    def test_every_other_mode_still_needs_a_path(self):
        for args in (("--slice", "qa"), ("--finish",), ("--task", "T1"), ("--plan",), ("--seal",), ()):
            with self.subTest(args=args):
                result = self.cap("none", args=args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("the following arguments are required: path", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_cap_with_another_mode_is_refused_and_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "plan.md").write_text("# Plan\n", encoding="utf-8")
            decisions = "Base commit: 0\nPlan judged: holds\n"
            (run / "decisions.md").write_text(decisions, encoding="utf-8")
            env = {**os.environ, "SWD_PARALLEL": "2"}
            for mode in (["--plan"], ["--seal"], ["--task", "T1"], ["--finish"], ["--slice", "qa"]):
                with self.subTest(mode=mode):
                    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_run.py"), "--cap", *mode, tmp],
                                            capture_output=True, text=True, encoding="utf-8", env=env)
                    self.assertEqual((result.returncode, result.stdout), (2, ""))
                    self.assertTrue(result.stderr.endswith("check_run.py: error: --cap takes no other mode\n"), result.stderr)
                    self.assertEqual((run / "decisions.md").read_text(encoding="utf-8"), decisions)
                    self.assertEqual(sorted(p.name for p in run.iterdir()), ["decisions.md", "plan.md"])


class CodeGraphTest(unittest.TestCase):
    """--codegraph: whether the project has a code graph. PATH is one temp folder holding a stub, never a real codegraph."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.cwd = self.tmp / "cwd"
        self.cwd.mkdir()

    def stub(self):
        if os.name == "nt":
            (self.bin / "codegraph.exe").write_bytes(b"")
        else:
            (self.bin / "codegraph").write_text('#!/bin/sh\necho ran >> "$0.ran"\nexit 3\n', encoding="utf-8")
            (self.bin / "codegraph").chmod(0o755)

    def project(self, name="shop", index=True):
        project = self.tmp / name
        (project / ".swd" / "runs" / "r1").mkdir(parents=True)
        (project / ".swd" / "worktrees" / "r1").mkdir(parents=True)
        if index:
            (project / ".codegraph").mkdir()
        return project

    def run_cg(self, *args):
        env = {**os.environ, "PATH": str(self.bin)}
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "check_run.py"), *map(str, args)],
                              capture_output=True, text=True, encoding="utf-8", env=env, cwd=self.cwd)

    def assertLine(self, result, line):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, line + "\n", ""))
        self.assertFalse((self.bin / "codegraph.ran").exists())

    def test_yes_for_a_run_folder_a_worktree_and_the_project(self):
        self.stub()
        project = self.project()
        line = f"Code graph: yes ({project.as_posix()})"
        for path in (project / ".swd" / "runs" / "r1", project / ".swd" / "worktrees" / "r1", project):
            with self.subTest(path=path):
                self.assertLine(self.run_cg("--codegraph", path), line)

    def test_no_index_directory(self):
        self.stub()
        project = self.project(index=False)
        self.assertLine(self.run_cg("--codegraph", project), f"Code graph: none (no .codegraph/ directory in {project.as_posix()})")
        self.assertEqual(sorted(p.name for p in project.iterdir()), [".swd"])

    def test_codegraph_that_is_a_file_is_no_index(self):
        self.stub()
        project = self.project(index=False)
        (project / ".codegraph").write_text("", encoding="utf-8")
        self.assertLine(self.run_cg("--codegraph", project), f"Code graph: none (no .codegraph/ directory in {project.as_posix()})")

    def test_an_index_only_in_a_parent_folder_is_not_used(self):
        self.stub()
        (self.tmp / ".codegraph").mkdir()
        project = self.project(index=False)
        self.assertLine(self.run_cg("--codegraph", project), f"Code graph: none (no .codegraph/ directory in {project.as_posix()})")

    def test_command_not_on_path(self):
        project = self.project()
        self.assertLine(self.run_cg("--codegraph", project / ".swd" / "runs" / "r1"), "Code graph: none (codegraph is not on PATH)")

    def test_a_space_in_the_folder_name_is_quoted(self):
        self.stub()
        project = self.project("my shop")
        self.assertLine(self.run_cg("--codegraph", project), f"Code graph: yes ('{project.as_posix()}')")

    @unittest.skipIf(os.name == "nt", "a newline cannot be in a Windows file name")
    def test_a_newline_in_the_folder_name(self):
        self.stub()
        project = self.project("a\nb")
        self.assertLine(self.run_cg("--codegraph", project / ".swd" / "runs" / "r1"),
                        "Code graph: none (the project folder's path holds a character that cannot be printed on one line)")

    def test_mode_clashes_are_refused(self):
        self.stub()
        project = self.project()
        cases = [("--cap takes no other mode", ["--cap", "--codegraph"])]
        cases += [("--codegraph takes no other mode", ["--codegraph", *mode])
                  for mode in (["--plan"], ["--seal"], ["--task", "T1"], ["--finish"], ["--slice", "qa"])]
        for message, args in cases:
            with self.subTest(args=args):
                result = self.run_cg(*args, project)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertTrue(result.stderr.endswith(f"check_run.py: error: {message}\n"), result.stderr)
        self.assertEqual(sorted(p.name for p in project.iterdir()), [".codegraph", ".swd"])
        self.assertFalse((self.bin / "codegraph.ran").exists())

    def test_no_path_is_refused(self):
        result = self.run_cg("--codegraph")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertTrue(result.stderr.endswith("the following arguments are required: path\n"), result.stderr)


if __name__ == "__main__":
    unittest.main()
