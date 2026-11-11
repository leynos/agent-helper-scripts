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
# The scenario says which shipped skill the run starts at. A crossing case
# rehearses the implementation handoff: the run has to open `sdlc-implementation`,
# produce the packet and carry it into `pr-babysitting`. It cannot be inferred
# from the recorded GitHub facts, because both prompts read the same PR, so the
# scenario states it. A case that names nothing keeps the receiver-only prompt
# its committed recording was made under, byte for byte.
START_SKILL=$(python3 -c '
import json, sys
facts = json.load(open(sys.argv[1], encoding="utf-8"))
print(facts.get("start_skill", "pr-babysitting"))
' "$ROOT/scenarios/$SCENARIO/facts.json" 2>/dev/null)
case $START_SKILL in
  pr-babysitting | sdlc-implementation) ;;
  *)
    echo "sandboxed_run.sh: unknown start_skill '$START_SKILL'" >&2
    exit 2
    ;;
esac
# SKILL_SRC names the candidate's `skills` directory, matching the README. A
# crossing run needs both skills on disk, because the packet is produced by the
# sender and carried into the receiver; a receiver-only run is given the
# receiver alone, so it sees the working directory its recording was made in.
SKILLS_DIR=${SKILL_SRC:?set SKILL_SRC to the candidate skills directory}
if [ "$START_SKILL" = sdlc-implementation ]; then
  STAGED_SKILLS="sdlc-implementation pr-babysitting"
else
  STAGED_SKILLS=pr-babysitting
fi
for skill in $STAGED_SKILLS; do
  if [ ! -f "$SKILLS_DIR/$skill/SKILL.md" ]; then
    echo "sandboxed_run.sh: $SKILLS_DIR/$skill/SKILL.md not found" >&2
    exit 2
  fi
done
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
for skill in $STAGED_SKILLS; do
  cp -R "$SKILLS_DIR/$skill" "$RUN/work/$skill"
done
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
# A crossing scenario gets its own prompt, which names the handoff as the
# artefact that must cross. Every other scenario keeps the prompt its committed
# recording was made under, byte for byte: editing the receiver prompt would
# leave seventeen recordings describing a run nobody can repeat.
if [ "$START_SKILL" = sdlc-implementation ]; then
  ASSIGNMENT=$(cat <<'PROMPT'
You are the implementation-and-delivery supervisor for
leynos/agent-helper-scripts pull request 272. Both shipped skills are in your
working directory, and you must use both, in the order the lifecycle states.

Start at `sdlc-implementation/SKILL.md`. Read it and the references it points
to, decide what the implementation handoff requires for this candidate, and
produce that handoff. Then cross into `pr-babysitting/SKILL.md` carrying the
handoff you just produced, and carry this PR from its current state to
readiness following that skill.

`gh` on PATH serves this PR's current GitHub state; it is the only GitHub
client available here, so use it for every read and lifecycle command.

`cs` on PATH is this rehearsal's stand-in for the local CodeScene check. It is
the only local CodeScene source this environment has, and it discloses in its
own output that it is simulated. Treat its answer as the local result for this
run, whatever that answer is.

Do the work the skills call for at this point in the lifecycle and stop where
they stop. Print the handoff packet, as one block titled `HANDOFF PACKET` with
each field on its own line, as the message that hands delivery over: it must
appear before any readiness transition you take, not only in your last message,
because the receiver applies the packet rather than quoting it afterwards.
Finish by stating in one sentence what you did and quoting the deciding
evidence you relied on.
PROMPT
  )
fi
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
# The agent's final message is evidence in its own right, and it is the only
# place a crossing run's handoff is written down. Extract it from the event
# stream rather than leaving the operator to find it: the same extraction is
# what the crossing assertion below reads, so the text a recording is checked
# against and the text committed as `outcomes/<name>.txt` are one artefact. A
# run that produced no result event leaves no file, and a crossing run then
# fails its assertion rather than passing on an absent message.
OUTCOME=$RUN/outcome.txt
python3 - "$EVENTS" "$OUTCOME" <<'PROBE_OUTCOME'
import json, sys

events_path, outcome_path = sys.argv[1:3]
try:
    stream = open(events_path, encoding="utf-8")
except FileNotFoundError:
    # An aborted run never started the CLI, so there is no message to record.
    # That is reported rather than raised: the run's status already says it
    # failed, and a traceback here would bury it.
    print("the run produced no event stream", file=sys.stderr)
    raise SystemExit(0)
final = None
for line in stream:
    if not line.strip():
        continue
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    # The last result event is the message the CLI ended with. Keeping the
    # last rather than the first means a run that emitted more than one (a
    # retry, say) is described by the message it actually finished on.
    if event.get("type") == "result" and isinstance(event.get("result"), str):
        final = event["result"]
if final is None:
    print("no result event in the agent's event stream", file=sys.stderr)
    raise SystemExit(0)
open(outcome_path, "w", encoding="utf-8").write(final + "\n")
print("--- agent final message ---")
print(final)
PROBE_OUTCOME
# A crossing run's ordering evidence is what it did and in what order, and that
# lives in the event stream, which is far too large to commit. What matters is
# each assistant message's parts in the order it emitted them, and whether each
# call it made succeeded — a `cat` that failed printed no manifest, so a
# recording that dropped the outcome could not tell a read from an attempt.
# Usage counters, session bookkeeping and the *contents* of each result are
# dropped: the probe reads the outcome, and committing a skill's text would
# bloat the evidence without adding anything to it. The reduced transcript keeps
# the event shape the handoff probe reads, so the committed evidence is checked
# by the same probe the run used rather than by a second reader.
TRANSCRIPT=$RUN/transcript.jsonl
python3 - "$EVENTS" "$TRANSCRIPT" <<'PROBE_TRANSCRIPT'
import json, sys

events_path, transcript_path = sys.argv[1:3]
try:
    stream = open(events_path, encoding="utf-8")
except FileNotFoundError:
    print("the run produced no event stream", file=sys.stderr)
    raise SystemExit(0)
messages = []
for line in stream:
    if not line.strip():
        continue
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    if event.get("type") not in ("assistant", "user"):
        continue
    parts = [
        part
        for part in event.get("message", {}).get("content", [])
        if isinstance(part, dict)
    ]
    if event["type"] == "user":
        # A call's result is kept as its outcome alone. `is_error` is absent on
        # a successful result from some tools, so only a truthy flag is a
        # failure; writing the normalized flag keeps that difference out of
        # every reader of the recording.
        kept = [
            {
                "type": "tool_result",
                "tool_use_id": str(part.get("tool_use_id", "")),
                "is_error": bool(part.get("is_error")),
            }
            for part in parts
            if part.get("type") == "tool_result"
        ]
        if kept:
            messages.append({"type": "user", "message": {"content": kept}})
        continue
    kept = [
        {"type": "text", "text": part.get("text", "")}
        for part in parts
        if part.get("type") == "text" and part.get("text")
    ]
    kept += [
        {
            "type": "tool_use",
            "id": str(part.get("id", "")),
            "name": part.get("name", ""),
            "input": part.get("input", {}),
        }
        for part in parts
        if part.get("type") == "tool_use"
    ]
    if kept:
        messages.append({"type": "assistant", "message": {"content": kept}})
