# Weave merge behaviour

## Contents

- [Git driver contract](#git-driver-contract)
- [Resolution pipeline](#resolution-pipeline)
- [What resolves cleanly](#what-resolves-cleanly)
- [Known clean-exit corruption](#known-clean-exit-corruption)
- [What remains conflicted](#what-remains-conflicted)
- [Fallbacks and limits](#fallbacks-and-limits)
- [Driver observability](#driver-observability)
- [Post-merge validation](#post-merge-validation)
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

The contract above describes what the driver reports, not what Git or an agent
may safely infer. A return code of `0` means the driver accepted the bytes it
wrote. It is not a semantic proof of the resulting file.

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
test the result, then perform the target/branch audit in the main skill.

Do not generalize the import-addition case to import relocation. With
`weave-driver 0.3.6`, relocating symbols between modules while another branch
reorders the same top-level import block has produced duplicated, truncated,
non-parsing Python despite a clean exit. That combination is unsafe for
semantic reconstruction and belongs on the line-level-fallback path.

## Known clean-exit corruption

The following failures have been observed with `weave-driver 0.3.6`. They are
regression evidence for operator and agent policy; they do not establish that a
later version has the same defects.

### Python import relocation

A branch relocating symbols between modules while another branch reordered the
same top-level import block produced duplicated and truncated Python. The
driver returned `0`; the result did not parse. This is the original reason the
skill requires a parser or compiler after every replayed commit.

### Rust cfg-gated sibling replacement

During a rebase, a real test body in `tests/settings.rs` was silently replaced
by the stub body of its sibling test under the opposite `cfg`. Both merge
parents contained the real body, and the branch had not changed the file. The
result parsed, compiled, and passed the test suite because the substituted stub
was itself valid Rust and a valid test.

This is the critical counterexample to “compile after every replay is enough”.
Structural gates can detect malformed output; they cannot prove that a clean
semantic reconstruction retained the correct entity body. The post-operation
audit must therefore require files changed by the target but untouched by the
branch to remain byte-identical to the target, and must inspect unexplained
deletions in branch-touched files.

### Rust re-export duplication

`src/bootstrap/mod.rs` gained a second copy of a `pub use { ... }` block plus
two stray closing braces. The shape reproduced in both a rebase and a merge of
main into another branch. The compiler caught this corruption, so a per-replay
Rust structural gate remains valuable even though it is not sufficient for the
cfg-gated replacement above.

### Markdown doubled blank lines

Two Markdown guides acquired doubled blank lines. Markdownlint rule MD012
caught the damage. Formatting and linting are therefore useful post-merge
sensors, but a clean Markdown result cannot be inferred from the merge driver's
exit status.

Taken together, these incidents establish two independent requirements:

1. run a parser/compiler/formatter/linter tripwire during or immediately after
   replay; and
2. audit semantic preservation against the recorded target and original branch
   after the complete operation.

Neither requirement subsumes the other.

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
Git cannot be executed, the final fallback is Diffy. Routing such formats
through the driver can therefore add a process hop without necessarily adding
semantic merge value; attribute policy should be deliberate rather than a
blanket global default.

The driver rejects NUL-containing input before reaching the core fallback.
This produces exit `2`, allowing Git or the operator to handle the binary path
instead of accepting a text merge.

Validation is intended to send an unsafe clean reconstruction through the
line-level fallback. A successful driver exit is not proof that this happened:
version 0.3.6 has been observed returning `0` for both malformed reconstruction
and semantically wrong but valid Rust. Parse or compile intermediate results,
but always perform the semantic post-operation audit as well.

## Driver observability

Driver stderr is evidence and must be retained for agent-driven operations.
Version 0.3.6 has emitted summary lines of the form:

```text
weave: 5 entities auto-resolved (conflict confidence)
```

An auto-resolved count identifies reconstruction work that deserves inspection;
it is not a success certificate. Correlate these lines with the paths touched
by the operation and the post-operation audit.

Weave 0.5.x adds the optional `WEAVE_EVENT=1` channel. When enabled for the Git
command, the driver writes one JSON line per merge to stderr behind a
`weave-event: ` prefix. Preserve these lines with the operation receipt. Use a
command-scoped environment override rather than exporting `WEAVE_EVENT` across
an agent session.

Record both binaries before relying on version-specific behaviour:

```text
weave --version
weave-driver --version
```

An unexpected CLI/driver mismatch is an environment finding. Do not assume the
CLI feature set from the driver's version or vice versa.

## Post-merge validation

A parser or compiler remains the first cheap detector for malformed clean
output. For a multi-commit rebase, run that detector through `git rebase
--exec` after every replayed commit. For Rust, `rustfmt` provides a parser-level
tripwire while `cargo check --workspace` is the stronger type-correctness gate
when its cost is acceptable.

That structural gate does not detect the cfg-gated sibling replacement above.
After the full operation, compare the pre-operation branch and target against
the resulting `HEAD`:

- a path changed by the target but untouched by the branch must be byte-identical
  to the target;
- every deletion against the target in a branch-touched path must be explained
  by the original branch intent or a named conflict-resolution decision;
- newly repeated multi-line blocks at `HEAD` that were not repeated at the
  target require inspection.

Weave 0.5.1 and later provide `weave check` in the expected estate baseline.
It verifies a merged working tree and can detect leftover markers, lines that
both sides retained but the result lost, and content stated more often than
either side supplied. The MCP server exposes the corresponding read-only
`weave_check` tool. Use either when supported, but retain the independent
branch/target audit because tool self-validation is not an independent semantic
oracle.

## Supported setup patterns

Observed setup writes `merge=weave` for a broad set of code and data formats,
including:

```text
ts tsx js mjs cjs jsx py go rs java c h cpp cc cxx hpp hh hxx rb cs php
swift ex exs sh f90 f95 f03 f08 xml plist svg csproj fsproj vbproj json
yaml yml toml md scala sc sbt kojo mill dart
```

This setup list is narrower than every parser or format mentioned in project
documentation. Trust `git check-attr merge -- path` for the current repository,
and add an explicit attribute rule only after confirming the installed Weave
version handles that format acceptably.

For unattended agents, a rule arriving only from global or clone-local ambient
configuration is not repository consent for a long multi-commit replay. The
main skill therefore defaults such operations to built-in Git merging with
`zdiff3`. A tracked `.gitattributes` rule is an explicit repository opt-in and
should be respected unless an authorised recovery says otherwise.
