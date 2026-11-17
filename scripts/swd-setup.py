#!/usr/bin/env python3
"""Write the permission rules a project needs for swd runs, into .claude/settings.local.json.

    python3 swd-setup.py --print <project>     show the rules, change nothing
    python3 swd-setup.py <project>             add them (existing settings are kept)
    python3 swd-setup.py --command "npm test" --command "npm run lint" <project>
                                               also allow these project commands

Without these rules, agents working in the background have their file writes and shell
commands held for an approval nobody can give, and the run stalls. The allow rules name each
plugin script a run needs by its full path, one rule per script and Python name, in the plugin's
version folder, so they match that script with any arguments and nothing else; after a plugin
update run setup again. They also allow git and `gh pr`, the project's test command, a few
read-only commands, and edits inside `.swd/` (the run folder and the run's worktree).
Rules are written for the plugin's path as typed and, when it differs, as resolved.
Ask rules make Claude Code ask before a command that starts with python3, python or py and
contains swd-setup. or swd-queue., or that names SWD_UNATTENDED plainly, whatever allow rule
matches it, so that an agent that follows the playbooks cannot change these rules or start a
queue without the user; an agent set on getting round them still can. In an unattended run
nobody can answer, so such a command does not run. Three deny rules make Claude Code refuse the
plain ways of running the plugin's hook, swd-mode.py, by name; a deny rule refuses, it does not
ask. Ask and deny rules name the file up to its dot, so a compiled copy in __pycache__ is caught
too. They match command text only, so they are not a hard boundary.
Setup adds missing rules to `permissions.allow`, `permissions.ask` and `permissions.deny`, and
removes from `permissions.allow` only the rules an earlier version of the plugin wrote, which
--print lists first; every other rule, the user's own included, is kept in order.
A --command, or the test command in .swd/project.md (which any agent in a run may write), is refused
(exit 2, nothing printed or written) when its rule could match every command or not name the program
that runs: it is empty, its first word holds a `*`, or it holds a control character; its first word
is not a plain program name or path (only letters, digits and . _ - + @ / :, not starting with -, so
an assignment, a quote, a backslash or other shell syntax there is refused); or its first word is a
program that runs another command it is given (env, xargs, sudo, doas, eval, exec, and sh, bash, zsh,
dash, ksh, fish or npx alone or followed by an option; the name compared ignoring case). It is
refused too when it names the plugin's own folder, whose scripts setup allows one by one.
The plugin's path, given with --plugin-root or found by setup itself, is refused the same way, before
any command, unless it is absolute (a single / at the start, or on Windows a drive letter and /), has no
. or .. folder, is at least two folders below the root and not the home folder, by either of its
spellings, or above it (on Windows /c/... counting as drive C there), and holds only letters, digits
and . _ - + @ / : ~, because any other path would make the rules match commands or files other than
the plugin's scripts; a space is refused. It is tested by its text as typed before setup opens it,
and then as resolved.
A settings file that is not strict JSON (NaN, Infinity, a number too large for a float and a key
repeated in one object count as not JSON) is refused and left unchanged, and setup never writes one.
settings.local.json is the user's own file for this project and is not meant to be committed.
"""
import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

PYTHONS = ("python3", "python", "py -3")
# The scripts the playbooks and agents run during a run. Not swd-setup.py or swd-queue.py: those ask (ASK).
RUN_SCRIPTS = ("check_run.py", "swd-clean.py", "swd-dashboard.py", "swd-findings.py",
               "swd-log.py", "swd-pr.py", "swd-test.py")

# Read-only commands, plus the three the principal chains into its own commands (echo, cat, mkdir, touch).
READ_ONLY = ["pwd", "ls *", "date *", "wc *", "diff *", "head *", "tail *", "grep *", "find *", "which *",
             "echo *", "cat *", "mkdir *", "touch *"]

