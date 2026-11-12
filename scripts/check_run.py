#!/usr/bin/env python3
"""Validate an swd run folder.

    python3 check_run.py --plan <run_dir>      check spec.md and plan.md only (before the gate)
    python3 check_run.py --seal <run_dir>      record the approved plan's checksum in decisions.md
    python3 check_run.py --task T1 <run_dir>   check a returned task's changes before review
    python3 check_run.py <run_dir>             check a finished run

<run_dir> is .swd/runs/<name>/ in the project. A project folder also works: its last run by
name is checked.

Prints one problem per line. Exit 0 when there are none, 1 otherwise.
The formats checked here are documented in standards/run-folder.md.
"""
import argparse
import hashlib
import posixpath
import re
import subprocess
import sys
from pathlib import Path

BUILDERS = {
    "generalist-engineer", "backend-engineer", "frontend-engineer",
    "database-engineer", "devops-engineer", "docs-writer",
}
STATUSES = {"todo", "in-progress", "in-review", "done", "blocked"}
EVENTS = {"dispatch", "return", "verdict", "commit", "fix", "replan", "ruling", "wave-done", "blocked", "done"}
TASK_FIELDS = ("Role", "Wave", "Files", "Depends", "Check")
BUILDER_SECTIONS = ("Summary", "Files changed", "Test first (failing)", "Test after (passing)", "Complexity", "Concerns")
CHECKER_SUFFIXES = ("code-reviewer", "security-reviewer", "qa-engineer")
PLACEHOLDERS = {"todo", "tbd", "n/a", "na", "none", "...", "-"}  # not evidence
VERDICT_RE = re.compile(r"^Verdict: (pass|fail)\s*$", re.M)
EVIDENCE_SECTIONS = ("Test first (failing)", "Test after (passing)")

TASK_RE = re.compile(r"^### (T\d+): (.+)$")
TASK_LIKE_RE = re.compile(r"^#+\s*T(ask)?\s*\d+\b", re.I)  # a heading that was meant to be a task
BASE_RE = re.compile(r"^Base commit: (\S+)", re.M)
SEAL_RE = re.compile(r"^Plan checksum: ([0-9a-f]{64})\s*$", re.M)
FIELD_RE = re.compile(r"^- (%s): (.*)$" % "|".join(TASK_FIELDS))
ACTIVITY_RE = re.compile(r"^- \d{2}:\d{2}:\d{2} (\S+)( .*)?$")
COMMIT_RE = re.compile(r"^([TW]\d+):")


def parse_plan(text):
    """Return (tasks, problems). A task is a dict: id, title, role, wave, files, depends, check."""
    tasks, problems, raw, current = [], [], {}, None
    for number, line in enumerate(text.splitlines(), 1):
        header = TASK_RE.match(line)
        if header:
            current = {"id": header.group(1), "title": header.group(2).strip()}
            raw[current["id"]] = {}
            tasks.append(current)
            continue
        if line.startswith("#"):
            current = None  # any other heading ends the task
            if TASK_LIKE_RE.match(line):
                problems.append(f"plan.md line {number}: a task heading must be '### T<n>: <title>'")
            continue
        field = FIELD_RE.match(line)
        if field and current:
            raw[current["id"]][field.group(1)] = field.group(2).strip()
        elif field:
            problems.append(f"plan.md line {number}: '- {field.group(1)}:' is not under a task heading")

    for task in tasks:
        fields = raw[task["id"]]
        for name in TASK_FIELDS:
            if not fields.get(name):
                problems.append(f"plan.md: {task['id']} is missing '- {name}:'")
        task["role"] = fields.get("Role", "")
        task["check"] = fields.get("Check", "")
        task["files"] = [posixpath.normpath(f.strip().strip("`")) for f in fields.get("Files", "").split(",") if f.strip()]
        depends = fields.get("Depends", "")
        task["depends"] = [] if depends.lower() in ("", "none") else [d.strip() for d in depends.split(",")]
        wave = fields.get("Wave", "")
        task["wave"] = int(wave) if wave.isdecimal() else None
        if wave and task["wave"] is None:
            problems.append(f"plan.md: {task['id']} Wave must be a number, got '{wave}'")
    return tasks, problems


