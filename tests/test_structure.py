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
    "standards/prototype.md",
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
        known = {p.stem for p in agent_files()} | {"build"}
        for folder in ("skills", "standards"):
            for path in (ROOT / folder).rglob("*.md"):
                for name in re.findall(r"swd:([a-z-]+)", path.read_text()):
                    with self.subTest(file=str(path.relative_to(ROOT)), ref=name):
                        self.assertIn(name, known)

    def test_standards_have_required_sections(self):
        for mode in ("production", "prototype"):
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
        for needle in ("activity.md", "swd-watch.sh", "swd-log.sh", "swd-dashboard.py --watch --open", "HERDR_PANE_ID"):
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
        for path in agent_files():
            with self.subTest(agent=path.name):
                self.assertIn("`Work in:`", path.read_text())


if __name__ == "__main__":
    unittest.main()