# Ask beats allow, so a project's interpreter rule (`Bash(python3 *)`) does not let an agent run the setup or queue
# script unasked; in a `claude -p` run nobody answers, so it does not run. Up to the dot, as DENY, so a run folder named
# `...-swd-setup-fix` keeps its checker calls. Only the three Python names: `*swd-setup.*` would also catch
# `git add scripts/swd-setup.py`. The last one catches `unset SWD_UNATTENDED` and any other command naming the variable
# plainly; a quoted or escaped spelling, or a name built at run time, gets past it.
ASK = ["Bash(python3 *swd-setup.*)", "Bash(python *swd-setup.*)", "Bash(py *swd-setup.*)",
       "Bash(python3 *swd-queue.*)", "Bash(python *swd-queue.*)", "Bash(py *swd-queue.*)",
       "Bash(*SWD_UNATTENDED*)"]

# Deny beats allow, so Claude Code refuses these even under a project's interpreter rule: without them
# `echo '<forged event>' | python3 <plugin>/hooks/swd-mode.py` runs and can turn swd mode off or set the conductor.
# They name the file up to its dot, `swd-mode.`, so the compiled copy Python runs as readily,
# `hooks/__pycache__/swd-mode.cpython-310.pyc`, is refused too. A deny rule refuses, it does not ask, so nothing
# wider: `*swd-mode*` would refuse every checker call on a run folder named `...-swd-mode-fix`, which has no dot.
# They match text, not the file, so a renamed copy or another letter case gets past them; they are not a hard boundary.
# `python *` does not match `python3` (the space is part of the rule); `py *` covers `py -3`.
DENY = ["Bash(python3 *swd-mode.*)", "Bash(python *swd-mode.*)", "Bash(py *swd-mode.*)"]

NOTES = "the test command in .swd/project.md"
WHY = ("a rule's first word must be the command's own name, with no '*' in it, and the command may hold no control "
       "character; '*' there would let the rule match every command")
# A first word with shell syntax in it (an assignment in any form, quotes, escapes) may not be the program that runs.
PLAIN = r"(?!-)[A-Za-z0-9_.+@/:-]+"
NOT_PLAIN = ("a rule's first word must be a plain program name or path, made only of letters, digits and . _ - + @ / : and "
             "not starting with -; quotes, backslashes, =, [, $, backticks, redirections and other shell syntax are refused, "
             "because the rule would then not name the program that runs")
# Programs whose job is to run a command they are given: no ask or deny rule sees the command inside them.
RUNNERS = ("env", "xargs", "sudo", "doas", "eval", "exec")
# The same when bare (they read commands) or given an option (`bash -c ...`, `npx --yes ...`); `bash scripts/test.sh` is fine.
SHELLS = ("sh", "bash", "zsh", "dash", "ksh", "fish", "npx")
RUNS_ANOTHER = ("a rule's first word must name the program that runs, not an assignment or a program that runs another "
                "command it is given (env, sh, bash, zsh, dash, ksh, fish, xargs, sudo, doas, eval, exec, npx), or the rule "
                'would match every command; give the command itself, such as "npm test" or "bash scripts/test.sh"')
# Every per-script, sh and Read rule is built from the plugin's path, so it must be a path no shell or interpreter reads as
# an option, an expansion or code (`-c'...'` became `python3 -c'...'`), and the Read rule must stay below the home folder.
# An allow list, as PLAIN is: two lists of refused characters each missed a value. No space: the shell splits the rule
# there, so `<stdlib>/pdb.py -c` as the root ran any -c an agent added, and the skills type the path unquoted anyway.
# `~` is accepted: it is not expanded inside a word, and Windows short names (RUNNER~1) hold it.
ROOT_CHARS = "._-+@/:~"
ROOT_WHY = ("a plugin path must be absolute (a single / at the start, or on Windows a drive letter and /), at least two "
            "folders below the root and not your home folder or above it, with no . or .. folder, and made only of letters, "
            "digits and . _ - + @ / : ~, with no space; any other path would make the rules match commands or files other "
            "than the plugin's scripts; run setup from a plugin folder whose path is such a path")