def parse_ledger(text):
    """Return ({task id: {role, status, attempts}}, problems)."""
    rows, problems = {}, []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] == "Task" or set(cells[0]) <= set("-: "):
            continue  # header and separator rows
        if len(cells) != 4:
            problems.append(f"ledger.md line {number}: expected 4 columns, got {len(cells)}")
            continue
        task_id, role, status, attempts = cells
        if status not in STATUSES:
            problems.append(f"ledger.md line {number}: unknown status '{status}'")
        if not attempts.isdecimal():
            problems.append(f"ledger.md line {number}: Attempts must be a number, got '{attempts}'")
        rows[task_id] = {"role": role, "status": status, "attempts": int(attempts) if attempts.isdecimal() else 0}
    return rows, problems


def read(path):
    """File text, or None when the file is missing or unreadable."""
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def run_mode(run_dir):
    match = re.search(r"^Mode: (prototype|production)\s*$", read(run_dir / "spec.md") or "", re.M)
    return match.group(1) if match else None


def load_plan(run_dir):
    text = read(run_dir / "plan.md")
    return parse_plan(text) if text is not None else ([], [])


def check_plan(run_dir):
    """Problems in spec.md and plan.md. Run before the approval gate."""
    problems = []
    if (read(run_dir / "write-check.txt") or "").strip() != "edited":
        problems.append("write-check.txt: the preflight write check has not passed (a subagent must write, then edit, this file)")
    spec = read(run_dir / "spec.md")
    if spec is None:
        problems.append("missing spec.md")
    else:
        if run_mode(run_dir) is None:
            problems.append("spec.md: needs a line 'Mode: prototype' or 'Mode: production'")
        if "## Acceptance criteria" not in spec:
            problems.append("spec.md: needs a '## Acceptance criteria' section")

    plan = read(run_dir / "plan.md")
    if plan is None:
        return problems + ["missing plan.md"]
    if not re.search(r"^Test command: `.+`", plan, re.M):
        problems.append("plan.md: needs a line 'Test command: `<command>`'")
    tasks, parse_problems = parse_plan(plan)
    problems += parse_problems
    if not tasks:
        problems.append("plan.md: has no tasks")

    by_id = {}
    for task in tasks:
        if task["id"] in by_id:
            problems.append(f"plan.md: task id {task['id']} is used twice")
        by_id[task["id"]] = task
        if task["role"] and task["role"] not in BUILDERS:
            problems.append(f"plan.md: {task['id']} Role '{task['role']}' is not a builder role")

    owners = {}  # (wave, file) -> first task id that owns it
    for task in tasks:
        for dep in task["depends"]:
            other = by_id.get(dep)
            if other is None:
                problems.append(f"plan.md: {task['id']} depends on {dep}, which does not exist")
            elif None not in (task["wave"], other["wave"]) and other["wave"] >= task["wave"]:
                problems.append(f"plan.md: {task['id']} depends on {dep}, which is not in an earlier wave")
        for name in task["files"]:
            first = owners.setdefault((task["wave"], name), task["id"])
            if first != task["id"]:
                problems.append(f"plan.md: {first} and {task['id']} both own {name} in wave {task['wave']}")
    return problems


def sections(text):
    """Map each '## Heading' to the text under it."""
    out, current = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            out[current] = ""
        elif current is not None:
            out[current] += line + "\n"
    return out


def check_verdict(run_dir, name):
    text = read(run_dir / "reports" / name)
    if text is None:
        return [f"missing reports/{name}"]
    verdicts = VERDICT_RE.findall(text)
    if len(verdicts) != 1:
        return [f"reports/{name}: needs exactly one Verdict line, found {len(verdicts)}"]
    if verdicts[0] != "pass":
        return [f"reports/{name}: Verdict is not pass"]
    return []


def git(repo_dir, *args):
    """Output of a git command in repo_dir. Paths come back unquoted, so non-ASCII names compare equal."""
    return subprocess.run(
        ["git", "-C", str(repo_dir), "-c", "core.quotePath=false", *args],
        capture_output=True, text=True, check=True,
    ).stdout


def plan_checksum(run_dir):
    return hashlib.sha256((run_dir / "plan.md").read_bytes()).hexdigest()


