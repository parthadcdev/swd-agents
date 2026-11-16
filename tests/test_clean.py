"""Tests for scripts/swd-clean.py: housekeeping of stale swd worktrees and branches at the start of a run.

Everything runs against real git repos in a temp folder, with a bare repo as `origin`.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "swd-clean.py"

GH_STUB = """#!/bin/sh
# gh pr list --head <branch> --state merged --json headRefOid  ->  the merged head recorded for the test
cat "$GH_STUB_REPLY" 2>/dev/null || echo "[]"
"""


def git(cwd, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", *args],
        check=check, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()


class CleanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.project = self.tmp / "project"
        self.project.mkdir()
        git(self.project, "init", "-q", "-b", "main")
        (self.project / "README.md").write_text("demo\n", encoding="utf-8")
        git(self.project, "add", "README.md")
        git(self.project, "commit", "-q", "-m", "Initial commit")
        git(self.tmp, "init", "-q", "--bare", "origin.git")
        git(self.project, "remote", "add", "origin", str(self.tmp / "origin.git"))
        git(self.project, "push", "-q", "-u", "origin", "main")
        # the run that is starting now
        self.run_dir = self.past_run("current", ledger=None, commit=False)

    def past_run(self, name, ledger="done", abandoned=False, commit=True, pushed=False):
        """A run on swd/<name> in its own worktree. ledger: 'done', 'todo' or None (no ledger yet)."""
        work = self.project / ".swd" / "worktrees" / name
        git(self.project, "worktree", "add", "-q", str(work), "-b", f"swd/{name}")
        if commit:
            (work / f"{name}.py").write_text("x = 1\n", encoding="utf-8")
            git(work, "add", f"{name}.py")
            git(work, "commit", "-q", "-m", f"T1: {name}")
        if pushed:
            git(work, "push", "-q", "-u", "origin", f"swd/{name}")
        run = self.project / ".swd" / "runs" / f"2026-11-12-{name}"
        run.mkdir(parents=True)
        lines = ["Base commit: 0", "Base branch: main", f"Branch: swd/{name}", f"Worktree: {work}", "Finish: branch"]
        if abandoned:
            lines.append("Abandoned: 2026-11-12")
        (run / "decisions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if ledger:
            (run / "ledger.md").write_text(
                f"| Task | Role | Status | Attempts |\n|---|---|---|---|\n| T1 | generalist-engineer | {ledger} | 1 |\n", encoding="utf-8")
        return run

    def merge_to_main(self, name, push=True):
        git(self.project, "merge", "-q", "--no-ff", "-m", f"Merge {name}", f"swd/{name}")
        if push:
            git(self.project, "push", "-q", "origin", "main")

    def clean(self, **env):
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.run_dir)], capture_output=True, text=True,
                                env={**os.environ, **env}, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result.stdout

    def branches(self):
        return set(git(self.project, "branch", "--format=%(refname:short)").split())

    def remote_branches(self):
        return set(git(self.tmp / "origin.git", "branch", "--format=%(refname:short)").split())

    def worktrees(self):
        return {p.name for p in (self.project / ".swd" / "worktrees").iterdir()}

    def test_merged_run_is_cleaned_up_locally_and_on_the_remote(self):
        self.past_run("login", pushed=True)
        self.merge_to_main("login")
        out = self.clean()
        self.assertNotIn("login", self.worktrees())
        self.assertNotIn("swd/login", self.branches())
        self.assertNotIn("swd/login", self.remote_branches())
        self.assertIn("swd/login", out)

    def test_finished_but_unmerged_run_keeps_its_branch_and_says_so(self):
        self.past_run("search")
        out = self.clean()
        self.assertNotIn("search", self.worktrees())      # a finished run's worktree is not needed
        self.assertIn("swd/search", self.branches())       # its commits are, until merged
        self.assertRegex(out, r"kept .*swd/search.*not merged")

    def test_unfinished_run_is_left_alone_to_be_resumed(self):
        self.past_run("billing", ledger="todo")
        out = self.clean()
        self.assertIn("billing", self.worktrees())
        self.assertIn("swd/billing", self.branches())
        self.assertRegex(out, r"kept .*swd/billing.*not finished")

    def test_abandoned_run_loses_its_worktree_but_not_unmerged_commits(self):
        self.past_run("export", ledger="todo", abandoned=True)
        out = self.clean()
        self.assertNotIn("export", self.worktrees())
        self.assertIn("swd/export", self.branches())
        self.assertRegex(out, r"kept .*swd/export.*not merged")

    def test_worktree_with_uncommitted_changes_is_never_removed(self):
        self.past_run("draft", ledger="todo", abandoned=True)
        (self.project / ".swd" / "worktrees" / "draft" / "wip.py").write_text("unsaved\n", encoding="utf-8")
        out = self.clean()
        self.assertIn("draft", self.worktrees())
        self.assertRegex(out, r"kept .*draft.*uncommitted")

    @unittest.skipIf(os.name == "nt", "the stub is a shell script, and Windows starts only .exe programs by name")
    def test_squash_merged_pull_request_is_recognised_through_gh(self):
        self.past_run("report", pushed=True)
        git(self.project, "worktree", "remove", str(self.project / ".swd" / "worktrees" / "report"))
        tip = git(self.project, "rev-parse", "swd/report")
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text(GH_STUB, encoding="utf-8")
        (bin_dir / "gh").chmod(0o755)
        reply = self.tmp / "reply.json"
        env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "GH_STUB_REPLY": str(reply)}

        reply.write_text('[{"headRefOid": "0000000000000000000000000000000000000000"}]', encoding="utf-8")
        self.clean(**env)
        self.assertIn("swd/report", self.branches())       # a different commit was merged: keep ours

        reply.write_text('[{"headRefOid": "%s"}]' % tip, encoding="utf-8")
        self.clean(**env)
        self.assertNotIn("swd/report", self.branches())
        self.assertNotIn("swd/report", self.remote_branches())

    def test_merged_branch_the_user_has_checked_out_is_kept_and_reported(self):
        self.past_run("login")
        self.merge_to_main("login")
        git(self.project, "worktree", "remove", str(self.project / ".swd" / "worktrees" / "login"))
        git(self.project, "checkout", "-q", "swd/login")   # the user is sitting on the merged branch
        out = self.clean()
        self.assertIn("swd/login", self.branches())
        self.assertRegex(out, r"kept .*swd/login.*checked out")

    def test_only_swd_branches_and_worktrees_are_touched(self):
        git(self.project, "branch", "feature/mine")
        git(self.project, "branch", "old-merged")           # merged into main, but not ours to delete
        git(self.project, "worktree", "add", "-q", str(self.tmp / "elsewhere"), "-b", "side")
        git(self.project, "push", "-q", "origin", "feature/mine")
        self.clean()
        self.assertTrue({"feature/mine", "old-merged", "side"} <= self.branches())
        self.assertIn("feature/mine", self.remote_branches())
        self.assertTrue((self.tmp / "elsewhere").is_dir())

    def test_the_starting_run_is_untouched_and_gets_a_housekeeping_line(self):
        self.past_run("login")
        self.merge_to_main("login")
        self.clean()
        self.assertIn("current", self.worktrees())
        self.assertIn("swd/current", self.branches())
        self.assertRegex((self.run_dir / "decisions.md").read_text(encoding="utf-8"), r"(?m)^Housekeeping: removed \d+, kept \d+$")

    def test_works_without_a_remote(self):
        git(self.project, "remote", "remove", "origin")
        self.past_run("login")
        self.merge_to_main("login", push=False)
        self.clean()
        self.assertNotIn("swd/login", self.branches())

    def test_nothing_to_do_is_quiet_and_still_recorded(self):
        out = self.clean()
        self.assertNotIn("kept", out)
        self.assertIn("Housekeeping: removed 0, kept 0", (self.run_dir / "decisions.md").read_text(encoding="utf-8"))

    def test_a_folder_that_is_not_a_run_is_an_error_not_a_traceback(self):
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.tmp)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
