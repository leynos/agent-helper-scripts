#!/usr/bin/env bash

# Insert a command hook into ~/.claude/settings.json for the requested hook
# type. The script stores the remaining argv as a shell-escaped command string
# and leaves existing identical command hooks unchanged.

set -euo pipefail

SETTINGS_FILE="${CLAUDE_SETTINGS_FILE:-$HOME/.claude/settings.json}"
SETTINGS_DIR="$(dirname "$SETTINGS_FILE")"

# Purpose:
#   Print command usage and terminate with an argument error.
# Parameters:
#   None.
# Returns:
#   Does not return; exits with status 2.
# Side effects:
#   Writes usage text to stderr.
usage() {
  cat >&2 <<'EOF'
Usage:
  install-hook-cmd.sh <HookType> <command...>
  install-hook-cmd.sh <HookType> --timeout <seconds> <command...>

Notes:
- <HookType> is a key under .hooks (e.g. Stop, SessionStart, PreToolUse, etc.)
- <command...> is stored as a single string, shell-escaped.
- Idempotent: does nothing if the exact command string already exists for that HookType.
- Writes via a temp file then replaces the original (may fail if the target is truly read-only/immutable).

Env:
  CLAUDE_SETTINGS_FILE  Override settings path (default: ~/.claude/settings.json)
EOF
  exit 2
}

if [[ $# -lt 2 ]]; then
  usage
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is required but was not found on PATH" >&2
  exit 1
fi

hook_type="$1"
shift

timeout=""
if [[ "${1:-}" == "--timeout" ]]; then
  [[ $# -ge 3 ]] || usage
  timeout="$2"
  shift 2
  [[ "$timeout" =~ ^[0-9]+$ ]] || { echo "Error: timeout must be an integer seconds value" >&2; exit 2; }
fi

[[ $# -ge 1 ]] || usage

# Turn the remaining argv into a single shell-escaped command string.
# This preserves spaces/quotes safely.
cmd=""
for arg in "$@"; do
  printf -v escaped '%q' "$arg"
  cmd+="${cmd:+ }$escaped"
done

mkdir -p "$SETTINGS_DIR"
if [[ ! -s "$SETTINGS_FILE" ]]; then
  echo '{}' >"$SETTINGS_FILE"
fi

tmp="$(mktemp "${SETTINGS_DIR}/settings.json.XXXXXX")"
# Purpose:
#   Remove the temporary settings file used for atomic replacement.
# Parameters:
#   None.
# Returns:
#   0 after attempting to remove the temporary file.
# Side effects:
#   Removes the file referenced by tmp when it exists.
cleanup() { rm -f "$tmp"; }
trap cleanup EXIT

jq --arg hook_type "$hook_type" \
   --arg cmd "$cmd" \
   --argjson has_timeout "$([[ -n "${timeout:-}" ]] && echo true || echo false)" \
   --argjson timeout_val "${timeout:-0}" '
  def newhook($cmd; $has_timeout; $timeout_val):
    if $has_timeout then
      { type: "command", command: $cmd, timeout: $timeout_val }
    else
      { type: "command", command: $cmd }
    end;

  (.hooks //= {})
  | (.hooks[$hook_type] //= [])
  | if (.hooks[$hook_type]
        | any(.[]?; .type=="command" and .command==$cmd)
      )
      then .
      else .hooks[$hook_type] |= ([ newhook($cmd; $has_timeout; $timeout_val) ] + .)
    end
' "$SETTINGS_FILE" >"$tmp"

# Replace atomically where possible.
# If this fails due to permissions, use `sudo install -m 0644 "$tmp" "$SETTINGS_FILE"` instead.
mv "$tmp" "$SETTINGS_FILE"
trap - EXIT