def seal_plan(run_dir):
    """Record plan.md's checksum in decisions.md. Done at the gate, and again after an approved re-plan."""
    checksum = plan_checksum(run_dir)
    with open(run_dir / "decisions.md", "a") as f:
        f.write(f"Plan checksum: {checksum}\n")
    return checksum


def check_seal(run_dir):
    """plan.md must still be what was last sealed. An unsealed run has nothing to compare."""
    seals = SEAL_RE.findall(read(run_dir / "decisions.md") or "")
    try:
        current = plan_checksum(run_dir)
    except OSError:
        return ["missing plan.md"] if seals else []
    if seals and seals[-1] != current:
        return ["plan.md: changed since it was sealed; only the architect amends it, and the principal seals it again"]
    return []


def changed_files(repo_dir):
    """Uncommitted paths in the working copy, outside the run folder."""
    names = []
    for line in git(repo_dir, "status", "--porcelain", "--untracked-files=all").splitlines():
        name = line[3:].split(" -> ")[-1].strip('"')
        if not name.startswith(".swd/"):
            names.append(name)
    return names


def check_task(run_dir, repo_dir, task_id):
    """Before a returned task is reviewed: every uncommitted change must be owned, and the task's
    own changes must be ones its report claims. A change nobody claims means something wrote
    outside the process, and that is for the user to look at, not for the run to absorb."""
    problems = check_seal(run_dir)
    tasks, _ = load_plan(run_dir)
    task = next((t for t in tasks if t["id"] == task_id), None)
    if task is None:
        return problems + [f"{task_id} is not in plan.md"]

    report_name = f"{task_id}-{task['role']}.md"
    report = read(run_dir / "reports" / report_name)
    claimed = set()
    if report is None:
        problems.append(f"missing reports/{report_name}")
    else:
        for line in sections(report).get("Files changed", "").splitlines():
            entry = line.strip().lstrip("-*").strip().strip("`")
            if entry:  # "path", or "path (what changed)"
                claimed |= {posixpath.normpath(entry), posixpath.normpath(entry.split()[0].strip("`"))}

    owned_by_any = {name for t in tasks for name in t["files"]}
    try:
        changed = changed_files(repo_dir)
    except (OSError, subprocess.CalledProcessError):
        return problems + [f"{repo_dir}: cannot read git status"]
    for name in changed:
        if name not in owned_by_any:
            problems.append(f"{name} changed, but no task owns it")
        elif name in task["files"] and report is not None and name not in claimed:
            problems.append(f"{name} changed, but is not listed under 'Files changed' in reports/{report_name}")
    return problems


def check_commits(run_dir, repo_dir, tasks):
    """Everything is committed, and each T<n>:/W<n>: commit of this run changes only files it owns."""
    # Only this run's commits count: an earlier run in the same project has its own T1.
    base = BASE_RE.search(read(run_dir / "decisions.md") or "")
    try:
        log = git(repo_dir, "log", "--name-only", "--format=%x00%s", *([f"{base.group(1)}..HEAD"] if base else []))
        uncommitted = changed_files(repo_dir)
    except (OSError, subprocess.CalledProcessError):
        return [f"{repo_dir}: cannot read git history"]

    problems = [f"uncommitted change: {name}" for name in uncommitted]

    by_task = {t["id"]: set(t["files"]) for t in tasks}
    by_wave = {}
    for task in tasks:
        by_wave.setdefault(f"W{task['wave']}", set()).update(task["files"])

    for entry in log.split("\0")[1:]:
        lines = [l for l in entry.splitlines() if l.strip()]
        if not lines:
            continue
        subject, changed = lines[0], lines[1:]
        match = COMMIT_RE.match(subject)
        if not match:
            continue
        key = match.group(1)
        owned = by_task.get(key) if key.startswith("T") else by_wave.get(key)
        if owned is None:
            problems.append(f"commit '{subject}': {key} is not in plan.md")
            continue
        for name in changed:
            if name not in owned and not name.startswith(".swd/"):
                problems.append(f"commit '{subject}' changes {name}, which {key} does not own")
    return problems


