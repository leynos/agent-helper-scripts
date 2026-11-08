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
#   * GH_TOKEN, GITHUB_TOKEN and GH_CONFIG_DIR are cleared, and the environment
#     is replaced with an explicit allowlist, so no ambient token, config
#     override or path reaches the agent;
#   * a private network namespace admits DNS to this host's resolvers and one
#     TCP port to the model API host, and drops everything else, so no HTTP
#     client can reach GitHub. Both the permitted and the blocked routes are
#     proved before the agent starts.
# The mount namespace is made private first, so none of this reaches the host.
# The stand-in records every invocation to the trace before answering.
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
# The model API host is the only egress the sandbox admits. It has to be
# resolved on the host, before the namespace drops the network, because the
# allowlist is written in addresses.
MODEL_HOST=$(python3 -c '
import os
import urllib.parse
url = os.environ.get("ANTHROPIC_BASE_URL", "")
print(urllib.parse.urlparse(url).hostname or "api.anthropic.com")
')
MODEL_ADDRS=$(getent ahostsv4 "$MODEL_HOST" | awk '{print $1}' | sort -u | tr '\n' ' ')
if [ -z "$MODEL_ADDRS" ]; then
  echo "sandboxed_run.sh: cannot resolve $MODEL_HOST; refusing to run" >&2
  exit 2
fi
# DNS is restricted to the resolvers this host actually uses, read from the
# same file the sandbox will read. Allowing port 53 generally would leave an
# arbitrary destination reachable from the agent.
DNS_ADDRS=$(awk '$1 == "nameserver" { print $2 }' /etc/resolv.conf | sort -u | tr '\n' ' ')
if [ -z "$DNS_ADDRS" ]; then
  echo "sandboxed_run.sh: no nameserver to admit; refusing to run" >&2
  exit 2
fi
# The egress allowlist is the boundary that stops a second HTTP client, so a
# host without pasta or nft cannot produce an isolated run at all.
for tool in pasta nft unshare; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "sandboxed_run.sh: '$tool' is required for an isolated run" >&2
    exit 2
  fi
done

rm -rf "$RUN"
mkdir -p "$RUN/work" "$RUN/scratch"

cp "$ROOT/gh-shim.py" "$RUN/gh"
sed -i "s#^RUN = .*#RUN = Path(\"$RUN\")#" "$RUN/gh"
chmod +x "$RUN/gh"
cp "$ROOT/scenarios/$SCENARIO/facts.json" "$RUN/facts.json"
cp -R "$SKILLS_DIR/$SKILL_NAME" "$RUN/work/$SKILL_NAME"
: > "$TRACE"

# Empty stand-ins for the credential surfaces the sandbox replaces. `home` is
# writable, because the CLI may create state; `empty-dir` is only read back.
mkdir -p "$RUN/empty-dir" "$RUN/home"
: > "$RUN/empty-file"

cat > "$RUN/outer.sh" <<'OUTER'
set -uo pipefail
# This runs in the network namespace pasta created, where netfilter is ours to
# manage. Install the egress allowlist, prove it took, then enter a mount
# namespace for the masking.
# Egress: drop everything except DNS to the host's resolvers and one TCP port
# to the model API. The agent runs with Bash, so a filesystem mask alone cannot
# stop a second HTTP client; this does. The addresses arrive space-separated
# and are written here as nftables sets, which need commas.
MODEL_SET=$(printf '%s' "$MODEL_ADDRS" | sed 's/ *$//; s/  */, /g')
DNS_SET=$(printf '%s' "$DNS_ADDRS" | sed 's/ *$//; s/  */, /g')
nft -f - <<NFTRULES || { echo "abort: cannot install egress rules" >&2; exit 1; }
table inet readiness-sandbox
delete table inet readiness-sandbox
table inet readiness-sandbox {
  chain out {
    type filter hook output priority 0; policy drop;
    oifname "lo" accept
    ip daddr { $DNS_SET } udp dport 53 accept
    ip daddr { $DNS_SET } tcp dport 53 accept
    ip daddr { $MODEL_SET } tcp dport 443 accept
    ct state established,related accept
  }
}
NFTRULES
if ! nft list table inet readiness-sandbox >/dev/null 2>&1; then
  echo "abort: egress ruleset is not present after install" >&2
  exit 1
fi
# Verify both directions before the agent starts. A blocked-only check can
# pass on a network that is simply broken, and an allowed-only check can pass
# with no filter installed at all, so only the pair establishes the boundary.
# The admitted set is one nftables rule, so one successful connection proves
# it. Requiring every address would fail the run on a single stale A record.
reached=
for addr in $MODEL_ADDRS; do
  if timeout 10 bash -c "exec 3<>/dev/tcp/$addr/443" 2>/dev/null; then
    reached=$addr
    break
  fi
done
if [ -z "$reached" ]; then
  echo "abort: no model API address is reachable: $MODEL_ADDRS" >&2
  exit 1
fi
echo "egress: model API reachable at $reached:443"
# Non-model destinations are addressed literally, so a DNS failure cannot be
# mistaken for a block. 1.1.1.1 is arbitrary; 140.82.121.4 is GitHub.
for addr in 1.1.1.1 140.82.121.4; do
  if timeout 8 bash -c "exec 3<>/dev/tcp/$addr/443" 2>/dev/null; then
    echo "abort: egress control reached $addr:443; sandbox is not isolated" >&2
    exit 1
  fi
done

exec unshare -m -- /bin/bash "$RUN/inner.sh"
OUTER

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
# The queue dispatcher may be absent on a host; mask it only when present, and
# fail closed when it is present but unmaskable.
if [ -e "$HOME_DIR/.cargo/bin/comenq" ]; then
  mask "$HOME_DIR/.cargo/bin/comenq" "$RUN_NO_TOOL"
fi

# Every credential surface the run can reach. These are emptied rather than
# unset, so a client that escaped the `gh` mask still finds no token, and an
# agent that reads the lifecycle credential file finds it empty.
for surface in \
  "$HOME_DIR/.config/gh" \
  "$HOME_DIR/.local/share/github-tokens" \
  "$CREDENTIALS_FILE"; do
  hide "$surface"
done
# Prove the credential stores are gone before the agent starts. A directory
# mask removes the paths beneath it, while a file mask leaves the path present
# but empty, so each shape is checked for what it should show: absence for the
# configuration file inside a masked directory, and emptiness for the files
# masked in place.
for surface in \
  "$HOME_DIR/.config/gh/hosts.yml"; do
  if [ -e "$surface" ]; then
    echo "abort: $surface is still readable; credentials are not isolated" >&2
    exit 1
  fi
done
for surface in \
  "$HOME_DIR/.local/share/github-tokens" \
  "$CREDENTIALS_FILE"; do
  if [ -s "$surface" ]; then
    echo "abort: $surface is still non-empty; credentials are not isolated" >&2
    exit 1
  fi
done
echo "isolation: credential stores are masked"

cd "$RUN/work" || exit 1
# The environment is cleared rather than filtered: only what this run needs is
# passed, so no ambient token, config override or path reaches the agent.
exec env -i \
  PATH="$RUN:$CLAUDE_BIN:/usr/bin:/bin" \
  HOME="$HOME_DIR" \
  GH_TOKEN= GITHUB_TOKEN= GH_CONFIG_DIR="$RUN/gh-config" \
  ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL" \
  ANTHROPIC_AUTH_TOKEN="$ANTHROPIC_AUTH_TOKEN" \
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

# pasta owns the network namespace: it forwards the host interface into a new
# one, where the inner script installs the egress allowlist. unshare then adds
# the private mount namespace inside it. --runas keeps the inner exit status
# meaningful by running as this user rather than dropping to `nobody`.
RUN="$RUN" RUN_NO_TOOL="$RUN/no-tool" CLAUDE_BIN="$CLAUDE_BIN" \
  ASSIGNMENT="$ASSIGNMENT" EVENTS="$EVENTS" \
  HOME_DIR="$HOME_DIR" CREDENTIALS_FILE="$CREDENTIALS_FILE" \
  MODEL_ADDRS="$MODEL_ADDRS" DNS_ADDRS="$DNS_ADDRS" \
  pasta --config-net -t none -u none -- /bin/bash "$RUN/outer.sh"
rc=$?
echo "agent rc: $rc"
echo "--- gh invocations ---"
cat "$TRACE"
# Propagate the agent's own status. A rehearsal that was killed by its budget,
# timed out, or aborted on an isolation check is not a successful run, and an
# automation reading this script's status must not mistake it for one.
if [ "$rc" -ne 0 ]; then
  echo "sandboxed_run.sh: run failed with status $rc; see above" >&2
  exit "$rc"
fi
exit 0
