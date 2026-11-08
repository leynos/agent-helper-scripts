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
| `proof-only-pending`  | `dddd4444` | no ExecPlan, so not applicable                                               | question posted, unanswered           | no            |
| `proof-only-cleared`  | `eeee5555` | no ExecPlan, so not applicable                                               | **clear**, subject `refinement_sound` | yes           |

`subset-only` and `subset-clear` differ only in the verdict; both stay in
draft. That pair isolates the subject check from the verdict, which a single
`not clear` subset case cannot do. `superseded-revision` isolates the revision
check: the verdict is clear and the whole plan, and only the revision is stale.

## Layout

- `scenarios/<name>/facts.json` — the recorded GitHub surface for that run.
- `traces/<name>.jsonl` — every `gh` argv the agent issued, one JSON array per
  line, in order, written before the stand-in answered.
- `outcomes/<name>.txt` — the agent's final message for that run, verbatim.
  These are `.txt`, not `.md`, so the repository's Markdown gates cannot reflow
  a verbatim recording.
- `gh-shim.py` — the executable stand-in. It derives the run directory from its
  own `__file__`, records each argv, and answers from `facts.json`. `pr ready`
  writes `state.json` with `isDraft: false`, so a later `pr view` can show the
  transition.
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
- The credential surfaces are emptied rather than only being unset:
  `~/.config/gh`, the `~/.local/share/github-tokens` pool and the agent's own
  `~/.claude/.credentials.json` are replace-bound with an empty directory or an
  empty file, so a client that escaped the mask finds no token and an agent
  that reads the lifecycle credential file finds it empty.
- Masking fails closed. A missing target, a shape mismatch (the token pool is
  one file, the client configuration a directory), a failed bind, or a mask
  that does not read back aborts the run before the agent starts.
- The credential masks are re-proved after they are applied: `hosts.yml` must
  be absent, and the token pool and credential file must be empty. A directory
  mask removes the paths beneath it, while a file mask leaves the path present
  but empty, so each shape is checked for what it should show.

**Process.** The environment is replaced rather than filtered: `env -i` passes
only `PATH`, `HOME`, an empty `GH_TOKEN`, `GITHUB_TOKEN` and `GH_CONFIG_DIR`,
the two model API variables, `GIT_TERMINAL_PROMPT`, `TMPDIR` and `TERM`. No
ambient token, config override or path reaches the agent. It runs `--bare`, so
operator instructions, hooks, MCP servers and memory are absent, with
`--permission-mode dontAsk` and `--allowedTools Bash,Read,Glob,Grep`. The
runner propagates the agent's own exit status, so a run killed by its budget or
by a timeout is a failure rather than a clean rehearsal.

These layers are proved, not assumed. A diagnostic stand-in for the CLI once
recorded the agent's view from inside the sandbox: the credential file, token
pool and `hosts.yml` were empty or absent, `GH_TOKEN` and `GITHUB_TOKEN` were
unset, `/usr/bin/gh` and `/bin/gh` both held the stand-in, and `github.com`,
`api.github.com`, `140.82.121.4:22` and `1.1.1.1:443` were all blocked while
the model API was reachable. An earlier revision of this runner defined its
masking helper without calling it, so those surfaces were reachable; the proof
checks above exist so that the same omission fails the run instead of silently
weakening it.

The limits are deliberate. The model API stays reachable, because the agent
needs it. The home directory is still readable, so the agent can read this
repository's files; the masking covers credentials, the live GitHub client and
the network, not the filesystem. And the boundary is stronger against reaching
GitHub than against a locally privileged process: the harness assumes a
cooperative agent, not an adversarial one.

## Recorded artefacts contain no live mutations

The traces show reads and, in the two permitting scenarios, `pr ready` against
the stand-in. No trace contains a POST, a merge, a review request or a comment.
Nothing here was captured from a live PR, and no credential appears in any file.

## Refreshing

Regenerate with `python3 -I make_scenarios.py` after editing a scenario, then
rerun the affected scenarios. Replace a trace and its outcome together: a trace
without the matching outcome, or the reverse, is not evidence of anything.
Review a new recording before replacing an old one, and keep the previous
recording's scope if it covered different evidence.