def check_run(run_dir, repo_dir):
    """Problems in a finished run. Includes everything check_plan reports."""
    problems = check_plan(run_dir) + check_seal(run_dir)
    for name in ("requirement.md", "standards.md", "ledger.md", "decisions.md", "activity.md"):
        if read(run_dir / name) is None:
            problems.append(f"missing {name}")

    if not (run_dir / "dashboard.html").is_file():
        problems.append("missing dashboard.html: start it with swd-dashboard.py --watch --open <run>")

    tasks, _ = load_plan(run_dir)
    mode = run_mode(run_dir)

    rows, ledger_problems = parse_ledger(read(run_dir / "ledger.md") or "")
    problems += ledger_problems
    for task in tasks:
        row = rows.get(task["id"])
        if row is None:
            problems.append(f"ledger.md: no row for {task['id']}")
        elif row["status"] != "done":
            problems.append(f"ledger.md: {task['id']} is {row['status']}, not done")

    for task in tasks:
        if task["role"] not in BUILDERS:
            continue
        name = f"{task['id']}-{task['role']}.md"
        text = read(run_dir / "reports" / name)
        if text is None:
            problems.append(f"missing reports/{name}")
        else:
            found = sections(text)
            for heading in BUILDER_SECTIONS:
                if heading not in found:
                    problems.append(f"reports/{name}: missing section '{heading}'")
                elif heading in EVIDENCE_SECTIONS and found[heading].strip().lower() in PLACEHOLDERS | {""}:
                    problems.append(f"reports/{name}: section '{heading}' has no command output")

    # Reports the mode requires, then every checker report that exists: none may be a fail.
    # A prototype may still hold per-task reviews, for a risky task held to the production bar.
    required = {"final-qa-engineer.md"}
    if mode == "production":
        for task in tasks:
            if task["role"] in BUILDERS:
                required |= {f"{task['id']}-code-reviewer.md", f"{task['id']}-security-reviewer.md"}
        if len(tasks) > 1:  # with one task, its own reviews already covered the whole change
            required |= {"final-code-reviewer.md", "final-security-reviewer.md"}
    else:
        required.add("final-code-reviewer.md")  # a prototype's only review
    present = set()
    for suffix in CHECKER_SUFFIXES:
        present |= {p.name for p in (run_dir / "reports").glob(f"*-{suffix}.md")}
    for name in sorted(required | present):
        problems += check_verdict(run_dir, name)

    activity = read(run_dir / "activity.md")
    if activity is not None:
        events = []  # (event, detail)
        for number, line in enumerate(activity.splitlines(), 1):
            if not line.strip():
                continue
            match = ACTIVITY_RE.match(line)
            if not match or match.group(1) not in EVENTS:
                problems.append(f"activity.md line {number}: expected '- HH:MM:SS <event> <detail>'")
                continue
            events.append((match.group(1), match.group(2) or ""))
        for task in tasks:
            if not any(e == "dispatch" and re.search(rf"\b{task['id']}\b", d) for e, d in events):
                problems.append(f"activity.md: no dispatch line for {task['id']}")
        if not events or events[-1][0] != "done":
            problems.append("activity.md: last line must be a 'done' event")

    return problems + check_commits(run_dir, repo_dir, tasks)


def latest_run(repo_dir):
    runs = repo_dir / ".swd" / "runs"
    folders = sorted(p for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []
    return folders[-1] if folders else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="check spec.md and plan.md only")
    parser.add_argument("--seal", action="store_true", help="check the plan, then record its checksum")
    parser.add_argument("--task", metavar="ID", help="check a returned task's changes before review")
    parser.add_argument("path", type=Path, help="a run folder, or a project folder")
    args = parser.parse_args(argv)

    path = args.path.resolve()
    if path.parent.name == "runs" and path.parent.parent.name == ".swd":
        run_dir, repo_dir = path, path.parents[2]
    else:
        run_dir, repo_dir = latest_run(path), path
    if run_dir is None or not run_dir.is_dir():
        print("no run folder found under .swd/runs/")
        return 1
    if args.seal:
        problems = check_plan(run_dir)
        if not problems:
            print(f"sealed plan.md: {seal_plan(run_dir)}")
    elif args.task:
        problems = check_task(run_dir, repo_dir, args.task)
    elif args.plan:
        problems = check_plan(run_dir)
    else:
        problems = check_run(run_dir, repo_dir)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
