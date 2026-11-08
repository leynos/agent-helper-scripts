# Agent-boundary rehearsal for `pr-babysitting` readiness

These are recordings from a headless agent run against the shipped
`pr-babysitting` skill. They show that an agent reading that skill gates the
draft-to-ready transition on the shape of the ExecPlan assessment evidence, and
they are reproducible from the files here.

They are **rehearsals against a controlled GitHub surface, not live GitHub
runs**. They exercise the shipped text, not the GitHub API, not a live
CodeRabbit reply, and not the real CodeRabbit service. Record the executable
checks actually run in a PR's validation evidence; do not cite these files as
proof of a live scenario.

## What each scenario pins

Every scenario serves the same green checks and the same base; the only
variable is the assessment evidence. `base` is
`73d32981c7b7e8f52590a074873e28a9f369f0f9` throughout, and the PR starts as a
draft in each case.

| Scenario              | Head       | Completeness evidence                                                        | Proof evidence                        | `gh pr ready` |
| --------------------- | ---------- | ---------------------------------------------------------------------------- | ------------------------------------- | ------------- |
| `subset-only`         | `aaaa1111` | **not clear**; subject is the declared subset (EP-M1, EP-M2)                 | none                                  | no            |
| `subset-clear`        | `ffff6666` | **clear**; subject is still the declared subset                              | none                                  | no            |
| `superseded-revision` | `bbbb2222` | **clear** whole plan, but recorded against `rev-6` while `rev-7` is in force | none                                  | no            |
| `current-whole-plan`  | `cccc3333` | **clear** whole plan, `rev-7`                                                | none affected                         | yes           |
| `codescene-advisory`  | `9999aaaa` | **clear** whole plan, `rev-7`; every check green                             | none affected                         | no            |
| `proof-only-pending`  | `dddd4444` | no ExecPlan, so not applicable                                               | question posted, unanswered           | no            |
| `proof-only-cleared`  | `eeee5555` | no ExecPlan, so not applicable                                               | **clear**, subject `refinement_sound` | yes           |

`codescene-advisory` isolates the CodeScene gate from every other reason to
hold: the whole approved plan has cleared at the revision in force, and all
three checks conclude `SUCCESS`. Its CodeScene check is nevertheless titled
"Issues found" and its output lists one advisory — a complexity finding against
a file the PR changes, so the finding is about this candidate. The run stays in
draft, which is the skill's rule that "a passing check with advisory findings
still has outstanding issues". That pairing is what distinguishes a gate bound
to CodeScene's output from one reading the green badge: if the agent had
treated the passing conclusion as clearance, this scenario would have marked
the PR ready. The run cannot clear the finding either — the sandbox has no
checkout and no `cs` — so it also shows the gate blocking rather than silently
waiving an issue it could not fix.

`subset-only` and `subset-clear` differ only in the verdict; both stay in
draft. That pair isolates the subject check from the verdict, which a single
`not clear` subset case cannot do: `subset-clear` is a clear verdict on the
current revision whose only defect is the subject, and it stays in draft anyway.
`subset-clear` was re-recorded under the completed stand-in, so its outcome
reads the hosted CodeScene check output, the PR's diff and its file list rather
than reporting them missing. `superseded-revision` isolates the revision check:
the verdict is clear and the whole plan, and only the revision is stale. It is
also the one scenario that exercises the manual-comment route: the agent posts
a follow-up asking for a `rev-7` verdict, reads it back, and waits for an
answer that the facts never supply. The scenario therefore shows both halves of
the stale-revision rule — the follow-up path works, and readiness still waits.

## Layout

- `scenarios/<name>/facts.json` — the recorded GitHub surface for that run.
- `traces/<name>.jsonl` — every `gh` argv the agent issued, one JSON array per
  line, in order, written before the stand-in answered.
- `outcomes/<name>.txt` — the agent's final message for that run, verbatim.
  These are `.txt`, not `.md`, so the repository's Markdown gates cannot reflow
  a verbatim recording.
- `submitted/<name>.txt` — the comment body that run posted, verbatim. A trace
  shows that a POST happened; this shows what it asked for. Like the outcomes
  it is `.txt`, so the Markdown gates cannot reflow a verbatim recording, and
  it is committed only from a run whose authorization proof passed.
