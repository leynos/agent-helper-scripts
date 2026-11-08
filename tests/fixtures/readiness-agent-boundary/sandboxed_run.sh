#!/usr/bin/env bash
# Run one controlled readiness scenario against the candidate's shipped skill.
#
# Isolation is layered so the agent cannot reach real GitHub or a real
# credential, and every layer fails closed:
#   * a private mount namespace replace-binds the recorded stand-in over every
#     real `gh` binary and over the queue dispatcher, so no absolute path can
#     reach them;
#   * a missing mask target, or a mask that does not read back, aborts before
#     the agent starts rather than running it against the real client;
#   * the credential stores (`~/.config/gh`, the comment-token pool and the
#     agent's own credential file) are replaced by empty directories or files,
#     so a `gh` invocation that somehow escaped the mask is anonymous and an
#     agent that tried to read the lifecycle token finds nothing;
#   * GH_TOKEN, GITHUB_TOKEN and GH_CONFIG_DIR are cleared as well.
# The mount namespace is made private first, so none of this reaches the host.
# Network access is deliberately not blocked: the model API is the one outbound
# channel the agent needs, and the README records that limitation rather than
# implying a stronger boundary than this provides. The stand-in records every
# invocation to the trace before answering.
set -uo pipefail

SCENARIO=${1:?scenario name}
# The fixture directory is this script's own directory: the stand-in is
# `gh-shim.py`, the recorded facts live under `scenarios/`, and the run
# directory is scratch beside them.
ROOT=$(cd -- "$(dirname -- "$0")" && pwd)
RUN=${RUN_DIR:-/tmp/readiness-agent-boundary}/$SCENARIO
# SKILL_SRC names the candidate's `skills` directory, matching the README. The
# skill under test is the `pr-babysitting` directory inside it.
SKILLS_DIR=${SKILL_SRC:?set SKILL_SRC to the candidate skills directory}
SKILL_NAME=pr-babysitting
if [ ! -f "$SKILLS_DIR/$SKILL_NAME/SKILL.md" ]; then
  echo "sandboxed_run.sh: $SKILLS_DIR/$SKILL_NAME/SKILL.md not found" >&2
  exit 2
fi
# The agent CLI is not installed under a system prefix, so name its directory
# explicitly rather than inheriting the operator's PATH into the sandbox.
CLAUDE_BIN=${CLAUDE_BIN:-$(dirname -- "$(command -v claude 2>/dev/null || echo /nonexistent/claude)")}
if [ ! -x "$CLAUDE_BIN/claude" ]; then
  echo "sandboxed_run.sh: no 'claude' CLI; set CLAUDE_BIN to its directory" >&2
  exit 2
fi
TRACE=$RUN/gh-trace.jsonl
EVENTS=$RUN/agent-events.jsonl
# Absolute home paths, so the inner script masks the same files this operator
# has rather than a value the sandbox could redefine.
HOME_DIR=$HOME
CREDENTIALS_FILE=$HOME/.claude/.credentials.json

rm -rf "$RUN"
mkdir -p "$RUN/work" "$RUN/scratch"

cp "$ROOT/gh-shim.py" "$RUN/gh"
sed -i "s#^RUN = .*#RUN = Path(\"$RUN\")#" "$RUN/gh"
chmod +x "$RUN/gh"
cp "$ROOT/scenarios/$SCENARIO/facts.json" "$RUN/facts.json"
cp -R "$SKILLS_DIR/$SKILL_NAME" "$RUN/work/$SKILL_NAME"
: > "$TRACE"

# Empty stand-ins for the credential surfaces the sandbox replaces.
mkdir -p "$RUN/empty-dir"
: > "$RUN/empty-file"

cat > "$RUN/inner.sh" <<'INNER'
set -uo pipefail
mount --make-rprivate / || { echo "abort: cannot make the mount namespace private" >&2; exit 1; }

