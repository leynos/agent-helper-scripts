# Scratch sidecar layout and manifest contract

Use this contract when establishing a repository scratch sidecar or deciding
whether its contents can be retired.

## Layout

For a repository at `~/Projects/Example`, use:

```text
~/Projects/
|-- Example/
|-- Example.worktrees/
`-- Example.scratch/
    |-- README.md
    |-- active/
    |-- recovery/
    |-- evidence/
    |-- experiments/
    `-- cache/
```

The category directories have distinct meanings:

| Category      | Contents                                                                            | Default cleanup rule                                                                    |
| ------------- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `active`      | Session hand-offs and temporary coordination state that do not fit another category | Retain while owned; reclassify when the task ends                                       |
| `recovery`    | Git bundles, binary patches, untracked-file archives and verified recovery receipts | Explicit item-by-item authorization only                                                |
| `evidence`    | Gate logs, review reports, reproduction captures and decision inputs                | Remove after recorded retention when no review, incident or audit still depends on them |
| `experiments` | Standalone clones, extracted source trees, apply checks and disposable prototypes   | Remove when expired, inactive and checked for unique work                               |
| `cache`       | Reproducible downloads and generated data                                           | Remove when inactive and affordable to rebuild                                          |

`active` is a coordination category rather than a dumping ground. Move durable
recovery or evidence out of it at task closeout.

Keep `README.md` short. State who owns the sidecar, how task identifiers are
chosen, which retention durations apply locally and how cleanup is authorized.
Do not duplicate individual task manifests in it.

## Task directories

Group files by task below a category:

```text
Example.scratch/
|-- recovery/
|   `-- pr-123-rebase/
|       |-- scratch.toml
|       |-- old-head.bundle
|       `-- working-tree.patch
`-- experiments/
    `-- issue-456-parser-probe/
        |-- scratch.toml
        `-- checkout/
```

Task identifiers should be stable and meaningful. Prefer `pr-123-rebase`,
`issue-456-parser-probe` or `session-<id>-<purpose>` over timestamps alone. Add
a suffix only to distinguish concurrent attempts.

## `scratch.toml`

Every substantial task directory should contain `scratch.toml`:

```toml
schema_version = 1
owner = "codex-session-id"
purpose = "Rehearse PR 123 rebase and preserve its old head"
source_repository = "/home/user/Projects/Example"
created_at = "2026-09-20T12:00:00Z"
expires_at = "2026-10-04T12:00:00Z"
retention = "recovery"
reproducible = false
related_pull_requests = [123]
related_issues = []

[provenance]
source_ref = "refs/heads/feature/example"
source_commit = "0123456789abcdef0123456789abcdef01234567"
capture = "git bundle plus binary working-tree patch"
verification = "bundle lists source commit; patch passes git apply --check"
```

Required fields are `schema_version`, `owner`, `purpose`, `source_repository`,
`created_at`, `retention` and `reproducible`. Use RFC 3339 UTC timestamps.
The optional fields are `expires_at`, `related_pull_requests`, `related_issues`
and `provenance`. For `retention = "recovery"`, the structured `[provenance]`
table is required and its `verification` field must be a non-empty string. For
non-recovery material, `provenance` may be omitted when no source-specific
provenance is needed. `expires_at` is optional for recovery data and expected
for evidence, experiments and caches.

Allowed retention values are `active`, `recovery`, `evidence`, `experiment` and
`cache`. The value should agree with the parent category. A mismatch blocks
automatic cleanup until a person or owning agent resolves it.

Use `provenance` for data whose value depends on a particular ref, commit,
input, tool version or capture method. Recovery material must describe how its
contents were verified. Reproducible data should name the command or source
needed to rebuild it.

## Retention and deletion decisions

Evaluate candidates in this order:

1. **Ownership:** An active owner, process or watcher blocks deletion.
2. **Classification:** Missing or invalid manifests require manual review.
3. **Uniqueness:** Unpublished commits, working changes, untracked files and
   sole recovery copies block deletion until preserved or discarded explicitly.
4. **External dependency:** Active pull requests, incidents, audits or reviews
   may extend evidence retention.
5. **Expiry:** Only then does the expiry timestamp make the path eligible.
6. **Rebuild cost:** Cache cleanup may still be deferred when regeneration is
   unusually expensive.

The cleanup preview should be machine-readable when practical and include, at
minimum, the absolute path, category, owner, size, expiry, Git state and reason
for the proposed action. Preserve that preview as evidence when the deletion is
large or discards explicitly authorized recovery data.

## Migration from a flat projects directory

Inventory before moving anything. Classify registered worktrees separately from
standalone Git repositories, ordinary directories, symlinks and files. Do not
infer safety from a filename such as `offline`, `review`, `proof` or `old`.

Move related artefacts into one task directory, write the manifest and verify
that paths recorded inside patches, receipts or scripts remain meaningful. Keep
registered worktrees under the worktree manager's layout. After migration, the
projects directory should contain the repository, its `<repository>.worktrees`
sidecar and its `<repository>.scratch` sidecar rather than a flat collection of
project-prefixed artefacts.
