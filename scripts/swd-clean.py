#!/usr/bin/env python3
"""Housekeeping at the start of an swd run: clear out what earlier runs left behind.

    python3 swd-clean.py <run_dir>      <run_dir> is the run that is starting now

It only ever touches `swd/` branches and worktrees under `.swd/worktrees/`, and only removes
what cannot lose work:

  - the worktree of a run that is finished or abandoned, when it has no uncommitted changes;
  - a local `swd/` branch whose tip is already in its base branch, or is the head of a merged
    pull request;
  - the same branch on `origin`, when it points at that same merged work.

Everything else is kept and listed with the reason, for the user to decide. An unfinished run
is left alone so it can be resumed. The result is recorded in the starting run's decisions.md
as a `Housekeeping:` line, which the plan check requires.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_run import decision, git, parse_ledger, read  # noqa: E402


class Project:
    def __init__(self, path):
        self.path = path

    def git(self, *args):
        """(succeeded, output). Housekeeping never stops on a git error."""
        try:
            return True, git(self.path, *args).strip()
        except (OSError, subprocess.CalledProcessError):
            return False, ""

    def ref(self, name):
        ok, sha = self.git("rev-parse", "--verify", "--quiet", name)
        return sha if ok and sha else None

    def contains(self, base, tip):
        """True when every commit of `tip` is already in `base`."""
        return bool(base and tip) and self.git("merge-base", "--is-ancestor", tip, base)[0]

    def merged_pr_heads(self, branch):
        """Head commits of merged pull requests for this branch, via gh. Empty when gh cannot say."""
        try:
            reply = subprocess.run(
                ["gh", "pr", "list", "--head", branch, "--state", "merged", "--json", "headRefOid"],
                cwd=self.path, capture_output=True, text=True, timeout=30,
            )
            return {pr["headRefOid"] for pr in json.loads(reply.stdout or "[]")}
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
            return set()


def run_finished(run_dir):
    rows, _ = parse_ledger(read(run_dir / "ledger.md") or "")
    return bool(rows) and all(row["status"] == "done" for row in rows.values())


def clean(run_dir):
    project = Project(run_dir.parents[2])
    removed, kept = [], []
    current_branch = decision(run_dir, "Branch")
    has_remote = "origin" in project.git("remote")[1].split()
    if has_remote:
        project.git("fetch", "--quiet", "--prune", "origin")  # offline is fine; we work from what we have
    project.git("worktree", "prune")

    runs = {}  # branch -> its newest run folder
    for other in sorted((run_dir.parent).iterdir()):
        branch = decision(other, "Branch") if other.is_dir() and other != run_dir else None
        if branch:
            runs[branch] = other

    def base_of(branch):
        recorded = decision(runs[branch], "Base branch") if branch in runs else None
        if recorded and project.ref(f"refs/heads/{recorded}"):
            return recorded
        return project.git("branch", "--show-current")[1] or None

    def is_merged(branch, tip):
        base = base_of(branch)
        tips = [project.ref(f"refs/heads/{base}"), project.ref(f"refs/remotes/origin/{base}")] if base else []
        return any(project.contains(t, tip) for t in tips) or tip in project.merged_pr_heads(branch)

    # Worktrees first: a branch cannot be deleted while it is checked out.
    home = (project.path / ".swd" / "worktrees").resolve()
    busy = {current_branch}  # branches this pass must not delete
    path = None
    for line in project.git("worktree", "list", "--porcelain")[1].splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
        elif line.startswith("branch refs/heads/swd/") and path and home in path.resolve().parents:
            branch = line[len("branch refs/heads/"):]
            run = runs.get(branch)
            if branch == current_branch:
                continue
            busy.add(branch)
            if run and not run_finished(run) and not decision(run, "Abandoned"):
                kept.append(f"{branch}: its run is not finished; resume it with /swd:build, or abandon it")
            elif project.git("-C", str(path), "status", "--porcelain")[1]:
                kept.append(f"worktree {path.name} ({branch}): it has uncommitted changes")
            elif project.git("worktree", "remove", str(path))[0]:
                removed.append(f"removed worktree .swd/worktrees/{path.name}")
                busy.discard(branch)
            else:
                kept.append(f"worktree {path.name} ({branch}): git would not remove it")

    local = project.git("for-each-ref", "--format=%(refname:short)", "refs/heads/swd")[1].split()
    remote = [r[len("origin/"):] for r in
              project.git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/swd")[1].split()]

    for branch in local:
        if branch in busy:
            continue
        tip = project.ref(f"refs/heads/{branch}")
        if not is_merged(branch, tip):
            kept.append(f"{branch}: not merged into {base_of(branch)}; merge it, or delete it yourself if it is not wanted")
            busy.add(branch)  # so its remote copy is left alone too
        elif project.git("branch", "-D", branch)[0]:  # safe: its tip was just shown to be merged
            removed.append(f"deleted branch {branch} (already merged)")
        else:
            kept.append(f"{branch}: already merged, but it is checked out; switch to another branch and it will go next run")
            busy.add(branch)

    for branch in remote if has_remote else []:
        tip = project.ref(f"refs/remotes/origin/{branch}")
        if branch in busy or project.ref(f"refs/heads/{branch}") or not is_merged(branch, tip):
            continue
        if project.git("push", "--quiet", "origin", "--delete", branch)[0]:
            removed.append(f"deleted remote branch origin/{branch} (already merged)")
        else:
            kept.append(f"origin/{branch}: merged, but the remote would not delete it")
    return removed, kept


def main(argv):
    run_dir = Path(argv[1]).resolve() if len(argv) == 2 else None
    if run_dir is None or run_dir.parent.name != "runs" or run_dir.parent.parent.name != ".swd" \
            or not (run_dir / "decisions.md").is_file():
        print("usage: swd-clean.py <run_dir>   (the folder of the run that is starting, with its decisions.md)",
              file=sys.stderr)
        return 1
    removed, kept = clean(run_dir)
    for line in removed:
        print(line)
    for line in kept:
        print("kept " + line)
    if not removed and not kept:
        print("housekeeping: nothing to clean up")
    with open(run_dir / "decisions.md", "a") as f:
        f.write(f"Housekeeping: removed {len(removed)}, kept {len(kept)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
