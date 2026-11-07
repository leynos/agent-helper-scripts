#!/usr/bin/env bash
# Run one controlled readiness scenario against the candidate's shipped skill.
#
# Isolation is layered so the agent cannot reach real GitHub:
#   * a private mount namespace replace-binds the recorded stand-in over every
#     real `gh` binary and over the queue dispatcher, so no absolute path can
#     reach them;
#   * GH_TOKEN, GITHUB_TOKEN and GH_CONFIG_DIR are cleared, so even an
#     unmasked client would be anonymous;
#   * the model API stays reachable, because the agent itself needs it.
# The mount namespace is made private first, so none of this reaches the host.
# The stand-in records every invocation to the trace before answering.
set -uo pipefail

SCENARIO=${1:?scenario name}
# The fixture directory is this script's own directory: the stand-in is
# `gh-shim.py`, the recorded facts live under `scenarios/`, and the run
# directory is scratch beside them.
ROOT=$(cd -- "$(dirname -- "$0")" && pwd)
RUN=${RUN_DIR:-/tmp/readiness-agent-boundary}/$SCENARIO
SKILL_SRC=${SKILL_SRC:?set SKILL_SRC to the candidate skills directory}
# The agent CLI is not installed under a system prefix, so name its directory
# explicitly rather than inheriting the operator's PATH into the sandbox.
CLAUDE_BIN=${CLAUDE_BIN:-$(dirname -- "$(command -v claude 2>/dev/null || echo /nonexistent/claude)")}
if [ ! -x "$CLAUDE_BIN/claude" ]; then
  echo "sandboxed_run.sh: no 'claude' CLI; set CLAUDE_BIN to its directory" >&2
  exit 2
fi
TRACE=$RUN/gh-trace.jsonl
EVENTS=$RUN/agent-events.jsonl

rm -rf "$RUN"
mkdir -p "$RUN/work" "$RUN/scratch"

cp "$ROOT/gh-shim.py" "$RUN/gh"
sed -i "s#^RUN = .*#RUN = Path(\"$RUN\")#" "$RUN/gh"
chmod +x "$RUN/gh"
cp "$ROOT/scenarios/$SCENARIO/facts.json" "$RUN/facts.json"
cp -R "$SKILL_SRC" "$RUN/work/pr-babysitting"
: > "$TRACE"

cat > "$RUN/inner.sh" <<'INNER'
set -uo pipefail
mount --make-rprivate /
for target in /usr/bin/gh /bin/gh /home/leynos/.cargo/bin/comenq; do
  if [ -e "$target" ]; then
    if [ "$target" = /home/leynos/.cargo/bin/comenq ]; then
      mount --bind "$RUN_NO_TOOL" "$target"
    else
      mount --bind "$RUN/gh" "$target"
    fi
  fi
done
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
  unshare -rm -- /bin/bash "$RUN/inner.sh"
echo "agent rc: $?"
echo "--- gh invocations ---"
cat "$TRACE"
