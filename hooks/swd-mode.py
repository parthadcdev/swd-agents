#!/usr/bin/env python3
"""UserPromptSubmit hook: keeps a session in swd mode once it has been turned on.

Reads the hook's JSON from stdin. `/swd:build` or `/swd:on` turns the mode on for that session,
`/swd:off` or the words "stop swd" turn it off. While it is on, every prompt gets a short
reminder added to the session's context: route code changes through the swd team.

A hook must never break a prompt, so every failure path prints nothing and exits 0.
"""
import json
import re
import sys
import time
from pathlib import Path

STATE = Path.home() / ".claude" / "swd-mode"
STALE_SECONDS = 7 * 24 * 60 * 60

ON = """swd mode: on
This session is in swd mode. Any request that creates or changes this project's code, tests,
configuration or documentation goes through the swd team: invoke the `swd:build` skill with
the request as the requirement, and do not make the change yourself. Answer questions,
explanations, reviews and status or git requests directly. If an swd run is already in
progress, carry on under its playbook. The user leaves swd mode by saying "stop swd" or
running /swd:off."""

OFF = """swd mode: off
swd mode has been turned off for this session. Handle requests normally from here on; the
swd team is used only when the user runs /swd:build again."""


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return
    if not isinstance(event, dict):
        return
    session = str(event.get("session_id") or "")
    prompt = str(event.get("prompt") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session):
        return  # no usable session id, and never a path
    flag = STATE / session

    if re.match(r"/swd:off\b", prompt) or re.search(r"\bstop swd\b", prompt, re.I):
        if flag.exists():
            flag.unlink()
            print(OFF)
        return
    if re.match(r"/swd:(build|on)\b", prompt):
        STATE.mkdir(parents=True, exist_ok=True)
        flag.write_text("")
        for old in STATE.iterdir():  # sessions that ended without turning it off
            if time.time() - old.stat().st_mtime > STALE_SECONDS:
                old.unlink()
    if flag.exists():
        print(ON)


if __name__ == "__main__":
    try:
        main()
    except OSError:
        pass
