#!/usr/bin/env python3
"""Render an swd run folder as one self-contained HTML page, dashboard.html.

    python3 swd-dashboard.py <run_dir>                  write the page once
    python3 swd-dashboard.py --watch --open <run_dir>   open it in the browser and keep it current

The page shows the tasks in columns by wave, coloured by status, the model and effort each task,
the reviews and the final check are staffed at, the model that conducts, and the activity timeline.
It is rebuilt from plan.md, ledger.md, activity.md, staffing.md and decisions.md, so no agent
has to do anything for it.
Set SWD_NO_BROWSER=1 to stop --open from opening a browser (used by the pilots).
"""
import argparse
import html
import os
import re
import sys
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_run import ACTIVITY_RE, decision, parse_ledger, parse_plan, read, run_mode  # noqa: E402

REFRESH_SECONDS = 2
MAX_WATCH_SECONDS = 12 * 60 * 60  # an abandoned run must not leave a process behind forever

CSS = """
:root { --bg:#f6f7f9; --card:#fff; --ink:#1c2330; --muted:#667085; --line:#d9dee7;
  --todo:#98a2b3; --in-progress:#2f6fed; --in-review:#b7791f; --done:#1f9d55; --blocked:#d1373f; }
@media (prefers-color-scheme: dark) { :root { --bg:#12151b; --card:#1b2029; --ink:#e7eaf0;
  --muted:#98a2b3; --line:#2c3440; --todo:#667085; --in-progress:#6b9bff; --in-review:#e0a63a;
  --done:#3fc37a; --blocked:#f0666d; } }
* { box-sizing: border-box; }
body { margin:0; padding:24px 16px 48px; background:var(--bg); color:var(--ink);
  font:15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width:1200px; margin:0 auto; }
h1 { font-size:20px; margin:0 0 4px; overflow-wrap:anywhere; }
h2 { font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin:0 0 10px; }
.summary { color:var(--muted); margin:0 0 12px; }
.badge { display:inline-block; padding:1px 8px; border:1px solid var(--line); border-radius:999px;
  font-size:12px; color:var(--ink); margin-right:6px; }
.bar { height:6px; background:var(--line); border-radius:3px; overflow:hidden; margin-bottom:24px; }
.bar div { height:100%; background:var(--done); }
.waves { display:flex; gap:16px; align-items:flex-start; overflow-x:auto; padding-bottom:8px; }
.wave { flex:1 0 240px; min-width:0; }
.task { background:var(--card); border:1px solid var(--line); border-left:5px solid var(--c);
  border-radius:8px; padding:10px 12px; margin-bottom:10px; }
.task .top { display:flex; justify-content:space-between; gap:8px; font-weight:600; }
.task .status { color:var(--c); font-size:12px; text-transform:uppercase; white-space:nowrap; }
.task .title { margin:2px 0 6px; overflow-wrap:anywhere; }
.task .meta { color:var(--muted); font-size:13px; overflow-wrap:anywhere; }
.status-todo { --c:var(--todo); } .status-in-progress { --c:var(--in-progress); }
.status-in-review { --c:var(--in-review); } .status-done { --c:var(--done); }
.status-blocked { --c:var(--blocked); }
.status-in-progress, .status-in-review { box-shadow:0 0 0 2px color-mix(in srgb, var(--c) 25%, transparent); }
.timeline { background:var(--card); border:1px solid var(--line); border-radius:8px; margin-top:24px;
  padding:12px 14px; font:13px/1.7 ui-monospace, SFMono-Regular, Menlo, monospace; }
.timeline div { overflow-wrap:anywhere; } .timeline .t { color:var(--muted); }
.timeline .e { display:inline-block; min-width:9ch; font-weight:600; }
.empty { color:var(--muted); }
"""


def esc(text):
    return html.escape(str(text), quote=True)


def read_activity(run_dir):
    """Timeline entries as (time, event, detail), oldest first. Lines in another shape are skipped."""
    entries = []
    for line in (read(run_dir / "activity.md") or "").splitlines():
        match = ACTIVITY_RE.match(line)
        if match:
            entries.append((line[2:10], match.group(1), (match.group(2) or "").strip()))
    return entries


def read_staffing(run_dir):
    """For -> (Model, Effort) from staffing.md, by check_run's row rules; the last row wins. Never raises."""
    staffing = {}
    for line in (read(run_dir / "staffing.md") or "").splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[:4] == ["For", "Agent", "Model", "Effort"] or all(c and set(c) <= set("-: ") for c in cells):
            continue
        if len(cells) == 5:
            staffing[cells[0]] = (cells[2], cells[3])
    return staffing