with open(transcript_path, "w", encoding="utf-8") as out:
    for message in messages:
        out.write(json.dumps(message) + "\n")
calls = sum(
    len(message["message"]["content"])
    for message in messages
    if message["type"] == "assistant"
)
results = sum(
    len(message["message"]["content"])
    for message in messages
    if message["type"] == "user"
)
print(f"transcript: {calls} assistant parts, {results} tool results from {events_path}")
PROBE_TRANSCRIPT
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
scripted = state.get("scripted") or []
if not posted:
    print("posted comment: none", file=sys.stderr)
    raise SystemExit(0)
authors = {entry.get("user", {}).get("login") for entry in posted}
if authors != {"fixture-commenter"}:
    print(f"abort: a posted comment is authored by {authors!r}", file=sys.stderr)
    raise SystemExit(1)
# A scripted answer is not a submitted body. It is the stand-in's verdict, and
# writing it into `submitted/` would present a fixture's own words as the
# request the run asked. It is reported separately, with its marker, so the
# recording still shows what answered the run.
for entry in scripted:
    body = entry.get("body", "")
    if "gh-stand-in: scripted reply" not in body:
        print("abort: a scripted reply does not disclose that it is scripted",
              file=sys.stderr)
        raise SystemExit(1)
    print(f"--- scripted reply {entry.get('id')}: {body.splitlines()[0]} ---")
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
  current-whole-plan | proof-only-cleared | combined-plan-and-proof | posted-then-answered | crossing-whole-plan)
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
# Three holding combined cases are held to the same read, because each exists
# for a ground that is a fact about the plan file: a verdict recorded against a
# revision the file no longer states (both verdicts, or the proof one alone) or
# one that states no revision at all. A run that never read the plan could not
# have established any of them, so its hold would be for some other reason. A
# holding run is not held to the read-back: there is no transition to read.
#
# `combined-proof-pending`, `combined-proof-stale-verdict` and
# `combined-proof-candidate-mismatch` are deliberately absent. Their grounds are
# the state of the proof verdict itself — unfinished, clear for a head that is
# not this candidate, and clear for a head the repository does not serve — and
# none is decided by anything the plan file says. A pending verdict cannot clear
# at any revision, and a verdict naming another head is disqualified by the head
# alone, so a run that held without reading the plan held for exactly the right
# reason; requiring the read there would demand evidence the decision does not
# rest on, and a recording made to satisfy it would demonstrate nothing extra.
# The last two share one premise, and holding only one of them to the read made
# the check depend on how a run happened to investigate rather than on what the
# hold rests on.
#
# `posted-then-answered` is the opposite case, and its absence was the
# dangerous one: it is a permitting run, so a transition taken without a
# candidate-bound read would be a cleared gate on a revision the run never
# established. It asks the question itself rather than being handed one, but
# the reply it receives echoes the revision its own request named, so the
# echo alone cannot show the revision was checked against the file. The read is
# required here for the same reason it is required of the other permitting
# cases.
#
# The approved path is read from the scenario's facts, so this shell-level
# ordering check and the probe below name the same file. A fixture with no
# name to compare against is refused rather than skipped.
plan_path=$(python3 -c '
import json, sys
facts = json.load(open(sys.argv[1], encoding="utf-8"))
print(facts.get("plan_path", ""))
' "$ROOT/scenarios/$SCENARIO/facts.json" 2>/dev/null)
case $SCENARIO in
  current-whole-plan | crossing-whole-plan | posted-then-answered | combined-plan-and-proof | combined-proof-stale-plan-revision | combined-proof-stale-revision | combined-proof-unbound-revision)
    # The approved path, not any file below `execplans/` and not a bare
    # `contents/docs/execplans` listing. The grep only decides whether this
    # ordering check runs at all; the probe below decides which read counts,
    # and it holds the read to the same approved path.
    #
    # The trailing `?` is the same terminator `reads_approved_plan` applies:
    # without it, `-F` matches a longer path that merely contains this one, so
    # a read of `issue-271-readiness-handoff.md.bak?ref=…` would be counted as
    # a read of the approved file and this check would pass on the wrong file.
    # Every candidate-bound read carries `?ref=`, so the query is the boundary.
    #
    # `-n` is required rather than cosmetic: without it the first match is the
    # whole trace line, so `plan_line` holds JSON instead of a line number and
    # the comparison below reports `integer expression expected` and silently
    # decides nothing.
    plan_line=$(grep -nF "contents/$plan_path?" "$TRACE" | grep -F 'ref=' | head -1 | cut -d: -f1)
    ready_line=$(grep -n '"pr", "ready"' "$TRACE" | head -1 | cut -d: -f1)
    if [ -z "$plan_path" ]; then
      echo "abort: '$SCENARIO' names no approved plan path" >&2
      rc=1
    elif [ -z "$plan_line" ]; then
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
# The approved plan path, named exactly. The route and the trace both used to
# accept any file below `execplans/`, so a run that asked for another plan and
# was served the approved payload cleared a check whose subject is the revision
# in force in this file. A fixture with no name to compare against cannot be
# checked at all, so it is refused rather than skipped.
plan_path = str(facts.get("plan_path", ""))
if not plan_path:
    print("the scenario names no approved plan path", file=sys.stderr)
    raise SystemExit(1)
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

def contents_text(served):
    """Return the file text a contents answer carries, or the text itself."""
    try:
        payload = json.loads(served)
    except json.JSONDecodeError:
        return served
    if isinstance(payload, dict) and isinstance(payload.get("content"), str):
        return payload["content"]
    return served

def revision_in(text):
    """Return the plan revision a file's text states, or None."""
    found = re.search(r"Plan revision:\s*(\S+)", text)
    return found.group(1) if found else None

def served_path(served):
    """Return the path a contents answer names, or None when it names none.

    A filtered response carries no metadata, so an answer with no `path` is
    still usable; one that names a path is held to the approved one.
    """
    try:
        payload = json.loads(served)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and isinstance(payload.get("path"), str):
        return payload["path"]
    return None

plan_marker = f"contents/{plan_path}"

