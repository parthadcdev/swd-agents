"""Plugin structure checks. Run from the repo root: python3 -m unittest tests.test_structure"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FILES = [".claude-plugin/plugin.json", "README.md"]
REQUIRED_AGENTS: list[str] = []
AGENT_SECTIONS = ["## Responsibility", "## Inputs", "## Process", "## Report", "## Never"]


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


if __name__ == "__main__":
    unittest.main()
