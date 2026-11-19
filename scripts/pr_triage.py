"""Optional triage of trusted pull request comments, used by swd-pr.py. Not run by name.

Triage asks TypeSafe two questions about each new trusted comment and leaves the decision to `decide`. It is on
only when the user's own ~/.claude/swd-triage lists the project and TYPESAFE_API_KEY is set; nothing from a pull
request, an issue or the project's files can turn it on or change where a request goes. Every failure ends triage
with a fixed string: exception text is never kept, because it can hold the Authorization header.
"""
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
TIMEOUT = 10  # seconds; shortcut: bounds each socket operation and, checked between chunks, the whole request, so the worst case is about twice TIMEOUT plus name lookup, which nothing bounds; upgrade if a slow resolver holds /swd:follow up
ANSWER_CAP = 65536  # bytes; a real answer is a few hundred
DONE_ABOVE = 0.7
WANTS_BELOW = 0.3
QUESTIONS = {
    "wants_change": {
        "type": "noul",
        "instructions": "Does the reviewer want code, tests or docs in this pull request changed, as `thread` stands at its end?",
        "criteria": {
            "true": "The thread asks for a change, or points out a defect that needs one, and the reviewer has not withdrawn it",
            "false": "The thread is praise, approval, thanks, a question that needs only an answer, an idea put off to a later pull request, or a request the reviewer withdrew",
        },
    },
    "already_done": {
        "type": "noul",
        "instructions": "Has the change the reviewer asked for already been made?",
        "criteria": {
            "true": "A later message in `thread` or a commit in `commits_after` says the requested change was made",
            "false": "Nothing after the request says it was made, or no change was requested",
        },
    },
}


KEY_PATTERN = re.compile(r"[!-~]{1,512}")  # printable ASCII, no space


def _same(a, b):
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


def api_key(project):
    """The key, when ~/.claude/swd-triage lists `project` (one absolute folder per line) and the key is set."""
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        return None
    try:
        lines = (Path.home() / ".claude" / "swd-triage").read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError, RuntimeError):
        return None  # missing, unreadable or not text: off, and nothing is said
    for line in lines:
        try:
            if Path(line.strip()).is_absolute() and _same(line.strip(), project):
                return key
        except (OSError, ValueError, RuntimeError):
            continue
    return None


def decide(done, wants):
    if done > DONE_ABOVE:
        return "already handled"
    if wants < WANTS_BELOW:
        return "asks for nothing"
    return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # a 3xx surfaces as an error, so the key never follows it to another host


def _scores(raw):
    """(done, wants) from a reply body, or None when it is not a usable answer."""
    try:
        answers = json.loads(raw)["answers"]
        found = [answers[name]["noul"] for name in ("already_done", "wants_change")]
    except (ValueError, KeyError, TypeError, RecursionError):
        return None
    if all(isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 1 for x in found):
        return tuple(found)
    return None


def triage(key, states, folder, stem):
    """(verdicts, failure): one verdict per state, None for a state not judged, and why triage stopped, if it did."""
    verdicts = [None] * len(states)
    if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
        return verdicts, "TYPESAFE_API_KEY is not usable"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    folder = Path(folder)
    for i, state in enumerate(states, 1):
        try:
            body = json.dumps({"model": MODEL, "state": state, "questions": QUESTIONS}).encode("utf-8")
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{stem}-{i}.request.json").write_bytes(body)
            request = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
                "Authorization": "Bearer " + key, "Content-Type": "application/json"})
            deadline = time.monotonic() + TIMEOUT
            with opener.open(request, timeout=TIMEOUT) as reply:
                if reply.status != 200:
                    return verdicts, f"status {reply.status}"
                raw = bytearray()   # linear however small the chunks are
                while True:
                    chunk = reply.read1(4096)   # not read(n), which waits for all n bytes
                    if time.monotonic() > deadline:
                        return verdicts, "timed out"
                    if not chunk:
                        if reply.length:   # bytes the header declared that never came; None when it declared none
                            return verdicts, "could not reach the service"
                        break
                    raw += chunk
                    if len(raw) > ANSWER_CAP:
                        return verdicts, "the answer was not usable"
            if key.encode("ascii") in raw:
                return verdicts, "the answer was not usable"   # an echoed key is never written to the run folder
            (folder / f"{stem}-{i}.answer.json").write_bytes(raw)
            scores = _scores(raw)
            if scores is None:
                return verdicts, "the answer was not usable"
        except urllib.error.HTTPError as error:
            # shortcut: a 413 ends triage for the round, trim the thread if real pull requests hit it
            error.close()
            return verdicts, f"status {error.code}"
        except socket.timeout:
            return verdicts, "timed out"
        except urllib.error.URLError as error:
            return verdicts, "timed out" if isinstance(error.reason, socket.timeout) else "could not reach the service"
        except Exception:  # noqa: BLE001 -- shortcut: any other failure is one fixed string, never its text, which can hold the key
            return verdicts, "could not reach the service"
        verdicts[i - 1] = (decide(*scores), *scores)
    return verdicts, None
