# Weave merge behaviour

## Contents

- [Git driver contract](#git-driver-contract)
- [Resolution pipeline](#resolution-pipeline)
- [What resolves cleanly](#what-resolves-cleanly)
- [What remains conflicted](#what-remains-conflicted)
- [Fallbacks and limits](#fallbacks-and-limits)
- [Supported setup patterns](#supported-setup-patterns)

## Git driver contract

Setup records this command:

```text
weave-driver %O %A %B %L %P
```

Git supplies ancestor, current-side temporary path, other-side temporary path,
marker length, and logical repository path. The driver reads all three inputs,
uses `%P` to select a parser, and overwrites `%A`. This is true for both clean
and conflicted results. It then returns `0` for clean, `1` for unresolved, or
`2` for operational failure and binary input.

The driver records lifetime statistics on a best-effort basis. Statistics and
optional conflict-free replicated data type (CRDT) recording never decide
merge success.

## Resolution pipeline

The engine applies these layers:

1. Preserve an input that already contains conflict markers and report a
   file-level conflict; nested three-way merging of pre-conflicted text is
   deliberately avoided.
2. Take identical sides, or take the side changed from an unchanged base.
3. Fall back when content is binary, over 1 MB, unsupported, unparsable,
   newly created differently on both sides with an empty base, or dominated by
   duplicate entity names.
4. Parse top-level semantic entities and match base-to-branch entities,
   including structural rename detection.
5. Resolve each entity independently, merge text between entities, and
   reconstruct using ours as the ordering skeleton.
6. Clean duplicate/blank-line artefacts and validate a clean, jointly modified
   result. Validation warnings can force a line-level retry when semantic
   reconstruction looks unsafe.

The core bridge is `entity_merge_with_registry`; the driver wraps it in a
five-second timeout and uses `git merge-file` on timeout.

## What resolves cleanly

Common clean cases include:

- only one branch changes, adds, or deletes an entity;
- both branches produce identical entity content;
- branches change different functions or top-level entities;
- branches change different members inside supported container entities;
- one branch changes only whitespace while the other changes content;
- compatible edits within one entity succeed through a three-way text merge;
- compatible decorator/annotation additions merge commutatively;
- many import additions and supported grouped or multiline imports merge
  commutatively;
- some structural renames are tracked so an entity is not emitted twice.

These are implementation strategies, not semantic proofs. Always compile or
test the result.

Do not generalize the import-addition case to import relocation. With
`weave-driver 0.3.6`, relocating symbols between modules while another branch
reorders the same top-level import block has produced duplicated, truncated,
non-parsing Python despite a clean exit. That combination is unsafe for
semantic reconstruction and belongs on the line-level-fallback path.

## What remains conflicted

Expect an entity-scoped or file-scoped conflict for:

- incompatible edits to the same entity after all inner strategies fail;
- modify/delete cases;
- different content added under the same new entity identity;
- both branches renaming the same base entity differently;
- rename-plus-modify cases that require human review;
- conflicting text between semantic entities;
- pre-existing markers in any input;
- any fallback merge that `git merge-file` or Diffy cannot resolve.

Container conflicts may be narrowed to an individual method or member. Common
prefix and suffix lines are emitted outside the marker. Enhanced Git-driver
markers annotate the entity and deletion side; standard `-l` mode includes a
diff3 base section.

## Fallbacks and limits

Unknown file types do not receive arbitrary 20-line “semantic” chunks; they go
straight to line-level merging. Code-like fallback text first tries separator
expansion plus Diffy, compares its conflict-marker count with `git merge-file`,
and keeps the result that is no worse by that measure.

Data formats and lock files skip separator expansion and use
`git merge-file --diff3` directly because expansion can worsen alignment. If
Git cannot be executed, the final fallback is Diffy.

The driver rejects NUL-containing input before reaching the core fallback.
This produces exit `2`, allowing Git or the operator to handle the binary path
instead of accepting a text merge.

Validation is intended to send an unsafe clean reconstruction through the
line-level fallback. A successful driver exit is not proof that this happened:
version 0.3.6 has been observed returning `0` for non-parsing reconstruction in
the import-relocation case above. Parse or compile intermediate results before
allowing a multi-commit rebase to continue.

## Supported setup patterns

Current setup writes `merge=weave` for:

```text
ts tsx js mjs cjs jsx py go rs java c h cpp cc cxx hpp hh hxx rb cs php
swift ex exs sh f90 f95 f03 f08 xml plist svg csproj fsproj vbproj json
yaml yml toml md scala sc sbt kojo mill dart
```

This setup list is narrower than every parser or format mentioned in project
documentation. Trust `git check-attr merge -- path` for the current repository,
and add an explicit attribute rule only after confirming the installed Weave
version handles that format acceptably.
