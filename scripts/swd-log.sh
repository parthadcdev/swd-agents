#!/usr/bin/env bash
# Appends one line to a run's activity.md, stamped from the clock:
#   swd-log.sh <run_dir> <event> <detail...>
# One command with no shell substitution, so it is easy to allow in a permission list.
run_dir="${1:-}"; event="${2:-}"
if [ -z "$run_dir" ] || [ -z "$event" ]; then
  echo "usage: swd-log.sh <run_dir> <event> <detail...>" >&2
  exit 1
fi
shift 2
case "$event" in
  dispatch|return|verdict|commit|fix|replan|ruling|wave-done|blocked|done) ;;
  *) echo "unknown event: $event" >&2; exit 1 ;;
esac
line="- $(date +%H:%M:%S) $event $*"
echo "${line% }" >> "$run_dir/activity.md"