def render(run_dir):
    """The whole page as a string. Never raises on a half-written or missing run file."""
    tasks, _ = parse_plan(read(run_dir / "plan.md") or "")
    rows, _ = parse_ledger(read(run_dir / "ledger.md") or "")
    activity = read_activity(run_dir)
    staffing = read_staffing(run_dir)
    conductor = decision(run_dir, "Conductor")
    finished = bool(activity) and activity[-1][1] == "done"

    statuses = {t["id"]: rows.get(t["id"], {}).get("status", "todo") for t in tasks}
    done = sum(1 for s in statuses.values() if s == "done")
    if finished:
        state = "Complete"
    elif "blocked" in statuses.values():
        state = "Blocked"
    else:
        state = "Running"

    last_seen = {}  # task id -> its most recent timeline entry
    for when, event, detail in activity:
        for task in tasks:
            if re.search(rf"\b{task['id']}\b", detail):
                last_seen[task["id"]] = f"{when} {event} {detail}"

    waves = {}
    for task in tasks:
        waves.setdefault(task["wave"], []).append(task)

    columns = []
    for wave in sorted(waves, key=lambda w: (w is None, w or 0)):
        cards = []
        for task in waves[wave]:
            status = statuses[task["id"]]
            if status not in ("todo", "in-progress", "in-review", "done", "blocked"):
                status = "todo"
            meta = [esc(task["role"] or "no role")]
            if task["id"] in staffing:
                meta.append(esc(" ".join(staffing[task["id"]])))
            attempts = rows.get(task["id"], {}).get("attempts", 0)
            if attempts > 1:
                meta.append(f"attempt {attempts}")
            if task["depends"]:
                meta.append("after " + esc(", ".join(task["depends"])))
            seen = f'<div class="meta">{esc(last_seen[task["id"]])}</div>' if task["id"] in last_seen else ""
            cards.append(
                f'<div class="task status-{status}">'
                f'<div class="top"><span>{esc(task["id"])}</span><span class="status">{status}</span></div>'
                f'<div class="title">{esc(task["title"])}</div>'
                f'<div class="meta">{" · ".join(meta)}</div>{seen}</div>'
            )
        label = f"Wave {wave}" if wave is not None else "No wave"
        columns.append(f'<section class="wave"><h2>{label}</h2>{"".join(cards)}</section>')

    board = (
        f'<div class="waves">{"".join(columns)}</div>' if columns
        else '<p class="empty">No plan yet. The architect is still designing.</p>'
    )
    lines = "".join(
        f'<div><span class="t">{esc(when)}</span> <span class="e">{esc(event)}</span> {esc(detail)}</div>'
        for when, event, detail in reversed(activity)
    ) or '<div class="empty">Nothing has happened yet.</div>'
    percent = round(100 * done / len(tasks)) if tasks else 0
    refresh = "" if finished else f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">'
    conductor_badge = f'\n<span class="badge">Conductor: {esc(conductor)}</span>' if conductor else ""
    checkers = " · ".join(
        f"{label}: {esc(' '.join(staffing[key]))}"
        for key, label in (("review", "Review"), ("final", "Final")) if key in staffing
    )
    checkers = f'\n<p class="summary">{checkers}</p>' if checkers else ""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{refresh}
<title>swd run: {esc(run_dir.name)}</title><style>{CSS}</style></head>
<body><main>
<h1>{esc(run_dir.name)}</h1>
<p class="summary"><span class="badge">{esc(run_mode(run_dir) or "mode not set")}</span>
<span class="badge">{state}</span>{conductor_badge} {done} of {len(tasks)} tasks done</p>{checkers}
<div class="bar" role="progressbar" aria-valuenow="{percent}" aria-valuemin="0" aria-valuemax="100"
 aria-label="Tasks done"><div style="width:{percent}%"></div></div>
{board}
<div class="timeline"><h2>Timeline</h2>{lines}</div>
</main></body></html>
"""


def write_page(run_dir):
    """Write dashboard.html atomically, so the browser never loads a half-written page."""
    page = render(run_dir)
    target = run_dir / "dashboard.html"
    temp = run_dir / "dashboard.html.tmp"
    temp.write_text(page, encoding="utf-8")
    os.replace(temp, target)
    return target, 'http-equiv="refresh"' not in page


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--watch", action="store_true", help="keep rebuilding until the run is done")
    parser.add_argument("--open", action="store_true", help="open the page in the browser")
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)

    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"not a run folder: {run_dir}", file=sys.stderr)
        return 1

    target, finished = write_page(run_dir)
    print(target)
    if args.open and not os.environ.get("SWD_NO_BROWSER"):
        webbrowser.open(target.as_uri())

    started = time.monotonic()
    while args.watch and not finished and time.monotonic() - started < MAX_WATCH_SECONDS:
        time.sleep(REFRESH_SECONDS)
        if not run_dir.is_dir():
            break
        try:
            _, finished = write_page(run_dir)
        except OSError:
            continue  # Windows will not replace a page the browser has open; the next refresh tries again
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
