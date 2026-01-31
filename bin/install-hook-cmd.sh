#!/usr/bin/env bash
set -euo pipefail

# install-hook-cmd.sh
#
# Insert a "command" hook into ~/.claude/settings.json for the given hook type.
# Idempotent: if the exact command already exists under that hook type, no change.
#
# Usage:
#   ./install-hook-cmd.sh <HookType> <command...>
#   ./install-hook-cmd.sh <HookType> --timeout <seconds> <command...>
#
# Examples:
#   ./install-hook-cmd.sh Stop python3 ~/.claude/hooks/post-turn-quality-stop-hook.py
#   ./install-hook-cmd.sh Stop --timeout 600 python3 ~/.claude/hooks/post-turn-quality-stop-hook.py
#   ./install-hook-cmd.sh PreToolUse --timeout 30 bash -lc 'echo hello'

SETTINGS_FILE="${CLAUDE_SETTINGS_FILE:-$HOME/.claude/settings.json}"
SETTINGS_DIR="$(dirname "$SETTINGS_FILE")"

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
        | any(
            .[]?;
            (.type=="command" and .command==$cmd)
            or (.hooks[]?; .type=="command" and .command==$cmd)
          )
      )
      then .
      else .hooks[$hook_type] |= ([ newhook($cmd; $has_timeout; $timeout_val) ] + .)
    end
' "$SETTINGS_FILE" >"$tmp"

# Replace atomically where possible.
# If this fails due to permissions, use `sudo install -m 0644 "$tmp" "$SETTINGS_FILE"` instead.
mv "$tmp" "$SETTINGS_FILE"
trap - EXIT