VERSION = r"\d+\.\d+\.\d+[^/\s]*"


class Refused(ValueError):
    """A command setup writes no rule for (contract C3)."""


def plugin_prefix(root):
    """The path prefix that matches this plugin's files. An installed plugin lives in a folder
    named for its version, so the prefix stops one level up and survives updates.
    `root` is a path object (a PureWindowsPath works anywhere); the prefix has forward slashes,
    as Claude Code writes the plugin's path in Git Bash on Windows."""
    if root.parent.parent.parent.name == "cache" and re.fullmatch(r"\d+\.\d+\.\d+.*", root.name):
        root = root.parent
    return root.as_posix().rstrip("/") + "/"


def permission_path(prefix):
    """The prefix as a Read rule's absolute path: //Users/... here, //c/Users/... for C:/Users/... on Windows."""
    if re.match(r"[A-Za-z]:/", prefix):
        return "//" + prefix[0].lower() + prefix[2:]
    return "/" + prefix


def plain_root(root, homes, windows=os.name == "nt"):
    """Whether every rule built from `root` names the plugin's own files (contract C1), from its text alone: nothing is
    opened, so a //host root is never reached. The path is absolute (a single / at the start, or, only when `windows`, a
    drive letter and /: elsewhere C:/work/x is relative, and its rule would run a file under the working folder), made
    only of letters, digits and ROOT_CHARS, has no ., .. or empty folder, and its plugin prefix is at least two folders
    below the root and not one of `homes` (the home folder's spellings, as_posix) or above it, case ignored. With
    `windows`, a prefix starting /c/ is read as c:/ for those last two tests, as Git Bash and Claude Code read it."""
    path = root.as_posix()
    prefix = plugin_prefix(root)
    if windows and re.match(r"/[A-Za-z]/", prefix):
        prefix = prefix[1] + ":" + prefix[2:]
    folder = prefix.rstrip("/").casefold()
    return ((path.startswith("/") and not path.startswith("//") or windows and re.match(r"[A-Za-z]:/", path) is not None)
            and all(c.isalnum() or c in ROOT_CHARS for c in path)
            and not {"", ".", ".."} & set(path.split("/")[1:])
            and folder.count("/") >= 2
            and not any(home == folder or home.startswith(folder + "/")
                        for home in (spelling.rstrip("/").casefold() for spelling in homes)))


def check_root(source, root, homes):
    """Raise Refused with C1's line unless plain_root(root, homes)."""
    if not plain_root(root, homes):
        shown = "".join(c if c.isprintable() else c.encode("unicode_escape").decode() for c in root.as_posix())
        raise Refused(f'setup: refused {source} "{shown}": {ROOT_WHY}')


def test_command(project):
    notes = project / ".swd" / "project.md"
    # `.*?`, not `.+?`: an empty value is read, and refused, rather than skipped. The value stays on one line.
    match = re.search(r"^Test command: `(.*?)`", notes.read_text(encoding="utf-8"), re.M) if notes.is_file() else None
    return match.group(1).strip() if match else None


def strict_json(text):
    """Parse settings as strict JSON. NaN, Infinity, a number too large for a float and a key repeated in one object
    raise ValueError, as text that does not parse does: writing such a file back would change it or drop the rules
    under the first copy of a key."""
    def constant(name):
        raise ValueError(f"{name} is not JSON")

    def finite(number):
        if math.isinf(value := float(number)):
            raise ValueError(f"{number} is too large for a float")
        return value

    def unique(pairs):
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("a key is repeated")
        return dict(pairs)

    return json.loads(text, parse_constant=constant, parse_float=finite, object_pairs_hook=unique)


