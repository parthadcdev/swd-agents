#!/usr/bin/env python3
"""Validate an swd run folder.

    python3 check_run.py --plan <run_dir>      check spec.md and plan.md only (before the gate)
    python3 check_run.py --seal <run_dir>      check the plan, the 'Plan judged:' line and staffing.md, then record the plan's checksum in decisions.md
    python3 check_run.py --task T1 <run_dir>   check a returned task's changes before review
    python3 check_run.py <run_dir>             check a finished run (a sealed run is not asked for '## Outcome'; an unsealed one is)
    python3 check_run.py --finish <run_dir>    check the run was delivered and cleaned up

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
TASK_FIELDS = ("Role", "Wave", "Files", "Depends", "Check", "Outcome")
MODELS = ("haiku", "sonnet", "opus", "fable")
EFFORTS = ("low", "medium", "high", "xhigh")
BUILDER_SECTIONS = ("Summary", "Files changed", "Test first (failing)", "Test after (passing)", "Complexity", "Concerns")
CHECKER_SUFFIXES = ("code-reviewer", "security-reviewer", "qa-engineer")
PLACEHOLDERS = {"todo", "tbd", "n/a", "na", "none", "...", "-"}  # not evidence
VERDICT_RE = re.compile(r"^Verdict: (pass|fail)\s*$", re.M)
EVIDENCE_SECTIONS = ("Test first (failing)", "Test after (passing)")

TASK_RE = re.compile(r"^### (T\d+): (.+)$")
TASK_LIKE_RE = re.compile(r"^#+\s*T(ask)?\s*\d+\b", re.I)  # a heading that was meant to be a task
BASE_RE = re.compile(r"^Base commit: (\S+)", re.M)
FINISHES = ("merge-push", "pr", "branch")
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


def decision(run_dir, key):
    """The value of the last 'Key: value' line in decisions.md, or None."""
    values = re.findall(rf"^{re.escape(key)}: (.+?)\s*$", read(run_dir / "decisions.md") or "", re.M)
    return values[-1] if values else None


def work_dir(run_dir, default):
    """Where the run's code is: its worktree while that exists, otherwise the given folder."""
    path = decision(run_dir, "Worktree")
    return Path(path) if path and Path(path).is_dir() else default


def check_finish_choice(run_dir):
    if decision(run_dir, "Finish") not in FINISHES:
        return ["decisions.md: needs a line 'Finish: merge-push', 'Finish: pr' or 'Finish: branch'"]
    return []


def check_staffing(run_dir):
    """Before the seal: the plan is judged, and staffing.md gives every task its agent, model and effort."""
    problems = []
    lines = (read(run_dir / "decisions.md") or "").splitlines()
    judged = [i for i, l in enumerate(lines) if l.startswith("Plan judged:") and l[12:].strip().lower() not in PLACEHOLDERS | {""}]
    sealed = [i for i, l in enumerate(lines) if SEAL_RE.match(l)]
    if not judged:
        problems.append("decisions.md: needs a line 'Plan judged: ...'; the principal judges the plan against the spec before the gate")
    elif sealed and judged[-1] < sealed[-1]:
        problems.append("decisions.md: the 'Plan judged:' line is older than the last 'Plan checksum:'; "
                        "judge the amended plan and add a new 'Plan judged: ...' line")
    text = read(run_dir / "staffing.md")
    if text is None:
        return problems + ["missing staffing.md: the agent, model and effort for each task"]
    agents = {}  # first cell -> Agent cell
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] == "For" or set(cells[0]) <= set("-: "):
            continue  # header and separator rows
        if len(cells) != 5:
            problems.append(f"staffing.md line {number}: expected 5 columns, got {len(cells)}")
            continue
        agents[cells[0]] = cells[1]
        if cells[2] not in MODELS:
            problems.append(f"staffing.md line {number}: Model must be one of {', '.join(MODELS)}, got '{cells[2]}'")
        if cells[3] not in EFFORTS:
            problems.append(f"staffing.md line {number}: Effort must be one of {', '.join(EFFORTS)}, got '{cells[3]}'")
    for task in load_plan(run_dir)[0]:
        if task["id"] not in agents:
            problems.append(f"staffing.md: no row for {task['id']}")
        elif agents[task["id"]] != task["role"]:
            problems.append(f"staffing.md: {task['id']} Agent '{agents[task['id']]}' is not the plan's Role '{task['role']}'")
    return problems