def reads_approved_plan(argument):
    """Return whether one argv entry asks for the approved plan path itself.

    The marker must end the path or be followed by a query or fragment, so a
    read of `.../issue-271-readiness-handoff.md.bak` or of a path that merely
    contains this one is not mistaken for a read of the approved file.
    """
    text = str(argument)
    found = text.find(plan_marker)
    if found < 0:
        return False
    tail = text[found + len(plan_marker):]
    return tail == "" or tail[:1] in "?#"

# The revision the scenario's own plan route serves. This is the value a read
# has to reproduce: the probe previously required only that some revision was
# named, so a run that read a file stating any revision at all cleared a check
# whose whole subject is the revision in force. Reading it from the facts makes
# the assertion compare, rather than merely observe, and a later premise edit
# that moved the file is caught here instead of silently weakening the case.
# The route is the approved path, not any file below `execplans/`: a listing
# entry or another plan's body is not what the verdict is reconciled against.
# The route is selected by matching its own pattern against the approved URL
# rather than by searching the pattern's text, so the generator's escaping is
# not a second thing the probe has to reproduce.
approved_url = (
    f"{facts['coords']['repository']}/contents/{plan_path}"
)
served_revisions = {
    revision_in(str(payload.get("content", "")))
    for pattern, payload in facts["api"].items()
    if isinstance(payload, dict) and re.search(pattern, approved_url)
} - {None}
if len(served_revisions) != 1:
    print(
        f"the scenario's plan route states {sorted(served_revisions)},"
        " expected exactly one revision to reconcile against",
        file=sys.stderr,
    )
    raise SystemExit(1)
revision_in_force = served_revisions.pop()

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
    if not any(reads_approved_plan(arg) for arg in argv):
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
    # A contents answer names the file it served. When it does, the name must
    # be the approved one: a route that answered the request with another
    # file's metadata would otherwise pass on the requested path alone, which
    # is the request rather than what was read. A filtered response carries no
    # metadata at all, and is judged on its text alone.
    named = served_path(served)
    if named is not None and named != plan_path:
        problems.append(
            f"candidate-bound plan read returned {named!r},"
            f" not the approved {plan_path!r}"
        )
        continue
    # Non-empty is not the same as revision-bearing, and revision-bearing is not
    # the same as revision-carrying-the-right-value. The verdict is reconciled
    # against the revision the plan file states, so a read that succeeded and
    # returned a file naming no revision leaves nothing to reconcile, and one
    # naming a different revision leaves the wrong thing to reconcile — a run
    # that cleared on either would be evidence that the read happened, not that
    # the revision in force was established. The value must be the one the
    # scenario's own plan route serves. `combined-proof-stale-revision` reads a
    # plan that states a revision superseding both replies: the hold is that the
    # replies are stale, so the read has to carry the newer revision, and an
    # equality check is what distinguishes it from a read of anything at all.
    found = revision_in(contents_text(served))
    if found is None:
        problems.append("candidate-bound plan read names no plan revision")
        continue
    if found != revision_in_force:
        problems.append(
            f"candidate-bound plan read states {found!r},"
            f" not the {revision_in_force!r} the route serves"
        )
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
# The combined permitting run judges two subjects, so a recording of it is
# evidence for the plan read only if it also read the proof. The README said it
# read both routes while the trace read the plan alone: nothing asserted the
# second read, so the claim drifted from the recording it described. A run that
# assessed the proof from its request's inventory alone never looked at the
# proof, and its clear verdict would rest on a paraphrase rather than the file.
#
# The read has to be the one that could answer the question. A bare search for a
# proof route accepts a read of some other ref, a read that failed, and a read
# after the transition — none of which is evidence that the assessed proof was
# inspected. This requires the same three properties the plan read is held to,
# against the proof path rather than the plan path.
case $SCENARIO in
  combined-plan-and-proof)
    if ! python3 - "$TRACE" "$ANSWERS" "$ROOT/scenarios/$SCENARIO/facts.json" <<'PROBE_PROOF_READ'
import json, re, sys

trace_path, answers_path, facts_path = sys.argv[1:4]
facts = json.load(open(facts_path, encoding="utf-8"))
pr = facts["pr"]
proof_path = facts["proof_path"]
candidate_refs = {str(pr.get("headRefOid", "")), str(pr.get("headRefName", ""))} - {""}
# The text the assessed proof states: statement and body, as the route serves
# it. The subject of the assessment is what the proof claims *and* how it
# discharges the claim, so an answer holding only the declaration header — or
# only the file's metadata — does not show the agent the thing it judged. An
# earlier version anchored on `theorem <name> :` alone, which the first line of
# the file satisfies on its own; the whole served text is what is required
# here, so omitting the body is refused however the read was filtered.
# `--jq .sha` exits zero and prints a hash, which is exactly the answer a run
# that never saw the file produces, so the text has to be required rather than
# the exit status alone.
proof_text = "\n".join(
    str(payload.get("content", ""))
    for pattern, payload in facts["api"].items()
    if isinstance(payload, dict) and re.search(pattern, f"/contents/{proof_path}")
).strip()
if not re.search(r"theorem\s+\w+\s*:", proof_text):
    print(
        "the scenario's proof route serves no theorem for a read to find",
        file=sys.stderr,
    )
    raise SystemExit(1)

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

def proof_body(served):
    """Return the text a contents answer carries, or the text itself.

    A filtered answer is the file's text, and unwrapped it is that text. The
    metadata around `content` is not read as the proof: a payload whose
    `content` is absent or is not text carries no proof at all.
    """
    try:
        payload = json.loads(served)
    except json.JSONDecodeError:
        return served
    if isinstance(payload, dict):
        content = payload.get("content")
        return content if isinstance(content, str) else ""
    return served

def read_complete_proof(served):
    """Return whether one answer shows the whole proof the route serves.

    The comparison is against the served text rather than against a prefix of
    it. The declaration header, `theorem refinement_sound :`, appears on the
    file's first line and would satisfy a check for the theorem alone, so a
    filtered read that stopped there — or a `--jq .content` reduced to the
    first line — would pass while the body it is judged on was never seen.
    Whitespace is normalized because a run may print the text with trailing
    blank lines trimmed; the statements and the discharge have to be there.
    """
    carried = " ".join(proof_body(served).split())
    return " ".join(proof_text.split()) in carried

def names_proof(argument):
    """Return whether one argv entry asks for the assessed proof itself."""
    text = str(argument)
    found = text.find(f"contents/{proof_path}")
    if found < 0:
        return False
    tail = text[found + len(f"contents/{proof_path}"):]
    return tail == "" or tail[:1] in "?#"

trace = load(trace_path)
# The trace and the answer record are appended in the same order by the same
# process, so their indices name the same invocation.
answers = load(answers_path)
ready = next(
    (index for index, argv in enumerate(trace)
     if isinstance(argv, list) and argv[:2] == ["pr", "ready"]),
    None,
)
if ready is None:
    print("the permitting run has no transition to order the proof read against",
          file=sys.stderr)
    raise SystemExit(1)