def refuse(source, command, prefixes):
    """Raise Refused when `command`'s rules could match every command or not name the program that runs, or would keep
    the plugin's broad rule because the command names one of `prefixes` (contract C3, four tests in order). The first
    test that refuses decides."""
    words = command.split()
    # The program's own name, case ignored: a case-insensitive file system (macOS, Windows) finds `Env` or `BASH.EXE`.
    name = re.sub(r"\.exe$", "", words[0].rsplit("/", 1)[-1], flags=re.I).lower() if words else ""
    named = [prefix for prefix in prefixes if prefix in command]
    if command.strip() == "" or "*" in words[0] or not command.isprintable():
        why = WHY
    elif not re.fullmatch(PLAIN, words[0]):
        why = NOT_PLAIN
    elif name in RUNNERS or name in SHELLS and (len(words) == 1 or words[1].startswith("-")):
        why = RUNS_ANOTHER
    elif named:
        why = f"it names the plugin's own folder, {named[0]}, whose scripts setup allows one by one; give the project's own command"
    else:
        return
    shown = "".join(c if c.isprintable() else c.encode("unicode_escape").decode() for c in command)
    raise Refused(f'setup: refused {source} "{shown}": {why}')


def rules(project, roots, commands=()):
    """The allow rules, for each of `roots` (the typed root first, then its resolved spelling when it differs)."""
    out = []
    for root in roots:
        folder = root.as_posix().rstrip("/")
        out += [f"Bash({name} {folder}/scripts/{script} *)" for script in RUN_SCRIPTS for name in PYTHONS]
        # The only .sh files the skills run, always through sh, named by the full plugin folder (an installed
        # plugin's version folder included): a * in the path would match any text, so a crafted command could
        # reach swd-python.sh run or install.
        out += [f"Bash(sh {folder}/scripts/swd-python.sh check)",
                f"Bash(sh {folder}/scripts/swd-watch.sh *)",
                f"Read({permission_path(plugin_prefix(root))}**)"]   # standards and skills; a leading // is absolute
    out += [
        "Bash(git *)",
        "Bash(gh pr *)",
        "Edit(/.swd/**)",             # the run folder and the worktree; paths are relative to the project
        "Read(/.swd/**)",
    ]
    out += [f"Bash({command})" for command in READ_ONLY]
    prefixes = [plugin_prefix(root) for root in roots]
    for source, command in [(NOTES, test_command(project)), *(("--command", c) for c in commands)]:
        if command is not None:
            refuse(source, command, prefixes)
            out += [f"Bash({command})", f"Bash({command} *)"]
    return list(dict.fromkeys(out))