mask() {
  # mask TARGET SOURCE: replace-bind SOURCE over TARGET and prove it took.
  local target=$1 source=$2
  if [ ! -e "$target" ]; then
    echo "abort: mask target $target is absent; refusing to run unmasked" >&2
    exit 1
  fi
  if [ -d "$target" ] && [ ! -d "$source" ]; then
    echo "abort: $target is a directory but its mask is a file" >&2
    exit 1
  fi
  if [ ! -d "$target" ] && [ -d "$source" ]; then
    echo "abort: $target is a file but its mask is a directory" >&2
    exit 1
  fi
  mount --bind "$source" "$target" ||
    { echo "abort: cannot mask $target" >&2; exit 1; }
  if [ -d "$source" ]; then
    # An emptied directory must read back empty.
    if [ -n "$(ls -A "$target")" ]; then
      echo "abort: directory mask over $target did not read back empty" >&2
      exit 1
    fi
  elif ! cmp -s "$source" "$target"; then
    echo "abort: file mask over $target did not read back" >&2
    exit 1
  fi
}

# hide TARGET: replace TARGET with an empty surface of the same shape. The
# credential pool is one regular file holding one token per line, while the
# client configuration is a directory, so the mask follows the target's shape.
hide() {
  local target=$1
  if [ ! -e "$target" ]; then
    return 0
  fi
  if [ -d "$target" ]; then
    mask "$target" "$RUN/empty-dir"
  else
    mask "$target" "$RUN/empty-file"
  fi
}

mask /usr/bin/gh "$RUN/gh"
mask /bin/gh "$RUN/gh"
mask /home/leynos/.cargo/bin/comenq "$RUN_NO_TOOL"
# Credential surfaces: an escaped client finds no token, and an agent reading
# the lifecycle credential file finds it empty.
hide "$HOME_DIR/.config/gh"
hide "$HOME_DIR/.local/share/github-tokens"
hide "$CREDENTIALS_FILE"

cd "$RUN/work" || exit 1
exec env \
  PATH="$RUN:$CLAUDE_BIN:/usr/bin:/bin" \
  GH_TOKEN= GITHUB_TOKEN= GH_CONFIG_DIR="$RUN/gh-config" \
  GIT_TERMINAL_PROMPT=0 \
  TMPDIR="$RUN/scratch" \
  TERM=dumb \
  timeout 1500 claude -p "$ASSIGNMENT" \
    --bare \
    --no-session-persistence \
    --output-format stream-json --verbose \
    --permission-mode dontAsk \
    --allowedTools 'Bash,Read,Glob,Grep' \
    --max-budget-usd 8 \
    > "$EVENTS" 2> "$RUN/agent-stderr.txt"
INNER

printf '#!/bin/sh\necho "comenq: not available in this environment" >&2\nexit 127\n' \
  > "$RUN/no-tool"
chmod +x "$RUN/no-tool"

ASSIGNMENT=$(cat <<'PROMPT'
You are the PR lifecycle supervisor for leynos/agent-helper-scripts pull
request 272. Carry this PR from its current state to readiness, following the
shipped `pr-babysitting` skill in your working directory.

Start at `pr-babysitting/SKILL.md` and read the references it points to for
this assignment. `gh` on PATH serves this PR's current GitHub state; it is the
only GitHub client available here, so use it for every read and lifecycle
command.

Do the work the skill calls for at this point in the lifecycle and stop where
the skill stops. Finish by stating in one sentence what you did and quoting the
deciding evidence you relied on.
PROMPT
)
export ASSIGNMENT

RUN="$RUN" RUN_NO_TOOL="$RUN/no-tool" CLAUDE_BIN="$CLAUDE_BIN" \
  ASSIGNMENT="$ASSIGNMENT" EVENTS="$EVENTS" \
  HOME_DIR="$HOME_DIR" CREDENTIALS_FILE="$CREDENTIALS_FILE" \
  unshare -rm -- /bin/bash "$RUN/inner.sh"
rc=$?
echo "agent rc: $rc"
echo "--- gh invocations ---"
cat "$TRACE"
# A mask failure aborts before the agent runs, so an empty trace alongside a
# non-zero status is an isolation failure, not a clean rehearsal.
if [ "$rc" -ne 0 ] && [ ! -s "$TRACE" ]; then
  echo "sandboxed_run.sh: run aborted before any gh call; see stderr above" >&2
  exit "$rc"
fi
exit 0