def run_mode(run_dir):
    match = re.search(r"^Mode: (prototype|production|quick)\s*$", read(run_dir / "spec.md") or "", re.M)
    return match.group(1) if match else None


def load_plan(run_dir):
    text = read(run_dir / "plan.md")
    return parse_plan(text) if text is not None else ([], [])


def check_plan(run_dir, outcome=True):
    """Problems in spec.md and plan.md. Run before the approval gate.

    outcome=False leaves out the two Outcome rules, so a plan from before they existed still passes."""
    problems = []
    for key in ("Base branch", "Branch", "Worktree"):
        if not decision(run_dir, key):
            problems.append(f"decisions.md: needs a line '{key}: ...'; the run works on its own branch in its own worktree")
    if not (read(run_dir.parent.parent / "project.md") or "").strip():
        problems.append("missing .swd/project.md: the project's notes (test command, conventions, layout)")
    if not decision(run_dir, "Housekeeping"):
        problems.append("decisions.md: needs a 'Housekeeping:' line; run swd-clean.py <run> in preflight")
    if (read(run_dir / "write-check.txt") or "").strip() != "edited":
        problems.append("write-check.txt: the preflight write check has not passed (a subagent must write, then edit, this file)")
    spec = read(run_dir / "spec.md")
    if spec is None:
        problems.append("missing spec.md")
    else:
        if run_mode(run_dir) is None:
            problems.append("spec.md: needs a line 'Mode: quick', 'Mode: prototype' or 'Mode: production'")
        if "## Acceptance criteria" not in spec:
            problems.append("spec.md: needs a '## Acceptance criteria' section")

    plan = read(run_dir / "plan.md")
    if plan is None:
        return problems + ["missing plan.md"]
    if not re.search(r"^Test command: `.+`", plan, re.M):
        problems.append("plan.md: needs a line 'Test command: `<command>`'")
    if outcome:
        section = []  # the section's text up to the first task heading, which a plan with no '## Tasks' puts right below it
        for line in sections(plan).get("Outcome", "").splitlines():
            if TASK_RE.match(line) or TASK_LIKE_RE.match(line):
                break
            section.append(line)
        if "\n".join(section).strip().lower() in PLACEHOLDERS | {""}:
            problems.append("plan.md: needs a '## Outcome' section showing the finished result as it will really appear")
    tasks, parse_problems = parse_plan(plan)
    if not outcome:
        parse_problems = [p for p in parse_problems if not p.endswith(" is missing '- Outcome:'")]
    problems += parse_problems
    if not tasks:
        problems.append("plan.md: has no tasks")
    if run_mode(run_dir) == "quick" and len(tasks) > 1:
        problems.append("plan.md: quick mode is for one task; use prototype or production mode for more")

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
    before = read(run_dir / "decisions.md") or ""
    with open(run_dir / "decisions.md", "a") as f:
        # A last line with no newline would swallow the checksum, and the seal would never be read back.
        f.write(("" if before.endswith("\n") or not before else "\n") + f"Plan checksum: {checksum}\n")
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
    """Problems in a finished run. Includes what check_plan reports; a sealed run is not held to the Outcome rules, which --plan and --seal enforce."""
    sealed = bool(SEAL_RE.search(read(run_dir / "decisions.md") or ""))
    problems = check_plan(run_dir, outcome=not sealed) + check_seal(run_dir)
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
    # Quick mode has one checker: its final code review also runs the tests and the acceptance criteria.
    required = set() if mode == "quick" else {"final-qa-engineer.md"}
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

    # What swd-test.py recorded. The script writes these, so a failing run before a passing one is
    # proof the test came first, and a passing last run is proof the work passes now.
    def exits(label):
        codes = []
        for path in sorted((run_dir / "evidence").glob(f"{label}-[0-9]*.txt")):
            match = re.search(r"^Exit: (-?\d+)\s*$", read(path) or "", re.M)
            codes.append(int(match.group(1)) if match else None)
        return codes

    for task in tasks:
        if task["role"] not in BUILDERS:
            continue
        codes = exits(task["id"])
        if 0 not in codes or not any(code not in (0, None) for code in codes[:codes.index(0)]):
            problems.append(f"evidence: {task['id']} has no failing run recorded before a passing one; "
                            "builders run their check with swd-test.py")
        elif codes[-1] != 0:
            problems.append(f"evidence: {task['id']}'s last recorded run did not pass")
    suites = ["final"]
    if mode == "production":
        waves = sorted({t["wave"] for t in tasks if t["wave"] is not None})
        suites = [f"wave-{wave}" for wave in waves[:-1]] + suites   # the last wave is covered by final
    for label in suites:
        codes = exits(label)
        if not codes:
            problems.append(f"evidence: no {label} run of the test suite recorded; run swd-test.py <run> {label}")
        elif codes[-1] != 0:
            problems.append(f"evidence: the last {label} run of the test suite did not pass")

    # Defects the run saw and left must be in the project's backlog, where the next run can find them.
    backlog = read(run_dir.parent.parent / "findings.md") or ""
    for finding in re.findall(r"^Finding: (.+?)\s*$", read(run_dir / "decisions.md") or "", re.M):
        if finding not in backlog:
            problems.append("a Finding is not in .swd/findings.md: run swd-findings.py <run>")
            break

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


