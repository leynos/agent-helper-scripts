#!/usr/bin/env bash
# Run one controlled readiness scenario against the candidate's shipped skill.
#
# Isolation is layered so the agent cannot reach real GitHub or a real
# credential, and every layer fails closed:
#   * a private mount namespace replace-binds the recorded stand-in over every
#     real `gh` binary, so no absolute path can reach one;
#   * a missing mask target, or a mask that does not read back, aborts before
#     the agent starts rather than running it against the real client;
#   * the whole host home is replaced by an empty directory, so no file under
#     it is reachable by absolute path — not the client configuration, the
#     comment-token pool or the agent's credential file, and not anything else
#     a credential could be stored in; the CLI is copied out before the mask;
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
# The run directory is deleted outright below, so the name is checked before
# anything is removed. A separator or a dot name would put the deletion above
# the scenario level, where the unrecorded runs of every other scenario live.
case $SCENARIO in
  */* | . | ..)
    echo "sandboxed_run.sh: invalid scenario name: $SCENARIO" >&2
    exit 2
    ;;
esac
# The fixture directory is this script's own directory: the stand-in is
# `gh-shim.py`, the recorded facts live under `scenarios/`, and the run
# directory is scratch beside them.
ROOT=$(cd -- "$(dirname -- "$0")" && pwd)
if [ ! -f "$ROOT/scenarios/$SCENARIO/facts.json" ]; then
  echo "sandboxed_run.sh: unknown scenario '$SCENARIO'; expected $ROOT/scenarios/$SCENARIO/facts.json" >&2
  exit 2
fi
# Resolve the run directory before deleting it. A relative `RUN_DIR` would
# otherwise be re-interpreted against whatever directory a later step runs in,
# so the stand-in rewrite and the `cd "$RUN/work"` would name different paths.
RUN=$(realpath -m -- "${RUN_DIR:-/tmp/readiness-agent-boundary}/$SCENARIO")
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
ANSWERS=$RUN/gh-answers.jsonl
STATE=$RUN/state.json
EVENTS=$RUN/agent-events.jsonl
SUBMITTED=$RUN/submitted.md
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
mkdir -p "$RUN/work" "$RUN/scratch" "$RUN/claude-bin"

cp "$ROOT/gh-shim.py" "$RUN/gh"
sed -i "s#^RUN = .*#RUN = Path(\"$RUN\")#" "$RUN/gh"
chmod +x "$RUN/gh"
cp "$ROOT/scenarios/$SCENARIO/facts.json" "$RUN/facts.json"
# The local CodeScene half is a simulated `cs`: the real binary checks its
# licence against api.codescene.io on every invocation, and this sandbox drops
# that egress. The stand-in writes its own trace and discloses itself on every
# answer, so no recording can be mistaken for a real analysis.
cp "$ROOT/cs-shim.py" "$RUN/cs"
sed -i "s#^RUN = .*#RUN = Path(\"$RUN\")#" "$RUN/cs"
chmod +x "$RUN/cs"
cp -R "$SKILLS_DIR/$SKILL_NAME" "$RUN/work/$SKILL_NAME"
# The host home is masked wholesale below, so the CLI cannot be run from
# wherever the operator installed it. Copy it into the run directory first: the
# binary is self-contained and needs only the system libraries, which stay
# outside the masked home.
cp "$(readlink -f "$CLAUDE_BIN/claude")" "$RUN/claude-bin/claude"
chmod +x "$RUN/claude-bin/claude"
: > "$TRACE"

# Empty stand-ins for the credential surfaces the sandbox replaces. `home` is
# writable, because the CLI may create state; `empty-dir` is only read back.
mkdir -p "$RUN/empty-dir" "$RUN/home/.claude"
# The comment-token pool is replaced rather than abolished, so the manual-comment
# route stays exercisable inside the sandbox. The token is a fixture the stand-in
# alone honours: as far as real GitHub is concerned it is invalid, so nothing is
# lost if it escapes, and the host's real pool is never reachable because the
# whole host home is masked. The helper reads the pool under `$HOME`, so the
# isolated home gets the same fixture.
mkdir -p "$RUN/home/.local/share"
printf '%s\n' 'fixture-pool-token' > "$RUN/home/.local/share/github-tokens"

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

mask /usr/bin/gh "$RUN/gh"
mask /bin/gh "$RUN/gh"

# The whole host home is replaced, not a list of credential files inside it.
# Masking named paths left every other file under the operator's home readable
# by absolute path, and a credential can live at a path this runner never
# thought to name; the agent has no legitimate reason to read any of it. The
# isolated home at `$RUN/home` is what the run is given as `HOME`, and the CLI
# was copied out of the host home first so it still runs.
mask "$HOME_DIR" "$RUN/empty-dir"
# Prove the host home is gone and the isolated home survives it. A directory
# mask removes everything beneath the path, so any entry left under the host
# home means the mask did not take, and the read-back below fails closed on it.
if [ -n "$(ls -A "$HOME_DIR")" ]; then
  echo "abort: the host home still lists entries; it is not isolated" >&2
  exit 1
fi
for surface in \
  "$HOME_DIR/.config/gh/hosts.yml" \
  "$HOME_DIR/.local/share/github-tokens" \
  "$CREDENTIALS_FILE"; do
  if [ -e "$surface" ]; then
    echo "abort: $surface is still readable; credentials are not isolated" >&2
    exit 1
  fi
done
# The isolated home still holds the fixture pool, so the manual-comment route
# stays exercisable. Any real token would change the line count or the content
# and fail here.
if [ "$(wc -l < "$RUN/home/.local/share/github-tokens")" -ne 1 ] ||
  [ "$(cat "$RUN/home/.local/share/github-tokens")" != "fixture-pool-token" ]; then
  echo "abort: the fixture comment-token pool is not intact" >&2
  exit 1
fi
if [ ! -x "$RUN/claude-bin/claude" ]; then
  echo "abort: the staged agent CLI is missing or not executable" >&2
  exit 1
fi
# The agent's HOME is the run's own directory, so nothing under the host home
# is reachable by a relative path. The masks above still cover the absolute
# host paths, so neither route reaches a real credential. These check the
# isolated home the run is about to hand over, not the ambient one.
if [ "$RUN/home" = "$HOME_DIR" ] || [ "$RUN/home" = / ]; then
  echo "abort: the isolated home resolves to the host home" >&2
  exit 1
fi
if [ ! -d "$RUN/home/.claude" ]; then
  echo "abort: the isolated home has no .claude directory" >&2
  exit 1
fi
# The stand-in must authorize a POST from the fixture token and refuse one
# without it. Without this, a recording could show a follow-up (or the end of
# it) that the real service would have rejected, because the stand-in stamped
# the pool's login on every POST regardless of what the request presented. The
# probe runs against its own copy, so it leaves this run's facts, state and
# trace untouched.
PROBE="$RUN/probe"
mkdir -p "$PROBE"
cp "$RUN/gh" "$PROBE/gh"
sed -i "s#^RUN = .*#RUN = Path(\"$PROBE\")#" "$PROBE/gh"
cp "$RUN/facts.json" "$PROBE/facts.json"
probe_post() {
  # probe_post TOKEN: return the stand-in's status for a comment POST.
  GH_TOKEN=$1 GH_CONFIG_DIR="$RUN/gh-config" timeout 10 "$PROBE/gh" api \
    --method POST repos/leynos/agent-helper-scripts/issues/272/comments \
    -f body=probe >/dev/null 2>&1
}
if probe_post ""; then
  echo "abort: the stand-in accepted a comment POST with no token" >&2
  exit 1
fi
if probe_post "fixture-pool-token"; then
  :
else
  echo "abort: the stand-in refused the fixture token" >&2
  exit 1
fi
# The refusal must be about the token and not the starting state. The POST
# above is now recorded, so a stand-in that wrote the comment before checking
# the credential would overwrite it here and look identical to one that
# refused cleanly. A wrong token must leave the accepted comment in place.
probe_post "wrong-token" || true
if ! python3 - "$PROBE/state.json" <<'PROBE_AUTHZ'
import json, sys

# A refused POST must not reach the record. Reading the body rather than the
# file's existence is what distinguishes "refused" from "accepted and
# replaced": both leave a state file, and only one leaves the right body.
#
# Every accepted comment is examined, not just the latest. The record holds one
# entry per accepted POST, so a run that posts twice has two comments and a
# stand-in that overwrote the first would still satisfy a check on the last.
state = json.load(open(sys.argv[1], encoding="utf-8"))
posted = state.get("posted") or []
bodies = [entry.get("body") for entry in posted]
if bodies != ["probe"]:
    print(
        f"abort: a wrong-token POST changed the recorded comments to {bodies!r}",
        file=sys.stderr,
    )
    raise SystemExit(1)
PROBE_AUTHZ
then
  exit 1
fi
echo "isolation: credential stores are masked, the pool is the fixture, HOME is isolated, and the stand-in authorizes only the fixture token"

cd "$RUN/work" || exit 1
# The environment is cleared rather than filtered: only what this run needs is
# passed, so no ambient token, config override or path reaches the agent.
exec env -i \
  PATH="$RUN:$RUN/claude-bin:/usr/bin:/bin" \
  HOME="$RUN/home" \
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

ASSIGNMENT=$(cat <<'PROMPT'
You are the PR lifecycle supervisor for leynos/agent-helper-scripts pull
request 272. Carry this PR from its current state to readiness, following the
shipped `pr-babysitting` skill in your working directory.

Start at `pr-babysitting/SKILL.md` and read the references it points to for
this assignment. `gh` on PATH serves this PR's current GitHub state; it is the
only GitHub client available here, so use it for every read and lifecycle
command.

`cs` on PATH is this rehearsal's stand-in for the local CodeScene check. It is
the only local CodeScene source this environment has, and it discloses in its
own output that it is simulated. Treat its answer as the local result for this
run, whatever that answer is.

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
RUN="$RUN" CLAUDE_BIN="$CLAUDE_BIN" \
  ASSIGNMENT="$ASSIGNMENT" EVENTS="$EVENTS" \
  HOME_DIR="$HOME_DIR" CREDENTIALS_FILE="$CREDENTIALS_FILE" \
  MODEL_ADDRS="$MODEL_ADDRS" DNS_ADDRS="$DNS_ADDRS" \
  pasta --config-net -t none -u none -- /bin/bash "$RUN/outer.sh"
rc=$?
echo "agent rc: $rc"
echo "--- gh invocations ---"
cat "$TRACE"
# The simulated local CodeScene result is its own evidence surface: a run that
# never invoked `cs` cannot have cleared the local half, whatever its outcome
# says. The mode is printed with each call so a reader sees what it was asked.
CS_TRACE=$RUN/cs-trace.jsonl
echo "--- cs invocations (simulated) ---"
if [ -f "$CS_TRACE" ]; then cat "$CS_TRACE"; else echo "(none)"; fi
# The submitted bodies are evidence in their own right: the trace shows that a
# POST happened, but only the body shows what it asked. Print the body, and
# fail the run when a POST recorded something the stand-in would have refused,
# so a recording cannot claim a follow-up the real service would have rejected.
if [ -f "$RUN/state.json" ]; then
  python3 - "$RUN/state.json" "$SUBMITTED" <<'PROBE_BODY' || rc=1
import json, sys

state = json.load(open(sys.argv[1], encoding="utf-8"))
posted = state.get("posted") or []
if not posted:
    print("posted comment: none", file=sys.stderr)
    raise SystemExit(0)
authors = {entry.get("user", {}).get("login") for entry in posted}
if authors != {"fixture-commenter"}:
    print(f"abort: a posted comment is authored by {authors!r}", file=sys.stderr)
    raise SystemExit(1)
bodies = [entry.get("body", "") for entry in posted]
for index, body in enumerate(bodies, 1):
    print(f"--- posted {index}/{len(bodies)} by fixture-commenter, {len(body)} chars ---")
    print(body)
# Keep the bodies beside the trace for review: the trace records that a POST
# happened, and this records what it asked. A run may post two follow-ups when
# both assessments are renewed, so every body is written, separated by a header
# naming which post it was. A single-post run writes one body with no header,
# which is what the committed recordings already hold. It is written to the run
# directory rather than the repository, so a rehearsal never edits a tracked
# file and the operator chooses what to commit, as with the trace and the
# outcome.
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    if len(bodies) == 1:
        handle.write(bodies[0] + "\n")
    else:
        for index, body in enumerate(bodies, 1):
            handle.write(f"--- posted comment {index} of {len(bodies)} ---\n")
            handle.write(body + "\n")
print(f"--- submitted body: {sys.argv[2]} ---")
PROBE_BODY
fi
# Assert the outcome the scenario exists to pin. A trace shows what the agent
# read; only this shows what it decided. Each expectation is the readiness
# transition the scenario is built to permit or refuse, and a run that decides
# otherwise fails here rather than being filed as a fresh recording.
EXPECT_READY=no
case $SCENARIO in
  current-whole-plan | proof-only-cleared | combined-plan-and-proof)
    EXPECT_READY=yes
    ;;
esac
# Read the local CodeScene mode this run was given. A scenario whose local
# evidence is a finding or unavailable must not transition, whatever its other
# evidence says: that is the rule section 4 states, and asserting it here is
# what stops an outcome from waiving a source it never evaluated.
CS_MODE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("cs_mode",""))' "$RUN/facts.json")
echo "outcome: local CodeScene mode=$CS_MODE"
if [ "$EXPECT_READY" = yes ] && [ "$CS_MODE" = unavailable ]; then
  echo "abort: '$SCENARIO' is written to permit a transition but its local CodeScene result is unavailable" >&2
  rc=1
fi
if [ "$EXPECT_READY" = yes ] && [ "$CS_MODE" = finding ]; then
  echo "abort: '$SCENARIO' is written to permit a transition but its local CodeScene result lists a finding" >&2
  rc=1
fi
# A permitting run must have asked for the local result at all. Marking ready
# without reading it is the waiver the rule forbids, and an outcome that merely
# says the tool was missing is not evidence that it was consulted.
if [ "$EXPECT_READY" = yes ] && [ ! -s "$CS_TRACE" ]; then
  echo "abort: '$SCENARIO' marked the PR ready without invoking the local CodeScene check" >&2
  rc=1
fi
# Non-empty is not enough: `cs version` touches no code, and the two traces are
# written by different processes, so their orderings are independent. A delta
# run after `pr ready` would clear a candidate that had already been judged.
# The stand-in appends a boundary line to `cs-trace.jsonl` at the moment `pr
# ready` is served, so both events land in one file and their order is the
# file's order rather than an inference from two clocks.
if [ "$EXPECT_READY" = yes ] && [ -s "$CS_TRACE" ]; then
  # The boundary count is read from parsed entries, not from a `grep` over the
  # file text. The stand-in writes its line with `json.dumps` separators, so a
  # pattern matching `"event": "pr-ready"` agrees with it only by coincidence:
  # a change to either separator would silently make every run look as though
  # no transition had been recorded.
  delta_before=$(python3 - "$CS_TRACE" "$ROOT/scenarios/$SCENARIO/facts.json" <<'PROBE_DELTA'
import json, sys

trace, facts_path = sys.argv[1], sys.argv[2]
facts = json.load(open(facts_path, encoding="utf-8"))
base = facts["pr"]["baseRefOid"]
head = facts["pr"]["headRefOid"]
entries = []
for line in open(trace, encoding="utf-8"):
    try:
        entries.append(json.loads(line))
    except json.JSONDecodeError:
        print("malformed trace line", file=sys.stderr)
        raise SystemExit(2)
boundaries = [i for i, e in enumerate(entries) if e.get("event") == "pr-ready"]
if len(boundaries) != 1:
    # The count is the answer, so the shell can say which boundary rule failed.
    # Anything but exactly one is a refusal: none means the run never
    # transitioned, and more than one means the trace cannot be read as a
    # single decision.
    print(f"boundaries={len(boundaries)}")
    raise SystemExit(1)
seen_delta = False
for entry in entries[:boundaries[0]]:
    argv = entry.get("argv") or []
    # The candidate-bound delta is the call that names both endpoints. A bare
    # `cs delta` reads the working tree, which this sandbox does not have, so
    # it cannot be the evidence a readiness decision rests on.
    if len(argv) >= 3 and argv[0] == "delta" and base in argv and head in argv:
        seen_delta = True
print("yes" if seen_delta else "no")
raise SystemExit(0 if seen_delta else 1)
PROBE_DELTA
  ) || true
  # Everything after the boundary is the run's own read-back, which is not
  # evidence for the decision it follows, so the probe stops at it.
  case $delta_before in
    yes) echo "outcome: candidate-bound 'cs delta' read before 'pr ready'" ;;
    boundaries=0)
      echo "abort: '$SCENARIO' has no transition boundary in the local CodeScene trace" >&2
      rc=1
      ;;
    boundaries=*)
      echo "abort: '$SCENARIO' records more than one transition boundary" >&2
      rc=1
      ;;
    *)
      echo "abort: '$SCENARIO' marked ready without a candidate-bound 'cs delta' before the transition" >&2
      rc=1
      ;;
  esac
fi
# A plan-bearing run must read the plan file before deciding, and read it for
# the head it is judging. `current-whole-plan` reconciles the echo against the
# revision in force, which is only evidence if the read came first; accepting
# the verdict's own echo would clear a superseded revision.
# `combined-plan-and-proof` applies for the same reason, and with more force:
# it is the only permitting run where two assessments must both clear, so the
# revision binding cannot be inferred from a single verdict's echo.
#
# Four holding combined cases are held to the same read, because each exists
# for a ground that is a fact about the plan file: a verdict recorded against a
# revision the file no longer states (both verdicts, or the proof one alone), one
# that states no revision at all, and a reply whose assessed head is not this
# candidate's while the plan is the only surface naming the revision it echoes. A
# run that never read the plan could not have established any of them, so its
# hold would be for some other reason. A holding run is not held to the
# read-back: there is no transition to read.
#
# `combined-proof-pending` and `combined-proof-stale-verdict` are deliberately
# absent. Their grounds are the state of the proof verdict itself — unfinished,
# or clear for a head that is not this candidate — and neither is decided by
# anything the plan file says. A pending verdict cannot clear at any revision,
# so a run that held without reading the plan held for exactly the right
# reason; requiring the read there would demand evidence the decision does not
# rest on, and a recording made to satisfy it would demonstrate nothing extra.
case $SCENARIO in
  current-whole-plan | combined-plan-and-proof | combined-proof-stale-plan-revision | combined-proof-stale-revision | combined-proof-unbound-revision | combined-proof-candidate-mismatch)
    plan_line=$(grep -n 'contents/docs/execplans/.*ref=' "$TRACE" | head -1 | cut -d: -f1)
    ready_line=$(grep -n '"pr", "ready"' "$TRACE" | head -1 | cut -d: -f1)
    if [ -z "$plan_line" ]; then
      echo "abort: '$SCENARIO' decided without reading the plan file" >&2
      rc=1
    elif [ -n "$ready_line" ] && [ "$plan_line" -gt "$ready_line" ]; then
      echo "abort: '$SCENARIO' read the plan after the transition, not before it" >&2
      rc=1
    elif ! python3 - "$TRACE" "$ANSWERS" "$ROOT/scenarios/$SCENARIO/facts.json" "$EXPECT_READY" <<'PROBE_PLAN'
import json, re, sys

trace_path, answers_path, facts_path, expect_ready = sys.argv[1:5]
facts = json.load(open(facts_path, encoding="utf-8"))
pr = facts["pr"]
# The candidate is the head, named either by its commit or by its branch. The
# base branch is not: the plan file there is `main`'s copy, so reading it and
# finding a revision says nothing about the revision on this PR. A ref that
# names neither is not the candidate either, so it cannot be the read the
# revision is reconciled against.
candidate_refs = {str(pr.get("headRefOid", "")), str(pr.get("headRefName", ""))} - {""}

def load(path):
    """Return one parsed entry per line, skipping blank and malformed lines."""
    entries = []
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append(None)
    return entries

trace = load(trace_path)
# The trace and the answer record are appended in the same order by the same
# process, so their indices name the same invocation.
answers = load(answers_path)
ready = next(
    (index for index, argv in enumerate(trace)
     if isinstance(argv, list) and argv[:2] == ["pr", "ready"]),
    None,
)
# A permitting run orders the plan read against its transition. A holding run
# has no transition to order against, and the decision is the end of the run,
# so every read it made is before that decision by construction. Requiring a
# transition here would make the three holding combined cases unrunnable, and
# skipping the check for them would accept a hold with no evidence behind it.
if ready is None and expect_ready != "no":
    print("no transition to order the plan read against", file=sys.stderr)
    raise SystemExit(1)
if ready is None:
    ready = len(trace)
if len(answers) != len(trace):
    print("the answer record and the trace disagree in length", file=sys.stderr)
    raise SystemExit(1)
# The read that clears the revision check is the one that is BOTH candidate-bound
# AND before the transition. Checking those separately let a run read `main`
# first and the head afterwards, satisfying each condition with a different
# call — so the revision reconciled was never the one the decision used.
problems = []
for index, argv in enumerate(trace[:ready]):
    if not isinstance(argv, list) or argv[:1] != ["api"]:
        continue
    if not any("contents/docs/execplans/" in str(arg) for arg in argv):
        continue
    refs = {
        str(arg).split("ref=", 1)[1].split("&", 1)[0]
        for arg in argv
        if "ref=" in str(arg)
    }
    if not refs & candidate_refs:
        continue
    # A read the agent could not use is not the read it reconciled. The answer
    # record holds the status and the text, so both are required here. A failed
    # or empty read is recorded and the scan continues: one unusable attempt
    # does not establish the rule, and it must not hide a later attempt that
    # does. Exiting on the first one aborted runs that had in fact read the
    # plan at the head they judged, and each rehearsal is a costly model run.
    answer = answers[index] or {}
    if answer.get("status") != 0:
        problems.append(f"candidate-bound plan read failed: {answer.get('status')}")
        continue
    served = str(answer.get("stdout", ""))
    if not served.strip():
        problems.append("candidate-bound plan read returned nothing")
        continue
    # Non-empty is not the same as revision-bearing. The verdict is reconciled
    # against the revision the plan file states, so a read that succeeded and
    # returned a file naming no revision leaves nothing to reconcile — and a
    # run that cleared on it would be evidence that the read happened, not that
    # the revision in force was established. The value is required, not any
    # particular one: `combined-proof-stale-revision` reads a plan that states
    # a revision superseding both replies, which is exactly why it must be
    # readable here.
    found = re.search(r"Plan revision:\s*(\S+)", served)
    if not found:
        problems.append("candidate-bound plan read names no plan revision")
        continue
    raise SystemExit(0)
for problem in problems:
    print(problem, file=sys.stderr)
print("no usable candidate-bound plan read before the transition", file=sys.stderr)
raise SystemExit(1)
PROBE_PLAN
    then
      echo "abort: '$SCENARIO' did not read the plan at the head it is judging" >&2
      rc=1
    else
      echo "outcome: plan read at the candidate head, before 'pr ready'"
    fi
    ;;
esac
# A refusing run whose whole purpose is the local gate must have read it too,
# or its hold could be for an unrelated reason.
case $SCENARIO in
  local-codescene-*)
    if [ ! -s "$CS_TRACE" ]; then
      echo "abort: '$SCENARIO' never invoked the local CodeScene check it exists to exercise" >&2
      rc=1
    fi
    ;;
esac
# `codescene-advisory` is the only scenario whose CodeScene check passes while
# its own output lists a finding. The choice is asserted rather than assumed: a
# run that marks it ready shows the gate reading the badge instead of the
# output, and fails here.
if [ "$SCENARIO" = codescene-advisory ] && ! grep -q 'check-runs' "$TRACE"; then
  echo "abort: '$SCENARIO' did not read the hosted check output at all" >&2
  rc=1
fi
# The combined permitting run is the only one where a transition needs both
# applicable assessments. A run that transitioned would otherwise be recorded
# as clearing the combined gate even if it never read the thread carrying the
# proof verdict, which is the coverage the scenario exists to add.
case $SCENARIO in
  combined-plan-and-proof)
    # The proof reply is the one entry in the recorded discussion that answers
    # the proof question; the completeness reply does not contain it. Reading
    # the discussion after the last assessment is what a readiness run does, so
    # the check is that the thread was read at all and that it carried both
    # markers. Both are asserted from the facts rather than from the trace's
    # text: the trace records the routes, and only the facts say what the
    # thread held.
    if ! python3 - "$ROOT/scenarios/$SCENARIO/facts.json" <<'PROBE_COMBINED'
import json, sys

# Both applicable assessments must be present on the recorded thread, and each
# reply must answer its own question. Without the pair the scenario does not
# describe a combined assignment, and a permitting run recorded from it would
# not be evidence that the combined gate clears.
facts = json.load(open(sys.argv[1], encoding="utf-8"))
bodies = [str(entry.get("body", "")) for entry in facts["api"][r"/issues/\d+/comments"]]
requests = [body for body in bodies if "Assessment-ID:" in body and "@coderabbitai" in body]
replies = [
    body for body in bodies
    if "**Verdict:" in body and "**Assessed subject:** `refinement_sound`" in body
]
if len(requests) != 2:
    print(f"combined scenario records {len(requests)} questions, expected 2", file=sys.stderr)
    raise SystemExit(1)
if len(replies) != 1:
    print(f"combined scenario records {len(replies)} proof replies, expected 1", file=sys.stderr)
    raise SystemExit(1)
raise SystemExit(0)
PROBE_COMBINED
    then
      echo "abort: '$SCENARIO' does not record a combined assignment" >&2
      rc=1
    fi
    ;;
esac
# Each holding combined case exists for exactly one reason, and the premise is
# a property of the recorded facts rather than of the recording. A run is
# accepted as evidence for "a stale revision does not clear" only if the
# revision really is stale, and likewise for the other two. Without this check
# a later edit to a scenario could remove the defect and leave the recording
# looking like a hold on the named ground when it was a hold on nothing.
case $SCENARIO in
  combined-proof-pending | combined-proof-stale-verdict | combined-proof-stale-plan-revision | combined-proof-stale-revision | combined-proof-unbound-revision | combined-proof-candidate-mismatch)
    if ! python3 - "$SCENARIO" "$ROOT/scenarios/$SCENARIO/facts.json" <<'PROBE_PREMISE'
import json, re, sys

name, facts_path = sys.argv[1:3]
facts = json.load(open(facts_path, encoding="utf-8"))
pr = facts["pr"]
bodies = [str(entry.get("body", "")) for entry in facts["api"][r"/issues/\d+/comments"]]
replies = [body for body in bodies if "**Verdict:" in body]


def filed(text, field):
    """Return the value a reply records for one field, or None."""
    found = re.search(rf"\*\*{field}:\*\*\s*(.+)", text)
    return found.group(1).strip() if found else None


def revision_of(text):
    """Return the plan revision a file's body states, or None."""
    found = re.search(r"Plan revision:\s*(\S+)", text)
    return found.group(1) if found else None


# The plan text the run could read, from its own contents route.
plan_text = "\n".join(
    str(payload.get("content", ""))
    for pattern, payload in facts["api"].items()
    if "contents/docs/execplans/" in pattern and isinstance(payload, dict)
)
revision_in_force = revision_of(plan_text)
proof_replies = [
    body for body in replies if "**Assessed subject:** `refinement_sound`" in body
]
problems = []
if len(proof_replies) != 1:
    problems.append(f"{len(proof_replies)} proof replies, expected 1")
else:
    proof = proof_replies[0]
    if name == "combined-proof-stale-revision":
        # Both replies echo a revision the plan file no longer states. That is
        # the whole premise: the replies are right about everything except the
        # revision that has since moved.
        echoed = {filed(body, "Plan revision") for body in replies}
        if echoed != {"rev-7"}:
            problems.append(f"replies echo {sorted(echoed)}, expected rev-7")
        if revision_in_force != "rev-8":
            problems.append(f"the plan file reads {revision_in_force!r}, expected rev-8")
        if {filed(body, "Assessed base/head") for body in replies} != {
            f"{pr['baseRefOid']}...{pr['headRefOid']}"
        }:
            problems.append("a reply assesses a base/head other than the PR's")
    elif name == "combined-proof-pending":
        # The proof reply states no verdict of its own: it says the scrutiny is
        # unfinished. The completeness reply in the same thread must be clear
        # for the candidate and the revision in force, or the hold could be
        # the completeness assessment's and the case would not isolate a
        # pending proof.
        if "**Verdict: pending**" not in proof:
            problems.append("the proof reply does not record a pending verdict")
        if "**Verdict: clear**" in proof:
            problems.append("the proof reply states a clear verdict")
        if filed(proof, "Plan revision") != revision_in_force:
            problems.append("the pending proof reply does not echo the revision in force")
        completeness = [body for body in replies if body not in proof_replies]
        if len(completeness) != 1:
            problems.append(f"{len(completeness)} completeness replies, expected 1")
        else:
            current = completeness[0]
            if "**Verdict: clear**" not in current:
                problems.append("the completeness reply is not clear")
            if filed(current, "Plan revision") != revision_in_force:
                problems.append("the completeness reply does not echo the revision in force")
            if filed(current, "Assessed base/head") != (
                f"{pr['baseRefOid']}...{pr['headRefOid']}"
            ):
                problems.append("the completeness reply assesses a base/head other than the PR's")
    elif name == "combined-proof-stale-verdict":
        # The proof reply is clear, current in revision, and the only thing
        # wrong with it is the head it assessed. The completeness reply must be
        # clear, current and bound to this candidate, so the hold isolates the
        # stale proof verdict rather than inheriting a stale completeness one.
        assessed = filed(proof, "Assessed base/head") or ""
        head = assessed.rsplit("...", 1)[-1]
        if "**Verdict: clear**" not in proof:
            problems.append("the proof reply is not clear")
        if head == pr["headRefOid"]:
            problems.append("the proof verdict assesses the PR's current head")
        if filed(proof, "Plan revision") != revision_in_force:
            problems.append("the proof reply does not echo the revision in force")
        completeness = [body for body in replies if body not in proof_replies]
        if len(completeness) != 1:
            problems.append(f"{len(completeness)} completeness replies, expected 1")
        else:
            current = completeness[0]
            if "**Verdict: clear**" not in current:
                problems.append("the completeness reply is not clear")
            if filed(current, "Plan revision") != revision_in_force:
                problems.append("the completeness reply does not echo the revision in force")
            if filed(current, "Assessed base/head") != (
                f"{pr['baseRefOid']}...{pr['headRefOid']}"
            ):
                problems.append("the completeness reply assesses a base/head other than the PR's")
    elif name == "combined-proof-stale-plan-revision":
        # The proof reply is clear and bound to this candidate; its only defect
        # is the plan revision it echoes. The completeness reply must echo the
        # revision now in force and be clear for this head, or the hold could be
        # the completeness assessment's and the case would not isolate a stale
        # proof revision.
        if "**Verdict: clear**" not in proof:
            problems.append("the proof reply is not clear")
        if filed(proof, "Assessed base/head") != (
            f"{pr['baseRefOid']}...{pr['headRefOid']}"
        ):
            problems.append("the proof reply assesses a base/head other than the PR's")
        echoed = filed(proof, "Plan revision")
        if echoed is None:
            problems.append("the proof reply echoes no plan revision")
        elif echoed == revision_in_force:
            problems.append("the proof reply echoes the revision in force")
        completeness = [body for body in replies if body not in proof_replies]
        if len(completeness) != 1:
            problems.append(f"{len(completeness)} completeness replies, expected 1")
        else:
            current = completeness[0]
            if "**Verdict: clear**" not in current:
                problems.append("the completeness reply is not clear")
            if filed(current, "Plan revision") != revision_in_force:
                problems.append("the completeness reply does not echo the revision in force")
            if filed(current, "Assessed base/head") != (
                f"{pr['baseRefOid']}...{pr['headRefOid']}"
            ):
                problems.append("the completeness reply assesses a base/head other than the PR's")
    elif name == "combined-proof-unbound-revision":
        # The proof reply is clear and bound to the candidate, and its only
        # defect is that it states no plan revision. The completeness reply in
        # the same thread must state one, or the case would be testing a thread
        # with no revision anywhere rather than a reply that failed to bind.
        if filed(proof, "Plan revision") is not None:
            problems.append("the proof reply states a plan revision")
        completeness = [body for body in replies if body not in proof_replies]
        if len(completeness) != 1 or filed(completeness[0], "Plan revision") != "rev-7":
            problems.append("the completeness reply does not state rev-7")
        if revision_in_force != "rev-7":
            problems.append(f"the plan file reads {revision_in_force!r}, expected rev-7")
    else:
        # The proof reply is otherwise complete: it echoes the revision in force
        # and is clear. What it assesses is a head that is not the PR's.
        assessed = filed(proof, "Assessed base/head") or ""
        head = assessed.rsplit("...", 1)[-1]
        if head == pr["headRefOid"]:
            problems.append("the proof reply assesses the PR's own head")
        if head not in assessed or len(head) < 4:
            problems.append(f"the reply's assessed head {head!r} is not a commit")
        if filed(proof, "Plan revision") != revision_in_force:
            problems.append("the proof reply does not echo the revision in force")
for problem in problems:
    print(problem, file=sys.stderr)
if problems:
    raise SystemExit(1)
raise SystemExit(0)
PROBE_PREMISE
    then
      echo "abort: '$SCENARIO' does not record the defect it exists to demonstrate" >&2
      rc=1
    fi
    ;;
esac
ready_calls=$(grep -c '"pr", "ready"' "$TRACE" 2>/dev/null || true)
if [ "$EXPECT_READY" = yes ] && [ "$ready_calls" -eq 0 ]; then
  echo "abort: '$SCENARIO' should mark the PR ready, but no 'pr ready' was issued" >&2
  rc=1
fi
if [ "$EXPECT_READY" = no ] && [ "$ready_calls" -ne 0 ]; then
  echo "abort: '$SCENARIO' should stay in draft, but 'pr ready' was issued" >&2
  rc=1
fi
# A permitting run must read the transition back, so its own evidence is the
# observed state rather than the command's exit status. The check is ordered:
# an initial `pr view` also carries `isDraft`, so a bare search would pass even
# if the read-back were removed. Everything after the last `pr ready` is
# examined, and a read of the draft state there is the transition observed.
if [ "$EXPECT_READY" = yes ]; then
  after=$(grep -n '"pr", "ready"' "$TRACE" | tail -1 | cut -d: -f1)
  if [ -z "$after" ]; then
    echo "abort: '$SCENARIO' has no 'pr ready' to read back" >&2
    rc=1
  else
    readback=$(tail -n "+$((after + 1))" "$TRACE" | grep -c 'isDraft' || true)
    if [ "$readback" -eq 0 ]; then
      echo "abort: '$SCENARIO' did not read isDraft back after the transition" >&2
      rc=1
    fi
    echo "outcome: read-back reads after 'pr ready': $readback"
  fi
  # The argv trace records attempts, so neither check above shows the read
  # succeeded. A `pr view` answered with an error, or one the shim refused,
  # still appears there. `gh-answers.jsonl` carries each invocation's exit
  # status and the text it printed, so the read the transition is judged on must
  # both succeed and carry a ready value: `pr view --json isDraft --jq 'null'`
  # exits zero and prints `null`, which would satisfy an exit status alone.
  if ! python3 - "$ANSWERS" <<'PROBE_READBACK'
import json, re, sys

try:
    answered = [
        json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()
    ]
except (OSError, json.JSONDecodeError) as error:
    print(f"unreadable answer record: {error}", file=sys.stderr)
    raise SystemExit(1)
# The answer record and the argv trace are appended in the same order, and the
# runner has already established that an isDraft read follows the transition.
# What this adds is the value: the transition is judged on a read that both
# succeeded and returned the ready state.
last_ready = max(
    (index for index, entry in enumerate(answered)
     if entry.get("argv", [])[:2] == ["pr", "ready"]),
    default=None,
)
if last_ready is None:
    print("no transition in the answer record", file=sys.stderr)
    raise SystemExit(1)
read_backs = [
    entry
    for entry in answered[last_ready:]
    if entry.get("argv", [])[:2] == ["pr", "view"]
    and "isDraft" in " ".join(entry["argv"])
]
if not read_backs:
    print("no isDraft read after the transition", file=sys.stderr)
    raise SystemExit(1)
failed = [entry for entry in read_backs if entry.get("status") != 0]
if failed:
    print(f"{len(failed)} read-back call(s) failed", file=sys.stderr)
    raise SystemExit(1)


def shows_ready(text: str) -> bool:
    """Return whether this answer states the PR is no longer a draft.

    The answer is what the agent read, so it may be the JSON object, a `--jq`
    reduced `false`, a JSON string `"false"`, or a template printing
    `false <ref>`. `null`, a missing field, and a `true` value are all
    not-ready. A caller that asked for the value and got nothing usable has not
    observed the transition, whatever the exit status.
    """
    stripped = text.strip()
    if not stripped:
        return False
    # A template's output is not JSON at all, so it lands in this branch: an
    # earlier version searched only for the `"isDraft": false` spelling here
    # and refused `false cccc3333`, which is a ready value a run may print.
    leading_false = re.fullmatch(r"false(?:\s.*)?", stripped) is not None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return leading_false or bool(re.search(r'"isDraft"\s*:\s*false', stripped))
    if isinstance(parsed, bool):
        return parsed is False
    if isinstance(parsed, dict):
        return parsed.get("isDraft") is False
    if isinstance(parsed, str):
        return re.fullmatch(r"false(?:\s.*)?", parsed.strip()) is not None
    return False


ready_values = [entry for entry in read_backs if shows_ready(str(entry.get("stdout", "")))]
if not ready_values:
    print(
        f"no read-back returned a ready state: "
        f"{[str(entry.get('stdout', ''))[:40] for entry in read_backs]}",
        file=sys.stderr,
    )
    raise SystemExit(1)
print(f"read-back values: {[str(entry.get('stdout', '')).strip()[:40] for entry in ready_values]}")
raise SystemExit(0)
PROBE_READBACK
  then
    echo "abort: '$SCENARIO' transitioned but no successful read-back observed a ready state" >&2
    rc=1
  fi
  # `state.json` is the value the stand-in served from, so reading it here is
  # what makes the observed transition a value rather than a call.
  if ! python3 - "$STATE" <<'PROBE_STATE'
import json, sys
state = json.load(open(sys.argv[1]))
sys.exit(0 if state.get("isDraft") is False else 1)
PROBE_STATE
  then
    echo "abort: '$SCENARIO' transitioned but the served state still reads draft" >&2
    rc=1
  fi
fi
echo "outcome: expected ready=$EXPECT_READY, 'pr ready' calls=$ready_calls"

# Propagate the agent's own status. A rehearsal that was killed by its budget,
# timed out, or aborted on an isolation check is not a successful run, and an
# automation reading this script's status must not mistake it for one.
if [ "$rc" -ne 0 ]; then
  echo "sandboxed_run.sh: run failed with status $rc; see above" >&2
  exit "$rc"
fi
exit 0