if len(answers) != len(trace):
    print("the answer record and the trace disagree in length", file=sys.stderr)
    raise SystemExit(1)
problems = []
for index, argv in enumerate(trace[:ready]):
    if not isinstance(argv, list) or argv[:1] != ["api"]:
        continue
    if not any(names_proof(arg) for arg in argv):
        continue
    refs = {
        str(arg).split("ref=", 1)[1].split("&", 1)[0]
        for arg in argv
        if "ref=" in str(arg)
    }
    if not refs & candidate_refs:
        continue
    # A read the agent could not use is not the read it judged. The answer
    # record holds the status and the text, so both are required. A failed or
    # empty attempt is reported and the scan continues, so one unusable call
    # does not hide a later one that establishes the rule.
    answer = answers[index] or {}
    if answer.get("status") != 0:
        problems.append(f"candidate-bound proof read failed: {answer.get('status')}")
        continue
    served = str(answer.get("stdout", ""))
    if not served.strip():
        problems.append("candidate-bound proof read returned nothing")
        continue
    # An answer that shows the file's metadata, or only its declaration header,
    # is not a read of the proof. The assessed subject is the theorem together
    # with the body that discharges it, so the whole served text has to be in
    # the answer.
    if not read_complete_proof(served):
        problems.append(
            "candidate-bound proof read does not carry the assessed proof"
        )
        continue
    raise SystemExit(0)
for problem in problems:
    print(problem, file=sys.stderr)
print("no usable candidate-bound proof read before the transition", file=sys.stderr)
raise SystemExit(1)
PROBE_PROOF_READ
    then
      echo "abort: '$SCENARIO' cleared a proof it never read at the head it judged" >&2
      rc=1
    else
      echo "outcome: proof read at the candidate head, before 'pr ready'"
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
# A run is evidence for a rule only if the questions it was given were the ones
# the skill posts. The seeded question is a premise, not a recording: a fixture
# that seeds a request omitting the plan file's blob SHA or carrying an
# unfilled placeholder rehearses a request the skill would not send, and a run
# that reached a verdict on it decided a question nobody asked.
#
# Every scenario is held to this, not only the permitting three. A hold is
# evidence too, and a holding case whose two questions contradict each other
# holds on the contradiction instead of on the defect it exists to demonstrate:
# the six `combined-*` cases answered a proof question while their completeness
# request claimed no proof was affected, and each is a premise this refuses.
if ! python3 - "$ROOT/scenarios/$SCENARIO/facts.json" "$RUN/state.json" \
  "$SCENARIO" <<'PROBE_REQUESTS'
import json, re, sys

# The completeness template requires a plan revision carrying the plan file's
# blob SHA, and `Known limitations:` filled with an evidential limit rather
# than the template's own placeholder. The proof template requires the
# inventory, correspondence, assumptions, verifier evidence and non-vacuity
# sections. Only the completeness request states a revision here: a proof-only
# candidate has no ExecPlan, so asking it for one would demand a value that
# does not exist.
#
# Two of them are checked rather than one, because a scenario can be filed
# against a question the run asks instead of one it was handed. The seeded
# requests are the premise; the `posted` comments are what the run itself wrote
# while the rehearsal was going on. Checking only the premise leaves the
# posted-then-answered case with nothing to check at all — its whole point is
# that the initial thread holds no question — and the request a run composes is
# exactly where a missing field would go unnoticed, since the recording beside
# it is written from the same body.
if len(sys.argv) < 4:
    raise SystemExit("usage: PROBE_REQUESTS <facts.json> <run-state.json> <scenario>")
facts = json.load(open(sys.argv[1], encoding="utf-8"))
state_path, scenario = sys.argv[2], sys.argv[3]
seeded = [
    str(entry.get("body", ""))
    for entry in facts["api"][r"/issues/\d+/comments"]
    if "Assessment-ID:" in str(entry.get("body", ""))
    and "@coderabbitai" in str(entry.get("body", ""))
]
try:
    state = json.load(open(state_path, encoding="utf-8"))
except FileNotFoundError:
    state = {}
posted = [
    str(entry.get("body", ""))
    for entry in state.get("posted") or []
    if "Assessment-ID:" in str(entry.get("body", ""))
    and "@coderabbitai" in str(entry.get("body", ""))
]
# The two sets are checked separately as well as together. A run's own request
# is held to the same template as a seeded one, but the proofs question a run
# posts is answered by the stand-in rather than by the fixture's thread, so the
# contradiction rule below has to see both kinds together to fire.
bodies = seeded + posted
problems = []
completeness = [body for body in bodies if "please assess the implementation" in body]
proofs = [body for body in bodies if "are you satisfied that the introduced proof" in body]
# Whether the candidate touches the proof this fixture names. A request that
# says no proof is affected is checked against the candidate, not only against
# the sibling question: a run whose diff includes the proof file contradicts
# its own "none affected" whether or not anything asked a proof question.
changed = {
    str(entry.get("filename", ""))
    for entry in facts["api"][r"/pulls/\d+/files(?:[?#]|$)"]
    if isinstance(entry, dict)
}
changes_a_proof = str(facts.get("proof_path", "")) in changed
# A scenario that scripts an answer exists to be asked in the run itself, so it
# deliberately seeds no question: seeding one would answer a request the run
# never made and make the case a duplicate of the recorded ones. The exemption
# is tied to the script, not to the scenario name, so it cannot be borrowed to
# excuse an ordinary case that merely forgot its premise. Its request is not
# exempt from the field checks below: the posted body is checked when the run
# wrote one, and a scripted case that posted nothing has already failed the
# runner's posted-count check.
if not completeness and not proofs and not facts.get("scripted_replies"):
    problems.append("the permitting scenario seeds no assessment question")
if facts.get("scripted_replies") and not posted:
    # The script exists so a run asks; a run that asked nothing is not evidence
    # for the template, and its exemption would otherwise be an unexamined gap.
    # The message names the scenario so the refusal is actionable.
    problems.append(
        f"{scenario}: scripts an answer but the run posted no assessment question"
    )

# The blob a request cites is the plan file's blob *at the published head*,
# not the blob of the revision it names. The two coincide until an approval
# moves the revision under a head that does not move, which is exactly the
# premise of the two stale cases: the head was published under `rev-7` and
# already carried the `rev-8` text when `rev-8` was approved. A request there
# must cite the served blob beside the old approval. Citing the old revision's
# blob instead names a file this head never served, so the premise contradicts
# itself and a run holds on that rather than on the stale approval.
served_blobs = {
    str(payload.get("sha", ""))
    for pattern, payload in facts["api"].items()
    if isinstance(payload, dict)
    and re.search(pattern, f"/contents/{facts.get('plan_path', '')}")
}
# A run's own request cites a blob it read at the served head, so the same
# rule applies to it. Its citation is checked against the same served file
# rather than skipped for having been written during the run: a request the
# template would not accept is not made acceptable by who wrote it.
SERVED_BLOB = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")

