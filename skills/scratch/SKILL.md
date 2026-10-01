---
name: scratch
description: >-
  Create, audit, migrate and retire repository scratch sidecars; excludes linked
  Git worktrees and system temporary files.
---

# Repository Scratch Sidecars

Keep project scratch data in one visible sibling sidecar instead of scattering
task directories and recovery files through a projects directory. For a
checkout named `Example`, use `Example.scratch`; keep linked worktrees in
`Example.worktrees`.

Scratch placement does not make data disposable. Classify it by recovery value,
record its owner and lifetime, and obtain authorization for deletion separately
from authorization to create or use it.

Read [the layout and manifest contract](references/layout.md) before creating a
sidecar, moving existing material into one, or approving a cleanup sweep.

## Choose the right location

- Put active linked Git worktrees under `<repository>.worktrees/` and manage
  them with the repository's worktree workflow.
- Put task-local standalone clones, extracted trees, apply checks and
  disposable experiments under `<repository>.scratch/experiments/`.
- Put patches, bundles, manifests and receipts needed to recover unpublished
  work under `<repository>.scratch/recovery/`.
- Put test logs, review reports, reproduction captures and other retained
  observations under `<repository>.scratch/evidence/`.
- Put reproducible downloads and generated data under
  `<repository>.scratch/cache/`.
- Use the system temporary directory for short-lived process scratch that does
  not need to survive the command or session.

Do not place ordinary build output in the sidecar when the project's normal
build cache already owns it. Do not move credentials, unredacted secrets or
machine-global configuration into scratch storage.

## Create a task area

Use a stable task identifier derived from an issue, pull request, session or
short purpose. Create a task directory in the category that matches its
retention semantics, then add `scratch.toml` before producing substantial data.

Record:

- the owning person, agent or session;
- the purpose and source repository;
- creation and optional expiry timestamps;
- the retention class;
- related issues or pull requests; and
- enough provenance to decide whether the data is reproducible or unique.

Keep one task's related files together. Prefer a new task directory over
unstructured names at the sidecar root. Update the manifest when ownership,
retention or recovery status changes.

## Promote valuable results

Before retiring an experiment, classify every result:

- Commit and publish source changes that belong in the repository.
- Move verified recovery patches or Git bundles into `recovery/` and record
  the refs, commits, working-tree state and verification method they preserve.
- Move evidence needed for a current review, incident or acceptance decision
  into `evidence/` with a finite retention period.
- Leave only reproducible material in `cache/`.

A clean Git working tree does not prove publication. Check its branch,
upstream, unpushed commits, detached commits, submodules, untracked files and
ignored local data separately. A patch does not preserve untracked files unless
the recovery manifest says how they were captured.

## Clean up safely

Treat cleanup as a reviewed deletion operation:

1. Inventory task manifests and unclassified paths. Stop if the sidecar root
   contains loose data whose owner or retention class is unknown.
2. Detect processes whose current directory, open workspace or watcher lies
   inside a candidate. Coordinate their shutdown; do not kill another task.
3. Inspect Git repositories and recovery artefacts for unpublished or unique
   work. Promote anything still needed before deletion.
4. Check expiry and retention policy. Expiry makes an item reviewable for
   deletion; it does not override active ownership or recovery value.
5. Produce an exact dry-run list with path, category, size and deletion reason.
6. Delete only the reviewed candidates. Do not follow symlinks outside the
   sidecar, broaden a failed glob, or substitute a recursive sweep for an
   incomplete inventory.
7. Re-inventory the sidecar and report removed, retained and failed paths plus
   the recovered space.

Routine cleanup may remove reviewed expired experiments and reproducible cache
entries. It must not remove `recovery/` material without explicit authorization
for those exact recovery items. Evidence follows its stated retention policy,
subject to active review, incident and audit needs.

## Report the result

For creation, report the sidecar, category, task path, manifest and intended
retention. For an audit, separate active, recoverable, expired, unclassified
and reproducible material. For cleanup, report the reviewed preview, deletion
authorization, failures, retained recovery data and space reclaimed.