def earlier_rules(allow, roots):
    """The entries of `allow`, in order and duplicates included, that an earlier version of the plugin wrote and
    this one does not: the broad rules under the plugin's prefix, and an installed plugin's sh and per-script rules
    of another version folder. Only exact strings count; anything else is the user's and is kept (contract C2)."""
    exact, patterns = set(), []
    for root in roots:
        prefix = plugin_prefix(root)
        exact |= {f"Bash(python3 {prefix}*)", f"Bash(python {prefix}*)", f"Bash(py -3 {prefix}*)", f"Bash({prefix}*)"}
        if prefix != root.as_posix().rstrip("/") + "/":   # an installed plugin, in a version folder
            p = re.escape(prefix)
            names = "|".join(map(re.escape, PYTHONS))
            scripts = "|".join(map(re.escape, RUN_SCRIPTS))
            patterns += [(re.compile(form), root.name) for form in (
                rf"Bash\(sh {p}({VERSION})/scripts/swd-python\.sh check\)",
                rf"Bash\(sh {p}({VERSION})/scripts/swd-watch\.sh \*\)",
                rf"Bash\((?:{names}) {p}({VERSION})/scripts/(?:{scripts}) \*\)")]

    def earlier(entry):
        if entry in exact:
            return True
        return any((m := pattern.fullmatch(entry)) and m.group(1) != current for pattern, current in patterns)

    return [entry for entry in allow if isinstance(entry, str) and earlier(entry)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--print", action="store_true", dest="show", help="show the rules and change nothing")
    parser.add_argument("--command", action="append", default=[], metavar="CMD",
                        help="a project command to allow, such as its test or lint command (repeatable)")
    # The path as typed, never resolved: Bash rules match command text, and the skills type ${CLAUDE_PLUGIN_ROOT}.
    parser.add_argument("--plugin-root", type=Path)
    parser.add_argument("project", type=Path)
    args = parser.parse_args(argv)

    typed = args.plugin_root or Path(os.path.abspath(__file__)).parent.parent
    homes = (Path.home().as_posix(), Path.home().resolve().as_posix())
    project = args.project.resolve()
    try:
        # By its text before exists() or resolve() opens it: on Windows //host/x is a network path, and opening it would
        # reach that host. Only a root that passed is opened, and its resolved spelling is tested the same way.
        check_root("--plugin-root" if args.plugin_root else "the plugin's path", typed, homes)
        roots = [typed]
        resolved = typed.resolve() if typed.exists() else typed
        if resolved.as_posix() != typed.as_posix():
            check_root("the plugin's resolved path", resolved, homes)
            roots.append(resolved)
        wanted = rules(project, roots, args.command)
    except Refused as refused:
        print(refused, file=sys.stderr)
        return 2
    settings = project / ".claude" / "settings.local.json"

    data = {}
    if settings.exists():
        try:
            data = strict_json(settings.read_text(encoding="utf-8"))
        except ValueError:   # not strict JSON, or not UTF-8
            data = None
    permissions = data.setdefault("permissions", {}) if isinstance(data, dict) else None
    valid = isinstance(permissions, dict) and all(isinstance(permissions.get(key, []), list) for key in ("allow", "ask", "deny"))
    if valid:
        wanted_set = set(wanted)
        # A rule this run wants is never old, or it would be removed and added again on every run.
        old = [rule for rule in earlier_rules(permissions.get("allow", []), roots) if rule not in wanted_set]
        missing = {}
        for key, rules_wanted in (("allow", wanted), ("ask", ASK), ("deny", DENY)):
            have = {rule for rule in permissions.get(key, []) if isinstance(rule, str)}   # entries may be unhashable
            missing[key] = [rule for rule in rules_wanted if rule not in have]
        added = sum(len(rules_missing) for rules_missing in missing.values())

    if args.show:
        print(f"Rules for {settings}:")
        for heading, listed in ((None, wanted),
                                ("Ask rules, so Claude Code asks you before a command runs the setup or queue script,"
                                 " or names SWD_UNATTENDED:", ASK),
                                ("Deny rules, so Claude Code refuses the plain ways of running the plugin's hook by name:", DENY),
                                ("Rules an earlier version of the plugin wrote, which setup removes:", old if valid else [])):
            if heading and listed:
                print(heading)
            for rule in listed:
                print("  " + rule)
        if not valid:
            print(f"Not in place: {settings} is not valid JSON; fix or remove it, then run setup again.")
        elif added or old:
            print(f"Not in place: {settings} is missing {added} of the rules above and still holds {len(old)} rules"
                  " an earlier version wrote; run /swd:setup.")
        else:
            print(f"In place: {settings} holds every rule above and none an earlier version wrote.")
        return 0

    invalid = f"{settings} is not valid JSON; fix or remove it, then run setup again"
    if not valid:
        print(invalid, file=sys.stderr)
        return 1
    if not (added or old):
        print("setup: nothing to add")   # the file is left exactly as it is
        return 0
    if old:
        old_set = set(old)
        permissions["allow"] = [rule for rule in permissions["allow"] if not (isinstance(rule, str) and rule in old_set)]
    for key, rules_missing in missing.items():
        if rules_missing:
            permissions.setdefault(key, []).extend(rules_missing)
    try:
        text = json.dumps(data, indent=2, allow_nan=False) + "\n"
    except ValueError:   # never write a file that is not JSON
        print(invalid, file=sys.stderr)
        return 1
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(text, encoding="utf-8")
    line = f"setup: {added} rules added to {settings}"
    print(f"{line}; {len(old)} rules an earlier version of the plugin wrote removed" if old else line)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