def check_finish(run_dir, project_dir):
    """After delivery: the worktree is gone and the recorded finish really happened."""
    problems = check_finish_choice(run_dir)
    if problems:
        return problems
    finish = decision(run_dir, "Finish")
    branch, base, work = (decision(run_dir, key) for key in ("Branch", "Base branch", "Worktree"))
    if not (branch and base):
        return ["decisions.md: needs 'Branch:' and 'Base branch:' lines"]
    if work and Path(work).exists():
        problems.append(f"worktree {work} is still there; remove it with git worktree remove")

    def ref(name):
        try:
            return git(project_dir, "rev-parse", "--verify", "--quiet", name).strip() or None
        except (OSError, subprocess.CalledProcessError):
            return None

    def contains(ancestor, descendant):
        try:
            git(project_dir, "merge-base", "--is-ancestor", ancestor, descendant)
            return True
        except (OSError, subprocess.CalledProcessError):
            return False

    try:
        has_remote = "origin" in git(project_dir, "remote").split()
    except (OSError, subprocess.CalledProcessError):
        return problems + [f"{project_dir}: cannot read git remotes"]
    branch_sha, base_sha = ref(f"refs/heads/{branch}"), ref(f"refs/heads/{base}")

    if finish == "merge-push":
        base_commit = BASE_RE.search(read(run_dir / "decisions.md") or "")
        if branch_sha and base_sha and contains(branch_sha, base_sha):
            problems.append(f"{branch} is merged; delete it with git branch -d")
        elif branch_sha or (base_commit and base_sha and base_sha.startswith(base_commit.group(1))):
            problems.append(f"{branch} is not merged into {base}")
        if has_remote and base_sha != ref(f"refs/remotes/origin/{base}"):
            problems.append(f"{base} is not pushed to origin")
    elif not branch_sha:
        problems.append(f"{branch} is gone; 'Finish: {finish}' keeps the branch")
    elif finish == "pr":
        if not has_remote:
            problems.append("'Finish: pr' needs a remote; without one, record 'Finish: branch'")
        elif ref(f"refs/remotes/origin/{branch}") != branch_sha:
            problems.append(f"{branch} is not pushed to origin")
    return problems


def latest_run(repo_dir):
    runs = repo_dir / ".swd" / "runs"
    folders = sorted(p for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []
    return folders[-1] if folders else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="check spec.md and plan.md only")
    parser.add_argument("--seal", action="store_true", help="check the plan, the Plan judged line and staffing.md, then record the plan's checksum")
    parser.add_argument("--task", metavar="ID", help="check a returned task's changes before review")
    parser.add_argument("--finish", action="store_true", help="check the run was delivered and cleaned up")
    parser.add_argument("path", type=Path, help="a run folder, or a project folder")
    args = parser.parse_args(argv)

    path = args.path.resolve()
    if path.parent.name == "runs" and path.parent.parent.name == ".swd":
        run_dir, project_dir = path, path.parents[2]
    else:
        run_dir, project_dir = latest_run(path), path
    if run_dir is None or not run_dir.is_dir():
        print("no run folder found under .swd/runs/")
        return 1
    repo_dir = work_dir(run_dir, project_dir)  # git checks look at the run's worktree, not the user's copy
    if args.finish:
        problems = check_finish(run_dir, project_dir)
    elif args.seal:
        problems = check_plan(run_dir) + check_finish_choice(run_dir) + check_staffing(run_dir)
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
