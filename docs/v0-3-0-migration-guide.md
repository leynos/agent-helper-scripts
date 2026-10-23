# v0.3.0 Migration Guide (Unreleased)

This guide records migrations that change how the helper scripts and skills in
this repository behave, and what to do about work produced under the previous
behaviour. It documents changes staged for the next release and is not yet
published as a tagged version.

## ExecPlan implementation and PR delivery

The `sdlc-implementation` skill now implements an approved ExecPlan and hands
the candidate, delivery ledger, acceptance and validation evidence, pending
work, and mutation authority to `pr-babysitting`. Invoke the implementation
skill for the plan, then hand off to PR babysitting even when CI is red or the
PR is still a draft. `pr-babysitting` is the single owner of hosted CI, review
convergence, readiness, rebase, authorized merge, and post-merge integration.

Refresh the skills with `install-skills` before using the workflow. The managed
helper checkout now retains `agents/` alongside `skills/`, so workflow skills
can read `agents/subagents.yml`; agent definitions are not copied into user
skill directories. Existing skills-only sparse checkouts are updated by the
installer.

For implementation PRs, applicable hosted completeness/correctness and
proof-specific assessments must clear before a draft is marked ready. An
already-ready PR stays ready when evidence is missing or invalidated, while
merge remains blocked until the applicable assessment clears. See the
[users' guide](users-guide.md#execplan-implementation) and the
[`sdlc-implementation`](../skills/sdlc-implementation/SKILL.md) and
[`pr-babysitting`](../skills/pr-babysitting/SKILL.md) skills for invocation,
assessment, and delivery details.

## PR babysitting end states, review signals, and comment helper

`pr-babysitting` now defines when an assignment ends, reads CodeRabbit and
CodeScene from the signals they actually publish, and ships its comment helper
as a script. Refresh the skills with `install-skills` to pick up the changes.

- **End states.** Previously the skill ended at a merge or a blocked handoff,
  and bounded waits often ended an assignment early. It now keeps working until
  the PR reaches equilibrium, an authorized merge, or an intractable impasse,
  unless the assignment sets an earlier stopping point or deadline. Extra
  per-task instructions to "not end the turn" are no longer needed.
- **CodeRabbit.** Previously the skill watched for a CodeRabbit check run. It
  now reads the `CodeRabbit` commit status description and the summary issue
  comment, because the status is `success` even when a review was rate-limited,
  paused, or skipped. After every push it re-checks for a rate limit and queues
  at most one `comenq-coderabbit` request per rate-limited head.
- **CodeScene.** Previously only a failing quality gate triggered repair. Every
  outstanding issue now counts, including advisory findings in a passing check,
  `codescene-access[bot]` inline comments, and local `cs delta` warnings.
- **Comment helper.** The posting function embedded in `references/comments.md`
  is replaced by `skills/pr-babysitting/scripts/post-manual-comment.sh`. The
  token-pool format at `~/.local/share/github-tokens` is unchanged. The helper
  reads the lifecycle account from the stored `gh` login with `GH_TOKEN` and
  `GITHUB_TOKEN` removed; set `PR_BABYSITTING_LIFECYCLE_LOGIN` only where that
  account authenticates solely through an environment token. Callers that
  parsed its diagnostics should expect the new `lifecycle_identity` stage and
  `run_id` field.
- **Lifecycle identity.** `gh pr ready` and merges now run with `GH_TOKEN` and
  `GITHUB_TOKEN` removed, after confirming that the stored login is not a pool
  account. A host whose only lifecycle credential is an environment token must
  provide a stored `gh` login instead.
- **Default trust.** Without a supplied policy, a candidate is trusted for host
  validation only when an authenticated control shows who pushed every commit:
  verified signatures, a push restriction, or the supervisor's own publication
  record. Author and committer fields alone no longer suffice, so some
  candidates that previously ran on the host now need the isolated worker.

Host-wide agent instructions that require the lifecycle account for GitHub
operations should name the comment pool as an explicit exception; see the
[manual-comment identity contract](../skills/pr-babysitting/SKILL.md#manual-comment-identity-contract).

## Repository scratch sidecars

The `scratch` skill standardizes repository-specific experiments, recovery
artefacts, evidence and reproducible caches in a `<repository>.scratch`
sidecar. Linked Git worktrees remain in the separate `<repository>.worktrees`
sidecar; system temporary storage remains for short-lived process scratch. The
authoritative categories, `scratch.toml` contract, retention rules and cleanup
checks are in the
[scratch layout contract](../skills/scratch/references/layout.md).

### Migrating a flat projects directory

Inventory the projects directory and classify registered worktrees separately
from standalone repositories, directories, symlinks and files. Move related
scratch artefacts into a task directory under the matching category in
`<repository>.scratch`, add `scratch.toml`, and verify paths recorded in
patches, receipts and scripts. Keep registered worktrees under
`<repository>.worktrees`. Migration is not mandatory immediately when the
existing flat layout remains usable; migrate before cleanup or when adopting
the sidecar conventions.

## Shared spelling consumption

Moving from a vendored generator and phrase-check script to the pinned
`typos-config-builder gate` command.

### Previous model

A consumer vendored `scripts/generate_typos_config.py` alongside the
`typos_rollout*.py` modules, fetching `data/typos-oxendict-base.toml` from this
repository's `main`. The consumer tracked the generated `typos.toml` and ran
its own repository-local phrase-check script over Git-tracked text.

### New model

A consumer runs `typos-config-builder gate`, pinned to a released tag:

```bash
uvx --from "git+https://github.com/leynos/typos-config-builder.git@v0.1.3" \
  typos-config-builder gate
```

`gate` fetches the shared dictionary live from this repository's `main`, merges
the consumer's optional `typos.local.toml` overlay, rewrites `typos.toml` on
every run, runs the pinned `typos` binary, and enforces the shared phrase
corrections. The fetched dictionary is cached in ignored
`.typos-oxendict-base.toml`, with freshness metadata in
`.typos-oxendict-base.json`, so a valid cache still supports offline runs.

### Migrating an existing consumer

1. Delete the vendored generator and phrase-check scripts, and their tests.
2. Replace the repository's spelling Makefile targets with the single
   `gate` call.
3. Decide whether `typos.toml` stays tracked. Either untrack it — add it to
   `.gitignore` and run `git rm --cached typos.toml` — or keep it tracked only
   as a convenience snapshot that continuous integration never checks for
   drift. This repository (agent-helper-scripts) keeps it tracked because it
   curates the shared dictionary the snapshot is rendered from.
4. Add `.typos-oxendict-base.toml` and `.typos-oxendict-base.json` to
   `.gitignore`; `gate` writes both files as cache files, and neither is a
   policy source.
5. Run `gate` once to regenerate.

### This repository

As of 2026-09-16 the generator is gone from here too. The
`scripts/typos_rollout*.py` modules and their tests are deleted, and
`make spelling` runs the pinned `gate` command against this checkout's own
`data/typos-oxendict-base.toml` with `--scope all`. A repository that copied
those scripts should migrate rather than keep a copy: nothing here maintains
them any longer.

`scripts/oxford_form_harvest_cli.py` remains, because proposing a new shared
word still starts from evidence. It is a curation tool for this repository, not
something a consumer runs.

### Backward compatibility

This rollout is staged, not complete. Migration order and status are tracked in
`docs/execplans/audit-missing-functionality.md` in
`leynos/typos-config-builder`. Until a repository migrates, it keeps its legacy
tooling, which receives dictionary updates but enforces no phrase corrections.

## Whitaker installs refuse source builds

`get-rust-tooling` installed `whitaker-installer` 0.2.6 when `WITH_WHITAKER`
was set. When a published lint library or Dylint tool archive was missing, that
installer compiled it from source, and the install succeeded slowly.

### New behaviour

The default is now 0.2.9, and the installer always runs with
`--no-source-fallback`. A missing published lint library or Dylint tool now
fails the Whitaker install. The script then prints its existing warning,
"Whitaker is not currently available in this environment", and the rest of the
bootstrap continues.

### Migrating

- If you set `WHITAKER_INSTALLER_VERSION`, set it to 0.2.9 or later, or unset
  it to take the default. Older installers reject `--no-source-fallback`, so an
  older pin always ends in the warning.
- If you relied on a source build, for example to try an unpublished lint
  change, run `whitaker-installer` yourself from a Whitaker checkout. This
  script no longer builds from source.
