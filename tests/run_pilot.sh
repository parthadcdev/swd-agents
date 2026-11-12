#!/usr/bin/env bash
# Runs one pilot end to end: a real /swd:build run in a temp project, then grades it.
#
#   tests/run_pilot.sh existing-repo
#   tests/run_pilot.sh new-project
#
# This is a real multi-agent run. It costs tokens and takes several minutes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PILOT="$ROOT/tests/pilots/${1:?usage: run_pilot.sh <pilot-name>}"
[ -f "$PILOT/requirement.txt" ] || { echo "no such pilot: $1"; exit 2; }

TMP="$(mktemp -d)"
echo "pilot project: $TMP"
cd "$TMP"

if [ -d "$PILOT/repo" ]; then
  cp -R "$PILOT/repo/." .
  find . -name __pycache__ -type d -prune -exec rm -rf {} +
  git init -q
  git add -A
  git -c user.name=pilot -c user.email=pilot@example.com commit -q -m "Initial commit"
fi
# The team commits as the pilot user, not as whoever runs the pilot.
export GIT_AUTHOR_NAME=pilot GIT_AUTHOR_EMAIL=pilot@example.com
export GIT_COMMITTER_NAME=pilot GIT_COMMITTER_EMAIL=pilot@example.com

# Headless runs cannot answer permission prompts, so the tools the team needs are allowed
# up front. Edits are limited to the temp project by acceptEdits; Bash is limited to this list,
# which leaves out anything that deletes files or reaches the network.
ALLOWED=(
  Read Write Edit Glob Grep Agent Skill
  "Bash(git *)" "Bash(python3 *)" "Bash(echo *)" "Bash(cat *)" "Bash(mkdir *)"
  "Bash(date *)" "Bash(ls *)" "Bash(cd *)" "Bash(pwd)" "Bash(wc *)" "Bash(diff *)"
  "Bash(head *)" "Bash(tail *)" "Bash(grep *)" "Bash(find *)" "Bash(printf *)" "Bash(sort *)"
  "Bash(test *)" "Bash(touch *)" "Bash(cp *)" "Bash(mv *)" "Bash(chmod *)" "Bash(which *)"
  "Bash($ROOT/scripts/swd-watch.sh *)" "Bash($ROOT/scripts/swd-log.sh *)"
)

# Sonnet keeps a pilot affordable; the principal's playbook is written to work on a mid-tier model.
# User-level settings are left out so the run sees only this plugin: a user hook that rewrites
# shell commands would stop them matching the allowlist above.
claude -p --plugin-dir "$ROOT" --model sonnet --permission-mode acceptEdits \
  --setting-sources project,local --add-dir "$ROOT" \
  --allowedTools "${ALLOWED[@]}" \
  -- "Use the swd:build skill for this requirement: $(cat "$PILOT/requirement.txt")" \
  | tee "$TMP.output.txt"

status=0
echo "--- check_run"
python3 "$ROOT/scripts/check_run.py" "$TMP" || status=1
echo "--- acceptance"
python3 "$PILOT/acceptance.py" || status=1
[ "$status" -eq 0 ] && echo "PILOT PASS: $1" || echo "PILOT FAIL: $1 (project kept at $TMP)"
exit "$status"