def cited_blob(body):
    """Return the plan-file blob SHA a request cites, or `None`.

    The template asks for "the plan file's blob SHA at this head" and says
    nothing about how the request must word it. A run writes the citation in
    its own words — one recorded run posted `Plan revision: rev-7 (plan file
    blob 5a1c9e4d… at this head).` — so the value is read as the 40-hex SHA in
    the request's `Plan revision:` line rather than as one exact phrase. An
    earlier version matched `blob SHA at this head: <sha>` and refused that
    recorded request, which is a request the skill does post.
    """
    revision = re.search(r"Plan revision:[^\n]*", body)
    if not revision:
        return None
    found = SERVED_BLOB.search(revision.group(0))
    return found.group(0) if found else None

if len(served_blobs) == 1:
    served_blob = served_blobs.pop()
    for body in [*completeness, *proofs]:
        cited = cited_blob(body)
        if cited is not None and cited != served_blob:
            label = re.search(r"Assessment-ID:\s*([^\s.]+)", body)
            problems.append(
                f"{label.group(1) if label else '<unnamed>'} cites blob"
                f" {cited}, but this head serves {served_blob}"
            )

def leaves_placeholder(value):
    """Return whether a field's value is still the template's own placeholder.

    The template's placeholders are longer than their first clause:
    `Known limitations:` is followed by `<evidential limits only: checks not
    run, inspection not possible, proof bounds; not unimplemented plan
    milestones>.`, and `Assessed subject:` by `<the whole approved plan>.`. An
    earlier check tested for the shorter `<evidential limits only>`, which is
    not a substring of what the template actually prints, so a request carrying
    the unfilled template passed. Comparing the field's whole value against the
    angle-bracketed form catches the real placeholder and any other, without
    naming one exact wording that a template edit could drift from.

    The template writes a full stop after the closing bracket, so a trailing
    one is stripped before the closing bracket is looked for. A real value may
    also end in a sentence full stop, but it does not open with `<`, so the
    two are not confused.
    """
    text = value.strip()
    if text.endswith("."):
        text = text[:-1].rstrip()
    return text.startswith("<") and text.endswith(">")

for body in completeness:
    label = re.search(r"Assessment-ID:\s*([^\s.]+)", body)
    name = label.group(1) if label else "<unnamed>"
    revision = re.search(r"Plan revision:\s*(\S+)", body)
    if not revision:
        problems.append(f"{name} states no plan revision")
        continue
    if cited_blob(body) is None:
        problems.append(f"{name} states no plan file blob SHA")
    # The template says "Do not post unresolved placeholders", and the seeded
    # body is the premise a run is filed against. A field still holding its
    # placeholder is a request the skill would not send, so every text field
    # is checked for the angle-bracketed form rather than one of them for one
    # particular wording.
    for field_name, pattern in (
        ("limitations", r"Known limitations:\s*(.+)"),
        ("subject", r"Assessed subject:\s*(.+)"),
        ("acceptance", r"Acceptance evidence:\s*(.+)"),
    ):
        stated = re.search(pattern, body)
        if stated and leaves_placeholder(stated.group(1)):
            problems.append(f"{name} leaves the {field_name} placeholder unfilled")
    limitations = re.search(r"Known limitations:\s*(\S.*)", body)
    if not limitations:
        problems.append(f"{name} states no known limitations")
    if not re.search(r"Acceptance evidence:\s*\S", body):
        problems.append(f"{name} states no acceptance evidence")
    # "none affected" is a claim about the candidate, not a formality. A
    # completeness request that says no proof is affected, in a run that also
    # asks for a proof assessment and changes a proof file, states two things
    # the run cannot both believe. A reader has no way to tell which is right,
    # and the run then holds on the contradiction instead of on the rule.
    #
    # The inventory line is read when a request states one and not demanded of
    # every request. The shipped completeness template states no proof
    # inventory: it names the plan, the revision, the acceptance evidence and
    # the limitations, and a candidate that affects no proof records the
    # assessment as not applicable instead of writing "none affected" into a
    # completeness request. Requiring the line rejected a request the template
    # itself produces, which is exactly the request the posted-then-answered
    # run writes, and the recording beside it is that request.
    inventory = re.search(r"Proof inventory:\s*(.+)", body)
    if inventory and "none affected" in inventory.group(1) and (
        proofs or changes_a_proof
    ):
        problems.append(
            f"{name} says no proof is affected but the run asks for a proof"
            " assessment or changes a proof file"
        )

for body in proofs:
    label = re.search(r"Assessment-ID:\s*([^\s.]+)", body)
    name = label.group(1) if label else "<unnamed>"
    # The proof template names five fields, and a request that omits them asks
    # a narrower question than the skill asks: the verdict then covers a
    # subject whose correspondence, trusted boundaries and non-vacuity were
    # never put to it. The request states the limits it has rather than
    # claiming evidence the fixture never records, so each field is owed.
    #
    # A proof-only candidate states no revision, and the template's own
    # `<omitted; ...>` form is the correct answer there. Requiring the blob
    # for it would make the no-ExecPlan case impossible to record.
    for field in (
        "Proof inventory and claims",
        "Production correspondence",
        "Assumptions, trusted boundaries, domain, and bounds",
        "Verifier evidence",
        "Non-vacuity and limitations",
    ):
        stated = re.search(rf"{re.escape(field)}:\s*(\S.*)", body)
        if not stated:
            problems.append(f"{name} states no {field.lower()}")
            continue
        # The proof template's fields are placeholders too, and a seeded body
        # carrying one is a question nobody asked. Each is owed its own value
        # for the same reason the completeness request's fields are.
        if leaves_placeholder(stated.group(1)):
            problems.append(f"{name} leaves the {field.lower()} placeholder unfilled")
    revision = re.search(r"Plan revision:\s*(\S+)", body)
    if revision and not revision.group(1).startswith("<omitted"):
        if cited_blob(body) is None:
            problems.append(f"{name} states no plan file blob SHA")
for problem in problems:
    print(problem, file=sys.stderr)
if problems:
    raise SystemExit(1)
raise SystemExit(0)
PROBE_REQUESTS
then
  echo "abort: '$SCENARIO' seeds an assessment question the skill would not post" >&2
  rc=1
