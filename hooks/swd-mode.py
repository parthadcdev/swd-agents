#!/usr/bin/env python3
"""UserPromptExpansion, UserPromptSubmit and PreModelSwitch hook: swd mode, and keeping the
principal on the models the project's conductor setting accepts.

Reads the hook's JSON from stdin and dispatches on `hook_event_name`.

The conductor setting is `fable` (the default: Fable 5.2 alone) or `opus` (Fable 5.2 or Opus 5.5),
one per project, in ~/.claude/swd-conductor/<sha256 of the project key>. The key is computed from
the event's `cwd` text alone: the part before `.swd/worktrees/<name>`, otherwise the folder itself;
text with a `..` component has no key and reads as `fable`. Nothing is resolved, no link is followed and nothing in the project is opened or listed. The setting
is `opus` only when the entry is a regular file holding `opus`; anything else, and any error, is
`fable`.

UserPromptExpansion: when the user types `/swd:build`, `/swd:follow` or `/swd:on` (the event's
`command_name`), swd mode turns on for that session. When the user types `/swd:conductor [fable|opus]`
it stores, refuses or reads the setting for the project of `cwd`, whatever the session. Only this
event turns swd mode on or stores the setting, because it fires for a command the user typed, while a
prompt also carries text the user did not type, such as an agent's report. This path never exits
non-zero: exit 2 would block the user's command.

UserPromptSubmit (and any other event): `/swd:off` or "stop swd" turn swd mode off only as the
whole prompt; when the flag cannot be deleted, it says so and names the file. The flag counts
only as a regular file. While it is on, every prompt gets a short reminder added to the session's
context: route code changes through the swd team, and the models the principal runs on in this
project. This path never exits non-zero.

PreModelSwitch: cancels a switch from an accepted model to one that is not (exit 2, the reason on
stderr) only while swd mode is on for the session. It reads no file in the project, only the
session's swd-mode flag and the project's conductor entry under ~/.claude. Anything else, bad input,
any error, or no decision within LIMIT_SECONDS lets the switch through silently.
"""
import hashlib
import json
import os
import re
import stat
import sys
import threading
import time
from pathlib import Path, PurePath

STATE = Path.home() / ".claude" / "swd-mode"
CONDUCTOR = Path.home() / ".claude" / "swd-conductor"
STALE_SECONDS = 7 * 24 * 60 * 60
MODEL_NAME = "Fable 5.2"
MODEL_ID = "claude-fable-5-2"
OPUS_NAME = "Opus 5.5"
OPUS_ID = "claude-opus-5-5"
LIMIT_SECONDS = 3  # at most half the PreModelSwitch timeout in hooks.json

ON = f"""swd mode: on
This session is in swd mode. Any request that creates or changes this project's code, tests,
configuration or documentation goes through the swd team: invoke the `swd:build` skill with
the request as the requirement, and do not make the change yourself. Answer questions,
explanations, reviews and status or git requests directly. If an swd run is already in
progress, carry on under its playbook. The user leaves swd mode by sending "stop swd" or
/swd:off as a message on its own.
The principal of an swd run runs on {MODEL_NAME}. Check which model you are running on, only from your own system and session information, at the start of every turn and again before every action that changes anything outside your own reply, such as a dispatch, ruling, commit, merge, push, reply on a pull request or write to the run folder; if you cannot tell, it is not {MODEL_NAME}; if it is not {MODEL_NAME}, do no principal work and change nothing for the run outside your own reply: say which model you are on and that the run continues once the user runs /model fable and sends a message, and stop."""

ON_OPUS = ON.rsplit("\n", 1)[0] + f"""
The principal of an swd run in this project runs on {MODEL_NAME} or {OPUS_NAME} (conductor setting: opus). Check which model you are running on, only from your own system and session information, at the start of every turn and again before every action that changes anything outside your own reply, such as a dispatch, ruling, commit, merge, push, reply on a pull request or write to the run folder; if you cannot tell, it is neither; if it is neither {MODEL_NAME} nor {OPUS_NAME}, do no principal work and change nothing for the run outside your own reply: say which model you are on and that the run continues once the user runs /model fable or /model opus and sends a message, and stop. On {OPUS_NAME}, dispatch the Fable judge where the build playbook says."""