- `gh-shim.py` — the executable stand-in. It derives the run directory from its
  own `__file__`, records each argv, and answers from `facts.json`. `pr ready`
  records `isDraft: false` in `state.json`, merging rather than replacing, so a
  later `pr view` can show the transition and a posted comment recorded earlier
  survives it. A POST to the issue-comment route is accepted only with the
  fixture token: without it the stand-in answers `401 Bad credentials`, because
  accepting the request would record a success the real service would refuse.
  An accepted POST returns the fixture comment's URL, records the submitted
  body — in both the `-f body=…` and `--input -` forms — and serves it back on
  its own route, so a read-back and the discussion listing both see what was
  posted rather than a placeholder. A single-comment route serves any comment
  the recorded listing carries, so a read-back finds a comment the run itself
  did not post. The `contents` route serves the plan file with its blob SHA,
  which is what lets a follow-up name the plan revision instead of stopping for
  a value the fixture never supplied. The `pulls/N`, `pulls/N/files`,
  `pulls/N/commits`, `pr list`, `pr diff` and `graphql` review-thread routes
  answer the reads a readiness run makes when it checks whether the delivered
  work matches the plan; without them a run reported those reads as 404 and
  could not see the diff at all. The check's own `annotations` route serves the
  entries its `annotations_count` advertises, and the `contents` route serves
  the file a finding names, so a run investigating an advisory reads the code
  rather than being told it is missing. `gh repo clone` is refused as
  unreachable — `Could not resolve host: github.com` — because that is what the
  dropped network really does; reporting it as an unsupported command would
  misdescribe the environment. The `check-runs` route carries the hosted check
  output, including CodeScene's own "no advisory findings" summary, which is
  one of the two CodeScene sources the skill reads; the recordings show only
  that half, for the reason under
  [what these recordings do not show](#what-these-recordings-do-not-show).
- `make_scenarios.py` — regenerates every `facts.json`.
- `sandboxed_run.sh` — the runner, including the isolation described below.

## Reproducing a run

`sandboxed_run.sh` takes a scenario name and needs `SKILL_SRC` set to the
`skills` directory of the candidate under test. It copies
`$SKILL_SRC/pr-babysitting` into a scratch working directory and runs a
headless agent there, so the prompt's `pr-babysitting/SKILL.md` resolves. Every
completeness request in `scenarios/` names the head it was posted for, and no
scenario carries a review decision the assessment is meant to be judged on.

```bash
SKILL_SRC=/path/to/checkout/skills \
  bash tests/fixtures/readiness-agent-boundary/sandboxed_run.sh current-whole-plan
```

The runner is not part of any Makefile gate: it needs a model API credential
and a `claude` CLI, which CI does not provide. It is a rehearsal tool, not a
deterministic check. It finds `claude` on the caller's PATH, or takes
`CLAUDE_BIN` naming the directory that holds it; the sandbox PATH is otherwise
fixed to the stand-in, that directory, `/usr/bin` and `/bin`, so the agent
inherits nothing else from the operator. It also needs `pasta`, `nft` and
`unshare`, and refuses to run without them, because the egress allowlist is the
boundary that stops a second HTTP client.

## Isolation

An earlier unmasked run proved that clearing ambient credentials alone is not a
boundary: the agent used the real client and posted a synthetic comment to the
live PR. Every recording here comes from a masked run in three layers.

**Network.** `pasta` gives the run a private network namespace and forwards the
host interface into it. The first thing the run does there is install an
`nftables` output policy of `drop`, admitting loopback, DNS to this host's own
resolvers, one TCP port to the model API host, and established flows. The
resolvers are read from `/etc/resolv.conf` on the host, and the model address
from `ANTHROPIC_BASE_URL`, both before the namespace drops the network; the run
aborts if either is empty. DNS is narrowed to those resolvers because admitting
port 53 generally would leave an arbitrary destination reachable.

After installing the rules, the run proves the boundary in both directions
before the agent starts, because a blocked-only check can pass on a broken
network and an allowed-only check can pass with no filter at all:

- at least one model API address must accept a connection on port 443;
- `1.1.1.1:443` and `140.82.121.4:443` must both fail, addressed literally so a
  DNS failure cannot be mistaken for a block.

The run aborts on either failure. This is the load-bearing boundary, because
the agent runs with Bash and a filesystem mask alone cannot stop a second HTTP
client. Verified against the live network: inside the sandbox `github.com`,
`api.github.com` and port 22 are all unreachable, while the model API and DNS
work.

**Mounts.** Inside the network namespace, `unshare -m` adds a private mount
namespace, made private with `mount --make-rprivate /` first:

- The stand-in is replace-bound over `/usr/bin/gh` and `/bin/gh`, so no
  absolute path reaches the real client.
- `comenq` is replaced by a stub that exits 127 when present.
- The client configuration and the agent's own credential file are emptied
  rather than only being unset: `~/.config/gh` and
  `~/.claude/.credentials.json` are replace-bound with an empty directory or an
  empty file, so a client that escaped the mask finds no token and an agent
  that reads the lifecycle credential file finds it empty.
- The comment-token pool is replaced rather than emptied. The runner binds a
  fixture pool holding one token, `fixture-pool-token`, over
  `~/.local/share/github-tokens`. The stand-in alone honours that token, which
  authenticates as `fixture-commenter`; real GitHub would reject it, so nothing
  is lost if it escapes. This keeps the manual-comment route exercisable inside
  the sandbox while the host's real pool stays unreachable.
- Masking fails closed. A missing target, a shape mismatch (the token pool is
  one file, the client configuration a directory), a failed bind, or a mask
  that does not read back aborts the run before the agent starts.
- The masks are re-proved after they are applied: `hosts.yml` must be absent,
  the credential file must be empty, and the token pool must hold exactly one
  line reading `fixture-pool-token`. A directory mask removes the paths beneath
  it, while a file mask leaves the path present but empty, so each shape is
  checked for what it should show; a real token in the pool would change the
  line count or the content and fail the check.

**Process.** The environment is replaced rather than filtered: `env -i` passes
only `PATH`, `HOME`, an empty `GH_TOKEN`, `GITHUB_TOKEN` and `GH_CONFIG_DIR`,
the two model API variables, `GIT_TERMINAL_PROMPT`, `TMPDIR` and `TERM`. No
ambient token, config override or path reaches the agent. `HOME` is the run's
own directory, not the operator's, so nothing under the host home is reachable
by a relative path; the absolute credential paths above stay masked, so neither
route reaches a real token. A `.claude` directory is created there so the CLI
has somewhere to write, and the run aborts if the isolated home resolves to the
host home or has no such directory. It runs `--bare`, so operator instructions,
hooks, MCP servers and memory are absent, with `--permission-mode dontAsk` and
`--allowedTools Bash,Read,Glob,Grep`. The runner propagates the agent's own
exit status, so a run killed by its budget or by a timeout is a failure rather
than a clean rehearsal.

These layers are proved, not assumed. A diagnostic stand-in for the CLI once
recorded the agent's view from inside the sandbox: the credential file, token
pool and `hosts.yml` were empty or absent, `GH_TOKEN` and `GITHUB_TOKEN` were
unset, `/usr/bin/gh` and `/bin/gh` both held the stand-in, and `github.com`,
`api.github.com`, `140.82.121.4:22` and `1.1.1.1:443` were all blocked while
the model API was reachable. An earlier revision of this runner defined its
masking helper without calling it, so those surfaces were reachable; the proof
checks above exist so that the same omission fails the run instead of silently
weakening it.

The runner also asserts the outcome each scenario exists to pin, because a
trace shows what the agent read and only the decision shows what it concluded.
A scenario expected to transition must issue `gh pr ready` and read the draft
state back; a scenario expected to stay in draft must issue none. A scenario
that decides otherwise fails the run instead of being filed as a recording, so
these files cannot drift from the rule they are meant to demonstrate.

The stand-in's own authorization is proved the same way. Before the agent
starts, the runner posts a comment twice against a copy of the stand-in: with
no token, which must fail, and with the fixture token, which must succeed. An
earlier revision stamped the pool's login on every POST regardless of what the
token was, so a recording could show a follow-up that the real service would
have refused. After the run, the runner also prints the body that was posted
and fails if its author is not the pool account, so the trace's evidence is the
request itself and not only the fact that one was made.

The limits are deliberate. The model API stays reachable, because the agent
needs it. The home directory is still readable, so the agent can read this
repository's files; the masking covers credentials, the live GitHub client and
the network, not the filesystem. And the boundary is stronger against reaching
GitHub than against a locally privileged process: the harness assumes a
cooperative agent, not an adversarial one.

## What these recordings do not show

Each recording is evidence for what its trace and outcome contain, and no more.
Two limits apply to every run here.

**Revision confirmation.** `current-whole-plan` marks the PR ready only after
reading the plan file at the head it is judging, and the trace shows that read:
`contents/docs/execplans/issue-271-readiness-handoff.md?ref=cccc3333` returns a
file whose body says `Plan revision: rev-7`, which is the revision the verdict
echoes. The recording therefore shows the echo reconciled against the revision
in force, not accepted on its own. Its content is served as plain text rather
than in the API's base64 envelope, so a run that decoded `content` itself would
see a different shape; the fixture chooses the readable one so a reviewed file
carries the plan text. `proof-only-cleared` needs no revision read: its request
states that no ExecPlan applies, so there is no revision to confirm and the
proof verdict is the only applicable assessment. `superseded-revision` reads
`contents/docs/execplans` while naming the stale revision in a follow-up, which
is a different use of the route from the confirmation above.

**CodeScene.** The sandbox has no checkout of the PR's code and no `cs` CLI, so
no run executes `cs delta`. The hosted `check-runs` output is the only
CodeScene source any recording reads, and the skill treats a local delta, the
`codescene-access[bot]` comments and that output as separate outstanding-issue
sources. A green hosted check therefore does not by itself clear the CodeScene
gate, and these recordings do not show the local half being cleared.

This is a bound of the harness, not a state a recording could be made to show
under it: admitting a checkout and a `cs` binary would mean admitting network
egress to the CodeScene service and a host tool outside the fixed sandbox
`PATH`, and a stand-in that fabricated a delta result would record an answer no
service produced. The positive recordings are still valid as rehearsals of the
assessment gate, which is what they were recorded for, and the outcome text of
each states which CodeScene sources it did read. A run under the real skill in
a real worktree is the only place the local half can be recorded, and that is a
live run, not one of these files.

What the recordings do establish is that the gate binds to CodeScene rather
than to the badge. `codescene-advisory` gives the agent an unqualified clear
assessment, three `SUCCESS` checks, and a CodeScene output that lists an
outstanding finding against a changed file: the run stays in draft and names
that finding as its deciding evidence. The gate is therefore responsive to the
hosted result, and a run that cannot obtain the local half blocks rather than
waiving what it could not check. What remains unshown is the other half — a
clean local `cs delta` being required and obtained before a transition.

**Freshness of each recording.** `current-whole-plan` and `subset-clear` were
recorded under the stand-in as it now behaves. The other four were recorded
earlier, while `gh-shim.py` ignored `--jq`, so a filtered call returned the
unfiltered payload: a status filter yielded the whole status object, and
`--jq length` on an empty listing yielded `[]` rather than `0`. The stand-in
now applies the filter on every JSON route, refuses one on a human-readable
route instead of returning the text, derives the HTTP method as `gh api` does —
including the `--flag=value` spellings — and resolves that method before any
read route. All six traces replay against it with no unanswered call, so every
command those four runs issued still has an answer, but replaying recorded argv
is not the same as re-running the agent: it shows the surface is complete, not
that the agent would decide the same way under it. Replace those four
recordings with fresh runs before treating them as evidence about the current
stand-in.

## Recorded artefacts contain no live mutations

The traces show reads, `pr ready` in the two permitting scenarios, and one POST
in `superseded-revision`, all against the stand-in. No trace contains a merge
or a review request. Nothing here was captured from a live PR, and no
credential appears in any file: the only token any run could reach is the
fixture token, which real GitHub rejects. The one posted body names the plan
revision and the base/head it was posted for, and carries no credential.

## Refreshing

Regenerate with `python3 -I make_scenarios.py` after editing a scenario, then
rerun the affected scenarios into `RUN_DIR` and copy `gh-trace.jsonl` to
`traces/`, `submitted.md` to `submitted/` and the agent's own final message to
`outcomes/`. A scenario that posted no comment has no `submitted/` entry.
Replace a trace, its outcome and its submitted body together: any one without
the others, or the reverse, is not evidence of anything. Review a new recording
before replacing an old one, and keep the previous recording's scope if it
covered different evidence.