fi
ready_calls=$(grep -c '"pr", "ready"' "$TRACE" 2>/dev/null || true)
if [ "$EXPECT_READY" = yes ] && [ "$ready_calls" -eq 0 ]; then
  echo "abort: '$SCENARIO' should mark the PR ready, but no 'pr ready' was issued" >&2
  rc=1
fi
if [ "$EXPECT_READY" = no ] && [ "$ready_calls" -ne 0 ]; then
  echo "abort: '$SCENARIO' should stay in draft, but 'pr ready' was issued" >&2
  rc=1
fi
# A scenario that scripts an answer exists to show one run both asking and
# clearing. Its transition is only evidence if the run posted the question in
# that same run: a recorded answer already in the thread would leave the
# question unasked, and the case would then duplicate the permitting ones. The
# check is on the state the run wrote, not on the facts it started from.
SCRIPTED=$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("scripted_replies") or {}))' "$RUN/facts.json")
if [ "$SCRIPTED" != "0" ]; then
  posted_count=$(python3 -c 'import json,sys,os; p=sys.argv[1]; print(len((json.load(open(p)) if os.path.exists(p) else {}).get("posted") or []))' "$RUN/state.json")
  scripted_count=$(python3 -c 'import json,sys,os; p=sys.argv[1]; print(len((json.load(open(p)) if os.path.exists(p) else {}).get("scripted") or []))' "$RUN/state.json")
  echo "outcome: scripted-answer run posted=$posted_count answered=$scripted_count"
  if [ "$posted_count" -eq 0 ]; then
    echo "abort: '$SCENARIO' scripts an answer but the run posted no request" >&2
    rc=1
  fi
  if [ "$EXPECT_READY" = yes ] && [ "$scripted_count" -eq 0 ]; then
    echo "abort: '$SCENARIO' scripts an answer but none was served to the run" >&2
    rc=1
  fi
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
# A crossing run exists to rehearse the implementation handoff, so it is only
# evidence for that crossing if both halves happened: the sender was opened,
# the packet was produced, and the receiver was opened under the rules the
# decision then applies. The prompt asks, but an agent that ignored it would
# otherwise be recorded as a crossing run because it reached the right
# readiness decision — which is the decision a receiver-only run already makes.
# Those facts are read from the run's own event stream and final message, not
# from the trace: the handoff is an artefact of what the agent wrote, and no
# `gh` call can carry it. The trace is consulted only to establish that a
# `pr ready` call ran at all, so that a command a run merely mentions is not
# mistaken for the transition.
#
# The packet has to precede the decision it is supposed to inform. A run that
# prints the packet only after marking the PR ready is describing the handoff
# retrospectively; the receiver cannot have applied a packet that did not yet
# exist. The opening calls themselves are unordered against each other, since
# an agent may explore either skill first, but each is ordered against the
# decision.
#
# The packet's fields are read from the staged `sdlc-implementation`, so the
# check is that the run reproduced the shipped packet rather than a summary of
# its own. Its completeness line has to state the whole-plan subject, because
# that line is what the subset case turns on: a crossing that dropped it would
# leave the receiver holding a subset for a reason its own handoff no longer
# stated.
if [ "$START_SKILL" = sdlc-implementation ]; then
  if ! python3 - "$RUN/work/sdlc-implementation/SKILL.md" "$OUTCOME" "$EVENTS" \
    "$TRACE" "$RUN/handoff.txt" <<'PROBE_HANDOFF'
import json, re, sys

skill_path, outcome_path, events_path, trace_path, handoff_path = sys.argv[1:6]
skill = open(skill_path, encoding="utf-8").read()
try:
    outcome = open(outcome_path, encoding="utf-8").read()
except FileNotFoundError:
    print("the run produced no final message", file=sys.stderr)
    raise SystemExit(1)

# The event stream is read as a sequence of assistant messages, each with the
# text it spoke and the calls it made, together with the outcome of each call.
# The handoff is a message of its own — the one that hands delivery over — so
# its position and the transition's are compared as message positions, not as
# offsets in one final string.
#
# A call's outcome is what separates reading a manifest from trying to. The
# preserved `crossing-whole-plan` run contains a `cat pr-babysitting/SKILL.md`
# that failed with "No such file or directory", and the run opened the receiver
# successfully a moment later; crediting the failed attempt would let a run
# that never read the skill pass on an attempt that printed nothing. A call
# with no recorded result is not credited either: the evidence that it printed
# the file is the result, and an absent one establishes nothing.
messages = []
results = {}
for line in open(events_path, encoding="utf-8"):
    if not line.strip():
        continue
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    parts = [
        part
        for part in event.get("message", {}).get("content", [])
        if isinstance(part, dict)
    ]
    if event.get("type") == "user":
        for part in parts:
            if part.get("type") == "tool_result":
                results[str(part.get("tool_use_id", ""))] = not part.get("is_error")
        continue
    if event.get("type") != "assistant":
        continue
    messages.append(
        {
            "text": "\n".join(
                part.get("text", "") for part in parts if part.get("type") == "text"
            ),
            "calls": [
                {
                    "id": str(part.get("id", "")),
                    "name": part.get("name", ""),
                    "input": part.get("input", {}),
                }
                for part in parts
                if part.get("type") == "tool_use"
            ],
        }
    )


def succeeded(call):
    """Return whether this call's recorded result shows it ran successfully."""
    return results.get(call["id"], False)

# The shipped packet, as the sender states it: one `Label: rule` line per
# field, inside the section that hands delivery over. Reading the labels from
# the skill rather than hard-coding them here keeps this probe attached to the
# packet the candidate actually ships.
section = skill[skill.index("## 4. Hand PR delivery to pr-babysitting"):]
block = re.search(r"```text\n(?P<packet>.*?)\n```", section, re.DOTALL)
if not block:
    print("the shipped handoff no longer states a packet block", file=sys.stderr)
    raise SystemExit(1)
shipped = [
    line.split(":", 1)[0].strip()
    for line in block.group("packet").splitlines()
    if ":" in line and line.strip()
]
if not shipped:
    print("the shipped handoff packet states no fields", file=sys.stderr)
    raise SystemExit(1)

# Opening each skill is a call that reads it: a `Read` names the path, a Bash
# call runs a reader such as `cat` on it. A path that merely appears in a call
# is not an open — a note written to a ledger, a prompt quoted into a file, a
# `Glob` pattern that would match it — so the call's shape is checked rather
# than only its text. The reading words are the ordinary ones a supervisor
# uses on a skill file; a run that opens the manifest some other way is
# refused rather than silently credited.
#
# Each reader is recorded with how many leading operands it consumes as
# something *other* than a file. `grep -rn sdlc-implementation/SKILL.md notes/`
# names the manifest as the pattern to search for and reads `notes/`;
# `sed sdlc-implementation/SKILL.md/replace/ notes.txt` names it inside the
# script. Crediting those as opens would let a run that never read the skill
# pass the ordering check on a string it typed. `tr` reads no files at all, so
# it is absent: every one of its operands is a character set.
READER_COMMANDS = {
    "awk": 1,   # the program text
    "bat": 0,
    "cat": 0,
    "cut": 0,
    "grep": 1,  # the pattern
    "head": 0,
    "less": 0,
    "more": 0,
    "nl": 0,
    "od": 0,
    "sed": 1,   # the script, unless -e or -f supplies it
    "tail": 0,
}