OFF = """swd mode: off
swd mode has been turned off for this session. Handle requests normally from here on; the
swd team is used again only when the user runs /swd:build, /swd:follow or /swd:on."""

OFF_FAILED = f"""swd mode: still on
The swd-mode hook could not delete its flag file, so swd mode is still on and switches away from the principal's models are still cancelled. Tell the user to delete this file by hand, or to start a new session (not a resumed one): {{path}}"""

ON_COMMANDS = ("swd:build", "swd:follow", "swd:on")
CONDUCTOR_COMMAND = "swd:conductor"
ACCEPTED = {"fable": (MODEL_ID,), "opus": (MODEL_ID, OPUS_ID)}
MODELS = {"fable": MODEL_NAME, "opus": f"{MODEL_NAME} or {OPUS_NAME}"}
REFUSAL = {
    "fable": (f"swd: this session stays on {MODEL_NAME}, because the principal runs on it and swd mode is on "
              "in this session. To switch anyway, run /swd:off."),
    "opus": (f"swd: this session stays on {MODEL_NAME} or {OPUS_NAME}, because the principal of this project "
             "runs on them and swd mode is on in this session. To switch anyway, run /swd:off."),
}
NOT_TOLD = f"The hook was not told this session's folder, so only {MODEL_NAME} may conduct here."


def main():
    # Claude Code sends UTF-8; on Windows Python would read cp1252 and print a non-ASCII path in cp1252.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        event = json.load(sys.stdin)
    except (ValueError, RecursionError):
        return
    if not isinstance(event, dict):
        return
    name = event.get("hook_event_name")
    if name == "PreModelSwitch":
        model_switch(event)
    elif name == "UserPromptExpansion":
        expansion(event)
    else:
        prompt(event)


