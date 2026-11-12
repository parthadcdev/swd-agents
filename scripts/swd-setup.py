#!/usr/bin/env python3
"""Write the permission rules a project needs for swd runs, into .claude/settings.local.json.

    python3 swd-setup.py --print <project>     show the rules, change nothing
    python3 swd-setup.py <project>             add them (existing settings are kept)
    python3 swd-setup.py --command "npm test" --command "npm run lint" <project>
                                               also allow these project commands

Without these rules, agents working in the background have their file writes and shell
commands held for an approval nobody can give, and the run stalls. The rules allow: the
plugin's own scripts, git and `gh pr`, the project's test command, a few read-only commands,
and edits inside `.swd/` (the run folder and the run's worktree, where all changes are made).
settings.local.json is the user's own file for this project and is not meant to be committed.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Read-only commands, plus the three the principal chains into its own commands (echo, cat, mkdir).
READ_ONLY = ["pwd", "ls *", "date *", "wc *", "diff *", "head *", "tail *", "grep *", "find *", "which *",
             "echo *", "cat *", "mkdir *"]


def plugin_prefix(root):
    """The path prefix that matches this plugin's files. An installed plugin lives in a folder
    named for its version, so the prefix stops one level up and survives updates."""
    root = Path(root)
    if root.parent.parent.parent.name == "cache" and re.fullmatch(r"\d+\.\d+\.\d+.*", root.name):
        root = root.parent
    return str(root) + "/"


def test_command(project):
    notes = project / ".swd" / "project.md"
    match = re.search(r"^Test command: `(.+?)`", notes.read_text(), re.M) if notes.is_file() else None
    return match.group(1).strip() if match else None


def rules(project, plugin_root, commands=()):
    prefix = plugin_prefix(plugin_root)
    out = [
        f"Bash(python3 {prefix}*)",   # check_run.py, swd-clean.py, swd-dashboard.py, ...
        f"Bash({prefix}*)",           # swd-log.sh, swd-watch.sh
        f"Read(/{prefix}**)",         # standards and scripts; a leading // marks an absolute path
        "Bash(git *)",
        "Bash(gh pr *)",
        "Edit(/.swd/**)",             # the run folder and the worktree; paths are relative to the project
        "Read(/.swd/**)",
    ]
    out += [f"Bash({command})" for command in READ_ONLY]
    for command in [test_command(project), *commands]:
        if command:
            out += [f"Bash({command})", f"Bash({command} *)"]
    return list(dict.fromkeys(out))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--print", action="store_true", dest="show", help="show the rules and change nothing")
    parser.add_argument("--command", action="append", default=[], metavar="CMD",
                        help="a project command to allow, such as its test or lint command (repeatable)")
    parser.add_argument("--plugin-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("project", type=Path)
    args = parser.parse_args(argv)

    project = args.project.resolve()
    wanted = rules(project, args.plugin_root, args.command)
    settings = project / ".claude" / "settings.local.json"
    if args.show:
        print(f"Rules for {settings}:")
        for rule in wanted:
            print("  " + rule)
        return 0

    data = {}
    if settings.exists():
        try:
            data = json.loads(settings.read_text())
        except ValueError:
            data = None
        if not isinstance(data, dict):
            print(f"{settings} is not valid JSON; fix or remove it, then run setup again", file=sys.stderr)
            return 1
    permissions = data.setdefault("permissions", {})
    allow = permissions.setdefault("allow", [])
    added = [rule for rule in wanted if rule not in allow]
    allow.extend(added)
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(data, indent=2) + "\n")
    print(f"setup: {len(added)} rules added to {settings}" if added else "setup: nothing to add")
    return 0


if __name__ == "__main__":
    sys.exit(main())