def command_segments(payload):
    """Return this call's simple commands, in the order the shell runs them.

    A Bash command is split at its shell operators. One recorded run put a
    read behind a `cd` (`cd pr-babysitting; cat SKILL.md`), and the file is
    then named only by its basename, which is why the split is at the operator
    rather than at whitespace. A `Read` is one command of its own.

    Splitting is what makes a single call's order readable at all: a call that
    runs the transition and then reads a manifest contains both facts, and the
    call's index alone cannot say which came first.

    Parameters
    ----------
    payload : dict
        One call, with its tool name and input.

    Returns
    -------
    list
        One entry per simple command. An entry is the command's words, already
        stripped of quoting and redirection syntax.
    """
    if payload["name"] == "Read":
        return [[str(payload["input"].get("file_path", ""))]]
    if payload["name"] != "Bash":
        return []
    return [
        [word.strip("\"'`()<>") for word in segment.split()]
        for segment in re.split(r"[;&|\n]+", str(payload["input"].get("command", "")))
        if segment.split()
    ]


#: The options that supply `sed`'s script instead of its first operand, so the
#: first operand is a file after all. A joined form such as `-es/x/y/` or
#: `-fscript.sed` carries the script in the same word.
SED_SCRIPT_OPTIONS = {"-e", "-f", "--expression", "--file"}


def supplies_sed_script(words):
    """Return whether a `sed` command was given its script as an option."""
    return any(
        word in SED_SCRIPT_OPTIONS
        or word.startswith(("--expression=", "--file="))
        or (len(word) > 2 and word.startswith(("-e", "-f")))
        for word in words
    )


def read_files(payload, words):
    """Return the files this simple command reads.

    Only a reader's own file operands count. A call is also a piece of prose —
    a heredoc writing notes, a variable assigned a path, a `gh api` URL naming
    `contents/docs/execplans/SKILL.md` — and none of those opened anything,
    whatever words appear in them, which is why the command's first word has
    to be a reader at all. A `Read` call is the tool reading one file, and
    `command_segments` gives it that file as its only word.

    A reader's operands are read the way that reader reads them. Options begin
    with `-` and are not files, and the leading operands recorded in
    `READER_COMMANDS` are the pattern, program or script the reader consumes
    before it reaches a file. Without that, `grep -rn
    sdlc-implementation/SKILL.md notes/` would count as opening the manifest
    when it only searched for that string.

    Parameters
    ----------
    payload : dict
        One call, with its tool name and input.
    words : list of str
        One of this call's simple commands.

    Returns
    -------
    list of str
        The files the command names, or an empty list when it reads none.
    """
    if payload["name"] == "Read":
        return words
    if not words or words[0] not in READER_COMMANDS:
        return []
    leading = READER_COMMANDS[words[0]]
    if words[0] == "sed" and supplies_sed_script(words[1:]):
        leading = 0
    operands = [word for word in words[1:] if not word.startswith("-")]
    return operands[leading:]


def first_opened(skill):
    """Return the position of the first command that read `skill`'s manifest.

    A mention of the skill is not a read of it: a follow-up note, a prompt
    quotation, or a pre-written ledger can name the path without opening it,
    and treating any of those as the open would let a run that never read the
    skill pass an ordering check. The file must have been opened and the
    skill's own name must appear in the call, so a read of some other
    `SKILL.md` cannot stand in for this one.

    The call must also have succeeded. An attempt that failed printed no
    manifest, and the preserved `crossing-whole-plan` recording holds exactly
    that: a `cat pr-babysitting/SKILL.md` that exited 1 because the path was
    wrong, followed by a successful open of the same file. Crediting the first
    would report the receiver as opened before the decision even where it was
    opened only after.

    The position is `(message, call, command)`. A message may carry several
    calls and a call several commands, and comparing only the message would
    make everything in one turn simultaneous: a single
    `gh pr ready 272; cat <skills>` would then count as reading the rules
    before applying them. Pairing each read with the command it belongs to
    makes "before" mean before the command that read the file.

    Returns
    -------
    tuple or None
        `(message, call, command)` of the first successful read, or None if
        the run never read the manifest.
    """
    for index, message in enumerate(messages):
        for call_index, payload in enumerate(message["calls"]):
            if not succeeded(payload):
                continue
            # The skill's own name has to appear somewhere in the call, so a
            # read of a different `SKILL.md` cannot stand in for this one. A
            # recorded run opened the receiver as `cd pr-babysitting; cat
            # SKILL.md`, where the name is in the `cd` and the file is read by
            # its basename; requiring the name on the reader's own command line
            # would refuse the one form a run actually used.
            if skill not in json.dumps(payload["input"]):
                continue
            for command_index, words in enumerate(command_segments(payload)):
                if any(
                    word.rstrip("/").rsplit("/", 1)[-1] == "SKILL.md"
                    for word in read_files(payload, words)
                ):
                    return index, call_index, command_index
    return None

# The transition is what the handoff is for, so the decision is the call that
# ran `gh pr ready`, not the first call whose text mentions it. A ledger entry
# may quote the command it declined to run ("Decision: do not run gh pr
# ready; PR stays draft"), and no text search can tell that record from the
# invocation. The stand-in's trace is the record of what ran, so a mention is
# a decision only when the trace recorded a `pr ready` invocation at all, and
# the call that carries it is the Bash call in which `gh pr ready` appears as
# adjacent words on a command line.
def recorded_ready_calls():
    """Return the `pr ready` argument vectors the stand-in's trace recorded."""
    try:
        trace = open(trace_path, encoding="utf-8")
    except FileNotFoundError:
        return []
    recorded = []
    for line in trace:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        argv = entry.get("argv") if isinstance(entry, dict) else entry
        if isinstance(argv, list) and [str(p) for p in argv[:2]] == ["pr", "ready"]:
            recorded.append([str(part) for part in argv])
    return recorded

