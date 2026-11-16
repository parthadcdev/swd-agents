#!/usr/bin/env python3
"""UserPromptExpansion, UserPromptSubmit and PreModelSwitch hook: swd mode, and keeping the
principal on Fable 5.2.

Reads the hook's JSON from stdin and dispatches on `hook_event_name`.

UserPromptExpansion: when the user types `/swd:build`, `/swd:follow` or `/swd:on` (the event's
`command_name`), swd mode turns on for that session. Only this event turns it on, because it fires
for a command the user typed, while a prompt also carries text the user did not type, such as an
agent's report. This path never exits non-zero: exit 2 would block the user's command.

UserPromptSubmit (and any other event): `/swd:off` or "stop swd" turn swd mode off only as the
whole prompt; when the flag cannot be deleted, it says so and names the file. The flag counts
only as a regular file. While it is on, every prompt gets a short reminder added to the session's
context: route code changes through the swd team, and the principal runs on Fable 5.2. This path
never exits non-zero.

PreModelSwitch: cancels a switch from Fable 5.2 to another model (exit 2, the reason on stderr)
only while swd mode is on for the session. It reads no file in the project, only the session's
swd-mode flag. Anything else, bad input, any error, or no decision within LIMIT_SECONDS lets the
switch through silently.
"""
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

STATE = Path.home() / ".claude" / "swd-mode"
STALE_SECONDS = 7 * 24 * 60 * 60
MODEL_NAME = "Fable 5.2"
MODEL_ID = "claude-fable-5-2"
LIMIT_SECONDS = 3  # at most half the PreModelSwitch timeout in hooks.json

ON = f"""swd mode: on
This session is in swd mode. Any request that creates or changes this project's code, tests,
configuration or documentation goes through the swd team: invoke the `swd:build` skill with
the request as the requirement, and do not make the change yourself. Answer questions,
explanations, reviews and status or git requests directly. If an swd run is already in
progress, carry on under its playbook. The user leaves swd mode by sending "stop swd" or
/swd:off as a message on its own.
The principal of an swd run runs on {MODEL_NAME}. Check which model you are running on, only from your own system and session information, at the start of every turn and again before every action that changes anything outside your own reply, such as a dispatch, ruling, commit, merge, push, reply on a pull request or write to the run folder; if you cannot tell, it is not {MODEL_NAME}; if it is not {MODEL_NAME}, do no principal work and change nothing for the run outside your own reply: say which model you are on and that the run continues once the user runs /model fable and sends a message, and stop."""

OFF = """swd mode: off
swd mode has been turned off for this session. Handle requests normally from here on; the
swd team is used again only when the user runs /swd:build, /swd:follow or /swd:on."""

OFF_FAILED = f"""swd mode: still on
The swd-mode hook could not delete its flag file, so swd mode is still on and switches away from {MODEL_NAME} are still cancelled. Tell the user to delete this file by hand, or to start a new session (not a resumed one): {{path}}"""

ON_COMMANDS = ("swd:build", "swd:follow", "swd:on")


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


def expansion(event):
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
    if not was_on:  # when it was on, UserPromptSubmit has just printed ON for this message
        print(ON)


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
        print(ON)


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


def is_principal_model(model_id):
    return re.search(re.escape(MODEL_ID) + r"(?!\d)", model_id.lower()) is not None


def switch_refusal(event):
    """The message that cancels this switch, or None to allow it."""
    from_model, to_model = event.get("from_model"), event.get("to_model")
    if not isinstance(from_model, str) or not isinstance(to_model, str):
        return None
    if not from_model.strip() or not to_model.strip():
        return None  # a blank model id is bad input, not a model the user chose
    if not is_principal_model(from_model) or is_principal_model(to_model):
        return None
    flag = flag_for(event)
    if flag is None or not flag.is_file():
        return None
    return (f"swd: this session stays on {MODEL_NAME}, because the principal runs on it and swd mode is on "
            "in this session. To switch anyway, run /swd:off.")


if __name__ == "__main__":
    try:
        main()
    except OSError:
        pass
