#!/usr/bin/env bash
# Opens two herdr panes beside the principal's pane: the task ledger, refreshed
# every two seconds, and the activity timeline. In the Herdr desktop app
# (HC_TERMINAL_SOCKET) it starts two terminals with `hc run` instead. Elsewhere
# it prints the two commands. A dashboard problem must never fail a run, so this always exits 0.

run_dir="${1:-}"
if [ -z "$run_dir" ]; then
  echo "usage: swd-watch.sh <run_dir>"
  exit 0
fi

# shortcut: a run folder path containing a single quote breaks these commands; quote properly if that ever comes up.
# Drop the markdown separator row and align the columns, so the pane reads as a table.
ledger_cmd="while :; do clear; grep -v '^|-' '$run_dir/ledger.md' | column -t -s '|'; sleep 2; done"
activity_cmd="tail -f '$run_dir/activity.md'"

if [ -z "${HERDR_PANE_ID:-}" ] && [ -n "${HC_TERMINAL_SOCKET:-}" ]; then
  # Herdr desktop app: separate terminals through `hc`, not panes. --no-notify keeps
  # hc from typing into the principal's own terminal when a watcher exits.
  if ! command -v hc >/dev/null 2>&1; then
    echo "hc not found; the run continues without the watch terminals."
  elif hc run --bg --no-notify --label swd=ledger -- "$ledger_cmd" >/dev/null &&
       hc run --bg --no-notify --label swd=activity -- "$activity_cmd" >/dev/null; then
    echo "herdr app: started the ledger and activity terminals."
  else
    echo "warning: could not start herdr app terminals; the run continues without them."
  fi
  exit 0
fi

if [ -z "${HERDR_PANE_ID:-}" ]; then
  echo "Not running inside herdr. To watch this run, use two terminals:"
  echo "  $ledger_cmd"
  echo "  $activity_cmd"
  exit 0
fi

new_pane_id() {
  python3 -c 'import json, sys; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])' 2>/dev/null
}

# open_pane <split target> <direction> <label> <command>; prints the new pane id.
open_pane() {
  local id
  id=$(herdr pane split "$1" --direction "$2" --no-focus | new_pane_id) || return 1
  [ -n "$id" ] || return 1
  herdr pane rename "$id" "$3" >/dev/null 2>&1 || true
  herdr pane run "$id" "$4" >/dev/null || return 1
  echo "$id"
}

if ledger_pane=$(open_pane --current right "swd ledger" "$ledger_cmd") &&
   open_pane "$ledger_pane" down "swd activity" "$activity_cmd" >/dev/null; then
  echo "herdr: opened the ledger and activity panes."
else
  echo "warning: could not open herdr panes; the run continues without them."
fi
exit 0