def flag_for(event):
    """The session's swd-mode flag file, or None when the session id is unusable."""
    session = str(event.get("session_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session):
        return None  # no usable session id, and never a path
    return STATE / session


def project_key(folder):
    """The project a folder belongs to, from its text alone, or None when the text is unusable."""
    if not isinstance(folder, str) or not folder or not PurePath(folder).is_absolute():
        return None
    parts = PurePath(folder).parts
    if ".." in parts:  # text that climbs out of a worktree must not borrow another project's setting
        return None
    for i in range(1, len(parts) - 2):  # a run's worktree, .swd/worktrees/<name>, has its project's setting
        if parts[i] == ".swd" and parts[i + 1] == "worktrees":
            return str(PurePath(*parts[:i]))
    return str(PurePath(folder))


def conductor_entry(key):
    return CONDUCTOR / hashlib.sha256(os.path.normcase(key).encode("utf-8", "surrogatepass")).hexdigest()


def conductor_setting(folder):
    """"opus" or "fable" for the project of this folder. Never raises: anything unusable is "fable"."""
    try:
        key = project_key(folder)
        if key is None:
            return "fable"
        entry = conductor_entry(key)
        if not stat.S_ISREG(os.lstat(entry).st_mode):
            return "fable"
        # O_NONBLOCK: an entry swapped for a FIFO after the lstat must not stall the read.
        fd = os.open(entry, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        try:
            return "opus" if os.read(fd, 16).strip() == b"opus" else "fable"
        finally:
            os.close(fd)
    except Exception:
        return "fable"


def store_conductor(key, value):
    entry = conductor_entry(key)
    CONDUCTOR.mkdir(parents=True, exist_ok=True)
    entry.unlink(missing_ok=True)  # removes a link itself, never its target
    fd = os.open(entry, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, (value + "\n").encode("ascii"))
    finally:
        os.close(fd)


def shown(text):
    """Text with every line break and control character as "?", so a folder name cannot add a line."""
    return re.sub("[\x00-\x1f\x7f-\x9f  ]", "?", text)


def where(key, setting):
    if key is None:
        return NOT_TOLD
    return f"{MODELS[setting]} may conduct swd runs in {shown(key)}, its .swd/worktrees included."


def conductor_command(event):
    """/swd:conductor [fable|opus]: two lines on stdout. The value typed is never echoed."""
    folder = event.get("cwd")
    key = project_key(folder)
    current = conductor_setting(folder)
    value = str(event.get("command_args") or "").strip().lower()
    if not value:
        print(f"swd conductor: {current}\n{where(key, current)}")
    elif value not in ACCEPTED:
        print(f"swd conductor: refused, still {current}\n"
              f"The value must be fable or opus; nothing was stored. {where(key, current)}")
    elif key is None:
        print(f"swd conductor: not stored, still fable\n{NOT_TOLD}")
    else:
        try:
            store_conductor(key, value)
        except OSError as error:
            current = conductor_setting(folder)
            print(f"swd conductor: not stored, still {current}\nThe hook could not write "
                  f"{shown(str(conductor_entry(key)))}: {shown(str(error.strerror or error))}. {where(key, current)}")
        else:
            print(f"swd conductor: set to {value}\n{where(key, value)}")


def reminder(event):
    return ON_OPUS if conductor_setting(event.get("cwd")) == "opus" else ON


def expansion(event):
    if event.get("command_name") == CONDUCTOR_COMMAND:  # needs no session and leaves swd mode alone
        conductor_command(event)
        return
    flag = flag_for(event)
    if flag is None:
        return
    if str(event.get("command_name") or "") not in ON_COMMANDS:
        return
    was_on = flag.is_file()
    STATE.mkdir(parents=True, exist_ok=True)
    flag.unlink(missing_ok=True)  # removes a link itself, never its target
    os.close(os.open(flag, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    for old in STATE.iterdir():  # sessions that ended without turning it off
        if time.time() - old.stat().st_mtime > STALE_SECONDS:
            old.unlink()
    if not was_on:  # when it was on, UserPromptSubmit has just printed the reminder for this message
        print(reminder(event))


def prompt(event):
    flag = flag_for(event)
    if flag is None:
        return
    text = str(event.get("prompt") or "").strip()
    if text.lower() in ("stop swd", "/swd:off"):  # whole prompt only: quoted words must not turn it off
        if flag.is_file():
            try:
                flag.unlink()
            except OSError:
                print(OFF_FAILED.format(path=flag))
            else:
                print(OFF)
        return
    if flag.is_file():
        print(reminder(event))


def model_switch(event):
    # Claude Code cancels a switch whose hook outlives its timeout, so give up first and allow it.
    # shortcut: the limit cannot end a process stuck in an uninterruptible kernel wait or one whose interpreter has not started, upgrade if a hung home folder is reported locking switches
    watchdog = threading.Timer(LIMIT_SECONDS, os._exit, (0,))
    watchdog.daemon = True
    watchdog.start()
    try:
        message = switch_refusal(event)
    except Exception:
        return  # fail open
    if message:
        watchdog.cancel()
        print(message, file=sys.stderr)
        sys.exit(2)


def is_model(model_id, model):
    return re.search(re.escape(model) + r"(?!\d)", model_id.lower()) is not None


def switch_refusal(event):
    """The message that cancels this switch, or None to allow it."""
    from_model, to_model = event.get("from_model"), event.get("to_model")
    if not isinstance(from_model, str) or not isinstance(to_model, str):
        return None
    if not from_model.strip() or not to_model.strip():
        return None  # a blank model id is bad input, not a model the user chose
    setting = conductor_setting(event.get("cwd"))  # total: a bad cwd is "fable", so it can only cancel more
    accepted = ACCEPTED[setting]
    if not any(is_model(from_model, m) for m in accepted) or any(is_model(to_model, m) for m in accepted):
        return None
    flag = flag_for(event)
    if flag is None or not flag.is_file():
        return None
    return REFUSAL[setting]


if __name__ == "__main__":
    try:
        main()
    except OSError:
        pass
