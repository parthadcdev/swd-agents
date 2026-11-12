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

TMP="$(cd "$(mktemp -d)" && pwd -P)"  # the physical path, so it matches what git reports
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
export SWD_NO_BROWSER=1  # the dashboard is still written, but a pilot must not open browser tabs

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
  --output-format json \
  -- "Use the swd:build skill for this requirement: $(cat "$PILOT/requirement.txt")" \
  > "$TMP.output.json" || true
# Print the principal's final message, then every command the permission system refused:
# a refused command is the usual reason a pilot stalls, and the allowlist above is the fix.
python3 - "$TMP.output.json" <<'PY'
import json, sys
try:
    out = json.load(open(sys.argv[1]))
except (OSError, ValueError) as error:
    sys.exit(f"no usable output from claude: {error}")
print(out.get("result", ""))
for denial in out.get("permission_denials", []):
    print("REFUSED:", denial.get("tool_name"), json.dumps(denial.get("tool_input"))[:300])
PY

pkill -f "swd-dashboard.py --watch.*$TMP" 2>/dev/null || true  # in case the run stopped before 'done'

# A run left on its branch is graded there; a merged run is already on the base branch.
branch="$(git branch --list 'swd/*' --format='%(refname:short)' | head -1)"
[ -n "$branch" ] && { git checkout -q "$branch" || true; }  # fails if the worktree was left behind; the finish check reports that

status=0
echo "--- check_run"
python3 "$ROOT/scripts/check_run.py" "$TMP" || status=1
echo "--- finish"
python3 "$ROOT/scripts/check_run.py" --finish "$TMP" || status=1
[ -z "$(git worktree list --porcelain | grep -c '^worktree' | grep -v '^1$')" ] || { echo "a worktree was left behind"; status=1; }
echo "--- acceptance"
python3 "$PILOT/acceptance.py" || status=1
[ "$status" -eq 0 ] && echo "PILOT PASS: $1" || echo "PILOT FAIL: $1 (project kept at $TMP)"
exit "$status"