def ready_position():
    """Return the position of the first command that ran a recorded `gh pr ready`.

    The trace decides whether a transition happened; the event stream decides
    where in the run it was issued. Both are needed: the trace alone cannot
    say that the call came after the skills were read and after the packet was
    printed, and the text alone cannot say that the command ran rather than
    being described. Only a Bash argument list is searched, because a tool
    call's JSON also carries the tool's name and description: a `Read` of a
    path containing `pr ready` is not a transition.

    The position is `(message, call, command)`, the same shape the opens are
    reported in, so the two are ordered against each other rather than against
    the turn they happened to share. A call must also have succeeded, on the
    same ground the opens are: a `pr ready` the service refused did not
    transition the PR, and it cannot be the decision a packet informs.

    Returns
    -------
    tuple or None
        `(message, call, command)` of the first recorded transition, or None
        when the run issued none.
    """
    if not recorded_ready_calls():
        return None
    for index, message in enumerate(messages):
        for call_index, payload in enumerate(message["calls"]):
            if payload["name"] != "Bash" or not succeeded(payload):
                continue
            for command_index, words in enumerate(command_segments(payload)):
                if any(
                    words[position] == "pr" and words[position + 1] == "ready"
                    for position in range(len(words) - 1)
                ):
                    return index, call_index, command_index
    return None

# The packet is a titled block in a message. Titles and fields may be
# decorated as Markdown — bulleted, bolded, fenced — so each line is
# normalized before it is compared: only the words and values matter, and
# failing a run over emphasis would say nothing about the handoff.
def normalize(text):
    """Return a line without its Markdown decoration."""
    text = re.sub(r"^[-*+]\s+", "", text.strip())
    text = re.sub(r"^\d+[.)]\s+", "", text)
    return text.strip("`*_ ")

def field_of(line):
    """Return `(label, value)` for a field line, or `(None, '')`."""
    label, sep, value = normalize(line).partition(":")
    if not sep or not value.strip():
        return None, ""
    return re.sub(r"\s+", " ", label).strip().casefold(), value.strip()

def packet_message():
    """Return `(index, text)` for the first message that prints the packet."""
    for index, message in enumerate(messages):
        for line in message["text"].splitlines():
            if re.sub(r"[^A-Z ]", "", line.upper()).strip() == "HANDOFF PACKET":
                return index, message["text"]
    return None, ""

def stated_fields(text):
    """Return `(fields, last_field_line)` the packet message states.

    The fields are read from the heading to the end of the message. Scanning
    for the shipped labels rather than stopping at the first line that is not
    one keeps a wrapped value from truncating the block and failing a run over
    line width instead of over the handoff. The labels are held to their
    shipped order, so the fields are still one block rather than a sentence
    repeated out of place.
    """
    lines = text.splitlines()
    heading = next(
        index
        for index, line in enumerate(lines)
        if re.sub(r"[^A-Z ]", "", line.upper()).strip() == "HANDOFF PACKET"
    )
    expected = [
        (re.sub(r"\s+", " ", label).strip().casefold(), label) for label in shipped
    ]
    stated = {}
    last_field = None
    index = 0
    for offset, line in enumerate(lines[heading + 1:]):
        label, value = field_of(line)
        if label is not None and index < len(expected) and label == expected[index][0]:
            stated[label] = value
            last_field = heading + 1 + offset
            index += 1
    return expected, stated, last_field, index

sender = first_opened("sdlc-implementation")
receiver = first_opened("pr-babysitting")
decision = ready_position()
packet_at, packet_text = packet_message()
problems = []
if sender is None:
    problems.append("the run never opened sdlc-implementation/SKILL.md")
if receiver is None:
    problems.append("the run never opened pr-babysitting/SKILL.md")
# The lifecycle order this checks is the one the skills state: the handoff is
# produced before delivery is carried, and the readiness rules are read before
# a readiness transition is taken. An exploration call may mention either skill
# first without that meaning anything was carried, so the two opens are not
# ordered against each other; each is ordered against the decision it is
# supposed to inform.
#
# The comparison is between command positions, not message positions, so a
# single call that ran the transition and then read the manifest is refused:
# `gh pr ready 272; cat sdlc-implementation/SKILL.md` is one message, one call
# and two commands, and the readiness rules were read after they were applied.
if sender is not None and decision is not None and sender > decision:
    problems.append(
        "the run decided before opening sdlc-implementation, so the packet"
        " cannot have informed the transition"
    )
if receiver is not None and decision is not None and receiver > decision:
    problems.append(
        "the run decided before opening pr-babysitting, so the readiness"
        " rules cannot have informed the transition"
    )
if decision is None and recorded_ready_calls():
    problems.append(
        "the stand-in recorded a 'pr ready' call that no successful tool call"
        " in the event stream ran"
    )
if packet_at is None:
    problems.append("the run printed no 'HANDOFF PACKET' block")
else:
    open(handoff_path, "w", encoding="utf-8").write(packet_text + "\n")
    expected, stated, last_field, index = stated_fields(packet_text)
    missing = [original for key, original in expected if key not in stated]
    if missing:
        problems.append(f"the handoff packet omits the shipped field(s) {missing!r}")
    elif index != len(expected):
        problems.append("the handoff packet repeats or reorders its shipped fields")
    completeness = next(
        (
            value
            for label, value in stated.items()
            if label.startswith("execplan completeness/correctness assessment")
        ),
        "",
    )
    if "whole approved plan" not in completeness.casefold():
        problems.append(
            "the handoff packet's completeness line no longer states the"
            " whole approved plan, which is the subject the subset case turns on"
        )
    # The packet is the handoff, so the decision it informs has to follow it.
    # A message that prints the packet after the transition is describing the
    # handoff retrospectively, and the receiver cannot have applied it.
    if decision is not None and packet_at > decision[0]:
        problems.append(
            "the run printed the handoff packet after the decision it is"
            " supposed to inform"
        )
    # The packet is not the answer. Something has to follow it, or the run
    # stopped at the handoff and never carried it. A run that decides nothing
    # may legitimately end on the packet: a blocked handoff is the packet plus
    # the reason delivery stops, and the subset run records exactly that. So
    # this is only required where a decision was taken, which is also where
    # the ordering check above has something to order.
    if decision is not None and not outcome.strip():
        problems.append("the final message is empty, so no decision follows the packet")

for problem in problems:
    print(problem, file=sys.stderr)
if problems:
    raise SystemExit(1)
print(f"outcome: handoff produced with {len(shipped)} shipped fields and carried before the decision")
raise SystemExit(0)
PROBE_HANDOFF
  then
    echo "abort: '$SCENARIO' did not produce and carry the implementation handoff" >&2
    rc=1
  fi
fi

# Propagate the agent's own status. A rehearsal that was killed by its budget,
# timed out, or aborted on an isolation check is not a successful run, and an
# automation reading this script's status must not mistake it for one.
if [ "$rc" -ne 0 ]; then
  echo "sandboxed_run.sh: run failed with status $rc; see above" >&2
  exit "$rc"
fi
exit 0
