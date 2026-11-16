"""Tests for check_run.py --finish: after a run is delivered, the worktree is gone and the
chosen finish (merge and push, pull request, or leave the branch) really happened."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_run.py"
sys.path.insert(0, str(ROOT / "scripts"))


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()


def make_project(tmp, finish, remote=True):
    """A project on main with a finished run on swd/demo in its own worktree. Returns (project, work, run)."""
    tmp = Path(tmp)
    project = tmp / "project"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    (project / "README.md").write_text("demo\n", encoding="utf-8")
    git(project, "add", "README.md")
    git(project, "commit", "-q", "-m", "Initial commit")
    base = git(project, "rev-parse", "HEAD")
    if remote:
        git(tmp, "init", "-q", "--bare", "origin.git")
        git(project, "remote", "add", "origin", str(tmp / "origin.git"))
        git(project, "push", "-q", "-u", "origin", "main")
    work = project / ".swd" / "worktrees" / "demo"
    git(project, "worktree", "add", "-q", str(work), "-b", "swd/demo")
    (work / "a.py").write_text("x = 1\n", encoding="utf-8")
    git(work, "add", "a.py")
    git(work, "commit", "-q", "-m", "T1: Add a")
    run = project / ".swd" / "runs" / "2026-11-12-demo"
    run.mkdir(parents=True)
    lines = [f"Base commit: {base}", "Base branch: main", "Branch: swd/demo", f"Worktree: {work}"]
    if finish:
        lines.append(f"Finish: {finish}")
    (run / "decisions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return project, work, run


class FinishTest(unittest.TestCase):
    def setUp(self):
        import check_run
        self.cr = check_run
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name

    def assertProblem(self, problems, *needles):
        self.assertTrue(
            any(all(n in p for n in needles) for p in problems),
            f"no problem mentioning {needles}; got {problems}",
        )

    def merge(self, project, work, push=True, delete_branch=True):
        git(project, "merge", "-q", "--ff-only", "swd/demo")
        if push:
            git(project, "push", "-q", "origin", "main")
        git(project, "worktree", "remove", str(work))
        if delete_branch:
            git(project, "branch", "-q", "-d", "swd/demo")

    def test_leaving_the_branch_is_complete_once_the_worktree_is_gone(self):
        project, work, run = make_project(self.tmp, "branch")
        self.assertProblem(self.cr.check_finish(run, project), "worktree", "still there")
        git(project, "worktree", "remove", str(work))
        self.assertEqual(self.cr.check_finish(run, project), [])

    def test_merge_and_push_is_complete(self):
        project, work, run = make_project(self.tmp, "merge-push")
        self.merge(project, work)
        self.assertEqual(self.cr.check_finish(run, project), [])

    def test_merge_without_a_remote_is_complete(self):
        project, work, run = make_project(self.tmp, "merge-push", remote=False)
        self.merge(project, work, push=False)
        self.assertEqual(self.cr.check_finish(run, project), [])

    def test_merge_that_was_not_pushed_is_reported(self):
        project, work, run = make_project(self.tmp, "merge-push")
        self.merge(project, work, push=False)
        self.assertProblem(self.cr.check_finish(run, project), "main", "not pushed")

    def test_merged_branch_left_behind_is_reported(self):
        project, work, run = make_project(self.tmp, "merge-push")
        self.merge(project, work, delete_branch=False)
        self.assertProblem(self.cr.check_finish(run, project), "swd/demo", "delete")

    def test_merge_that_did_not_happen_is_reported(self):
        project, work, run = make_project(self.tmp, "merge-push")
        git(project, "worktree", "remove", str(work))
        self.assertProblem(self.cr.check_finish(run, project), "swd/demo", "not merged into main")

    def test_pull_request_finish_needs_the_branch_pushed(self):
        project, work, run = make_project(self.tmp, "pr")
        git(project, "worktree", "remove", str(work))
        self.assertProblem(self.cr.check_finish(run, project), "swd/demo", "not pushed")
        git(project, "push", "-q", "-u", "origin", "swd/demo")
        self.assertEqual(self.cr.check_finish(run, project), [])

    def test_last_finish_line_wins(self):
        # "pr" falls back to "branch" when the project has no remote; the principal records that.
        project, work, run = make_project(self.tmp, "pr", remote=False)
        with open(run / "decisions.md", "a", encoding="utf-8") as f:
            f.write("Finish: branch\n")
        git(project, "worktree", "remove", str(work))
        self.assertEqual(self.cr.check_finish(run, project), [])

    def test_missing_finish_choice_is_reported(self):
        project, work, run = make_project(self.tmp, None)
        self.assertProblem(self.cr.check_finish(run, project), "Finish:")

    def test_cli(self):
        project, work, run = make_project(self.tmp, "branch")
        cli = lambda: subprocess.run([sys.executable, str(SCRIPT), "--finish", str(run)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(cli().returncode, 1)
        git(project, "worktree", "remove", str(work))
        done = cli()
        self.assertEqual((done.returncode, done.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
