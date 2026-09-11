---
name: weave-git-merge
description: Use and troubleshoot Weave as an entity-aware Git merge driver during merges, rebases, cherry-picks, and conflict resolution. Use when configuring Weave, previewing a merge, checking whether Git will invoke it, interpreting Weave conflict markers or exit behaviour, detecting structurally corrupt clean results, auditing semantic corruption after a clean replay, bypassing Weave safely, recovering from driver failures, or explaining what Weave actually resolves versus when it falls back to line-level merging.
---

# Use Weave with Git

Treat Weave as a per-file Git merge driver, not as a replacement for `git merge`
or `git rebase`. Git selects it through attributes and invokes
`weave-driver %O %A %B %L %P` for each selected path.

Read [behaviour.md](references/behaviour.md) before diagnosing a surprising
result or deciding whether an unresolved file is safe to edit. In particular,
Weave 0.3.6 has produced clean-exit semantic corruption that parses, compiles,
and passes tests, so neither the driver's exit code nor a structural gate is
sufficient evidence on its own.

Every shell example below requires Bash. This matters for the stage-validation
commands and stderr capture in particular: `set -o pipefail` and process
substitution are Bash features with no POSIX `sh` equivalent.

## Establish the operation and evidence boundary

Perform unattended merge and rebase work in a linked worktree. Treat the
primary checkout as a read-only coordination anchor: do not use it as a scratch,
formatting, conflict-repair, or rebase surface.

Before a rebase or merge, record the candidate and target identities before any
history rewrite:

```bash
OLD_HEAD=$(git rev-parse HEAD)
TARGET=$(git rev-parse origin/main)
MERGE_BASE=$(git merge-base "$OLD_HEAD" "$TARGET")
printf 'old_head=%s\ntarget=%s\nmerge_base=%s\n' "$OLD_HEAD" "$TARGET" "$MERGE_BASE"
```

For a different target, substitute its exact fetched ref. Do not use a mutable
local primary checkout as the implicit base for unattended work. Resolve the
remote target to a commit first.

Before a rebase, establish the exclusive `OLD_BASE` with the
[rebase skill](../rebase/SKILL.md), then bind the semantic audit to that
accepted boundary:

```bash
BRANCH_BASE="$OLD_BASE"
```

For an ordinary merge only, bind it to the recorded merge-base instead:

```bash
BRANCH_BASE="$MERGE_BASE"
```

Assign `BRANCH_BASE` before any audit command below expands it. A target
merge-base is not a squash-restack boundary; it can include inherited parent
work that must not count as child-owned changes.

A completed rebase creates a new candidate. Any gate, review, or merge-eligibility
evidence tied to `OLD_HEAD` is stale for acceptance after the replay. Preserve
it as historical evidence, record the new `HEAD`, and rerun the candidate-bound
checks required by the repository.

Before any destructive `reset`, `clean`, abort-and-retry sequence, or recovery
that could discard manual resolution work, either prove there is no unrelated
work to preserve or create and verify recovery material covering staged,
unstaged, and intended untracked files. A patch that applies successfully does
not prove it captured untracked files. Generate native recovery diffs with
`--no-ext-diff --no-textconv --binary` and keep an explicit untracked-file
manifest.

## Decide whether Weave should participate

First identify why Weave is selected:

```bash
git check-attr merge -- path/to/file.rs
git config --show-origin --get merge.weave.driver
command -v weave-driver
weave-driver --version
weave --version
```

Expect `git check-attr` to report `merge: weave` when selected.
`git check-attr -a -- path` reports only effective attribute values, not which
source supplied them. Inspect `.git/info/attributes`, applicable
`.gitattributes` files, and the configured global attributes file directly (or
the default `$XDG_CONFIG_HOME/git/attributes` / `$HOME/.config/git/attributes`
when no file is configured). Locate an explicitly configured file with
`git config --path --get core.attributesFile`. That command prints nothing and
exits non-zero when the setting is absent, which means the default path applies,
not that no global rule exists; read the default path before concluding that
Weave was selected somewhere else.

For unattended agents, ambient selection is not repository consent. When an
operation will replay multiple commits, or a long-lived branch is being rebased
across substantial target history, bypass Weave up front when it is selected
only by global or clone-local ambient configuration. Use Git's built-in merge
machinery with `zdiff3` instead. Use Weave for such an operation only when the
repository explicitly opts in through tracked attributes or the task explicitly
requests Weave dogfooding/evidence collection.

For a global ambient rule, a typical unattended rebase therefore starts as:

```bash
git -c core.attributesFile=/dev/null \
    -c merge.conflictStyle=zdiff3 \
    rebase origin/main
```

If tracked `.gitattributes` selects Weave, that is explicit repository policy.
Do not silently bypass it. If an authorized recovery requires bypassing a
tracked or clone-local rule, use the scope-specific override below.

Choose one setup scope deliberately when configuring Weave:

```bash
# Tracked for this repository; suitable when the whole team should use Weave.
weave setup

# Untracked for this clone only; writes .git/info/attributes.
weave setup --local

# All repositories for this user; writes global Git config and attributes.
weave setup --global
```

Pass `--driver /absolute/path/to/weave-driver` when auto-detection is
unreliable. Prefer a stable installed path over a versioned build directory.

Use this compact matrix when bypassing Weave after preserving the current
attribute state:

| Setup scope | Rule location | Make `merge` unspecified | Verify, then retry |
| --- | --- | --- | --- |
| Global | Configured global attributes file (or the default path above) | Run Git with `-c core.attributesFile=/dev/null`. | `git -c core.attributesFile=/dev/null check-attr merge -- path/to/file.py` must report `unspecified`; rerun the original operation with the same arguments under the same `-c`. |
| Tracked | Repository `.gitattributes` | Preserve `.git/info/attributes`; add a later path-specific `path/to/file.py !merge` there; restore `.git/info/attributes` only after the operation completes. | `git check-attr merge -- path/to/file.py` must report `unspecified`; rerun the original operation with the same arguments. |
| Clone-local | `.git/info/attributes` | Preserve the file; add a later path-specific `path/to/file.py !merge`; restore `.git/info/attributes` only after the operation completes. | `git check-attr merge -- path/to/file.py` must report `unspecified`; rerun the original operation with the same arguments. |

## Preview before changing Git state

```bash
weave preview other-branch
weave preview other-branch --file path/to/file.ts
```

Use preview as an estimate. It reads the merge base, `HEAD`, and the named
branch directly; it does not reproduce every higher-level Git operation or
pre-existing conflicted stage exactly.

## Merge or rebase with observable driver output

Run the ordinary Git operation. During a rebase, remember that Git's labels
and the human meaning of “ours” and “theirs” are easy to misread. Reason from
the desired rebased result and inspect the stage blobs when provenance matters.

Never discard driver stderr. A line such as
`weave: 5 entities auto-resolved (conflict confidence)` identifies a file or
operation whose clean reconstruction deserves scrutiny; it is not proof of
correctness. On Weave versions that support it, set `WEAVE_EVENT=1` for one
JSON event per merge on stderr. Keep the environment override command-scoped
rather than exporting it across an agent session:

```bash
WEAVE_STDERR=$(mktemp -t weave-rebase.stderr.XXXXXX) || exit 1
env WEAVE_EVENT=1 git rebase origin/main 2>"$WEAVE_STDERR"
REBASE_STATUS=$?
cat -- "$WEAVE_STDERR" >&2

# Fail closed. `grep` exits 1 for "no match" and 2 for "could not read the
# file", so only the latter is a capture failure; an empty capture means the
# driver said nothing, which is itself worth recording rather than assuming.
grep -E 'auto-resolved|^weave-event: ' -- "$WEAVE_STDERR"
GREP_STATUS=$?
if [ "$GREP_STATUS" -gt 1 ]; then
  echo 'andon: driver stderr capture unreadable; stop before the audit' >&2
  exit 1
fi
printf 'rebase_status=%s\nevidence=%s\n' "$REBASE_STATUS" "$WEAVE_STDERR"
```

Read the captured stderr after the operation and correlate every auto-resolved
or event-reported path with the post-operation audit below. A clean exit and a
high-confidence label are evidence about Weave's decision, not evidence that
the merged semantics are correct.

After Git stops on a conflict:

```bash
git status --short
git diff --name-only --diff-filter=U
git ls-files -u -- path/to/file.ts
weave summary path/to/file.ts
```

Inspect the three index inputs without touching the working file:

```bash
git show :1:path/to/file.ts  # merge base
git show :2:path/to/file.ts  # stage 2
git show :3:path/to/file.ts  # stage 3
```

Check structural integrity before trusting either a reported conflict or a
clean driver exit. Use the language's cheapest parser or compiler on the
working file before `git add` or `git rebase --continue`. For Python:

```bash
python -m py_compile path/to/file.py
```

If the merged file is unexpectedly large, duplicated, truncated, or contains
garbled markers, parse each available stage as well. These commands inspect
the blobs without changing the working file:

```bash
set -o pipefail
git show :1:path/to/file.py | python -c \
  'import ast, sys; ast.parse(sys.stdin.read())'
git show :2:path/to/file.py | python -c \
  'import ast, sys; ast.parse(sys.stdin.read())'
git show :3:path/to/file.py | python -c \
  'import ast, sys; ast.parse(sys.stdin.read())'
```

Run only the stage commands for stages that exist. A parsing stage 3 does not
make a non-parsing stage 2 safe: during a multi-commit rebase, stage 2 can
already contain an earlier silently corrupted replay.
A stage must both exist and parse before it is trusted as a baseline, and the
resolved working file must parse before `git add` records the resolution.

During rebase, do not attach branch names to stages 2 and 3 from memory;
identify them from their content and the rebase operation.

`weave summary` understands Weave's enhanced markers. It may report no Weave
conflicts when a path used the line-level fallback and therefore contains
ordinary diff3 markers.

Review the whole merged file, including clean regions. Weave preserves the
ours-side entity ordering, inserts theirs-only entities, merges interstitial
text separately, and performs cleanup and structural validation. A clean exit
means no recorded conflict remains; it is not proof that the result has the
intended semantics.

Resolve remaining markers, perform the structural check, run the repository's
normal formatting, tests, lint, and type checks, then `git add` the path and
continue the Git operation.

## Guard every replayed commit

A cleanly returned but corrupted early replay becomes an input to later
replays. In a later conflict it may appear as stage 2, so reconstruction damage
can compound before an end-of-rebase test ever runs. Each replayed commit's
stage 2 derives from the previous replay's accepted result. The transition rule
is therefore strict: even when the next replay's own output parses,
never accept a structurally invalid result as a safe stage 2 for the next replay.

For agents, a per-replay guard is the default whenever Weave participates in a
multi-commit rebase. Use `git rebase --exec` with the repository's cheapest
credible structural gate, rather than reserving this only for import-relocation
branches.

For Python, for example:

```bash
git rebase --exec 'python -m compileall -q -f path/to/package' origin/main
```

For Rust, `rustfmt` is a useful parser-level tripwire, but it does not establish
workspace type correctness. `cargo check --workspace` is the honest default
when its cost is acceptable:

```bash
git rebase --exec 'cargo check --workspace' origin/main
```

A deliberately cheaper Rust parse guard such as `cargo fmt --all -- --check`
may be used when a workspace check per commit would be prohibitive, but record
that reduced scope explicitly. In every language, the per-replay structural
gate is necessary but not sufficient: the cfg-gated Rust test replacement
recorded in [behaviour.md](references/behaviour.md) parsed, compiled, and passed
tests. Do not rely solely on the full test suite after the final commit.

When dogfooding Weave during the rebase, combine the guard with command-scoped
event capture:

```bash
WEAVE_STDERR=$(mktemp -t weave-rebase.stderr.XXXXXX) || exit 1
env WEAVE_EVENT=1 git rebase \
  --exec 'cargo check --workspace' \
  origin/main 2>"$WEAVE_STDERR"
REBASE_STATUS=$?
cat -- "$WEAVE_STDERR" >&2
if [ ! -s "$WEAVE_STDERR" ] && [ "$REBASE_STATUS" -ne 0 ]; then
  echo 'andon: the rebase failed with no captured driver stderr' >&2
  exit 1
fi
```

## Audit the completed operation semantically

Run this audit after every Weave-participating merge or rebase, even when the
driver exits `0`, every per-replay structural gate passes, and the full test
suite is green. Use the `OLD_HEAD`, `TARGET`, and `MERGE_BASE` recorded before
the operation, plus the accepted `BRANCH_BASE` described above.

First enumerate what the branch and target independently changed:

```bash
git diff --name-only -z "$BRANCH_BASE..$OLD_HEAD" > /tmp/weave-branch-paths.z
git diff --name-only -z "$MERGE_BASE..$TARGET" > /tmp/weave-target-paths.z
```

Then enforce these three checks:

1. **Target-only paths are byte-identical.** Every file changed by the target
   but not by the branch must be byte-identical at the final `HEAD` to the
   target version. Any difference is an andon event. A semantic merge driver
   had no branch-side change to reconcile in that path.
2. **Every deletion against the target in a branch-touched file is explained.**
   Read each deletion hunk in `git diff "$TARGET"..HEAD -- <path>` and map it
   to an intended branch change from `git diff "$BRANCH_BASE".."$OLD_HEAD" --
   <path>` or to a named, reviewed conflict-resolution decision. An unexplained
   deletion is an andon event even if the file compiles and tests pass.
3. **Look for newly repeated blocks.** Scan each resulting text file for a
   multi-line block repeated more often at `HEAD` than at `TARGET`, then inspect
   every new repetition. This catches duplicated re-export/import blocks and
   similar reconstruction artefacts that may remain syntactically valid.

The first check can be automated directly. Compute the set difference between
the NUL-delimited target and branch path manifests above, bind each remaining
path, and run the comparison once per path:

```bash
sort -z /tmp/weave-branch-paths.z > /tmp/weave-branch-paths.sorted.z
sort -z /tmp/weave-target-paths.z > /tmp/weave-target-paths.sorted.z
comm -z -13 \
  /tmp/weave-branch-paths.sorted.z \
  /tmp/weave-target-paths.sorted.z > /tmp/weave-target-only-paths.z

while IFS= read -r -d '' path; do
  # `$path` must be bound before use; comparing an unset variable would widen
  # the check to the whole tree and fail on legitimate branch changes.
  if ! git diff --quiet "$TARGET" HEAD -- "$path"; then
    printf 'andon: target-only path is not byte-identical: %s\n' "$path" >&2
    exit 1
  fi
done < /tmp/weave-target-only-paths.z
```

For the second and third checks, use a repository audit helper when one exists;
otherwise inspect the diffs and repeated-block report explicitly. Do not waive
the review because a parser, compiler, formatter, linter, or test suite is
green. The known Rust cfg-gated sibling replacement is specifically a case
where all of those structural signals can miss the corruption.

Finally run ordinary repository checks such as `git diff --check`, formatting,
lint, type checking, and tests. Markdown doubled-blank-line corruption has been
caught by Markdownlint, while Rust duplicate blocks with stray braces have been
caught by the compiler; these are useful detectors, but they complement rather
than replace the semantic audit.

## Run Weave's own post-merge checker when supported

Record `weave --version` in the operation evidence. The estate is expected to
provision Weave 0.5.1 or newer; on an installed version that supports
`weave check`, run it after the Git operation and before accepting the result:

```bash
weave --version
weave check --help >/dev/null
weave check
```

`weave check` verifies the merged working tree against the merge inputs and can
report leftover markers, lines present on both sides that went missing, and
content repeated more often than either side supplied. Treat findings or an
unsupported/missing checker as explicit evidence states; do not translate
“checker unavailable” into success.

When the Weave MCP server is available, the read-only `weave_check` tool is the
agent-facing equivalent. Use it instead of shelling out when that is the
established integration, and retain its findings with the same candidate
identity. Neither interface replaces the target/branch semantic audit above.

As a read-only verifier, `weave check` or MCP `weave_check` must not mutate the
working tree. Unexpected mutation is an andon event.

## Interpret driver outcomes

- Exit `0`: Weave wrote the result to `%A` and considers it clean. This is not
  semantic acceptance.
- Exit `1`: Weave wrote a partially merged result with conflicts to `%A`; Git
  keeps the path unmerged for manual or agent resolution.
- Exit `2`: invocation, input, output, or binary-file failure. Do not treat
  this as a semantic conflict; inspect stderr and repair the driver/configuration.

The Git driver uses enhanced seven-character markers with entity names and
hints. The `-l` option selects standard diff3-compatible markers and is meant
for tools such as Jujutsu; Git's positional `%L` does not disable enhanced
markers.

Set `WEAVE_VERBOSE=1` to print per-file statistics. Prefer command-scoped
`env WEAVE_VERBOSE=1 ...` rather than a session-wide export. Set
`WEAVE_TIMEOUT` to a whole number of seconds only when the default five-second
entity-merge timeout is unsuitable. A timeout falls back to `git merge-file`;
it does not abort the overall driver invocation.

## Andon triggers

Stop advancing the branch, preserve the current state, and establish the
candidate again when any of these occurs:

- Weave, a parser, compiler, formatter, linter, test, or `weave check` reports a
  failure after a replay;
- a target-only path differs from `TARGET` after the operation;
- a branch-touched path contains an unexplained deletion against `TARGET`;
- a repeated-block scan finds a new duplication that cannot be justified;
- driver stderr records an auto-resolution whose affected path has not yet been
  audited;
- the installed `weave` and `weave-driver` versions disagree unexpectedly, or
  the required post-merge checker is unavailable;
- source or compiled artefact provenance disagrees;
- recovery evidence omits staged, unstaged, or intended untracked work;
- the rebase changes the candidate head while old gate/review evidence is still
  being treated as current.

An andon event is not an instruction to guess a repair. Preserve evidence,
identify the authoritative inputs, and either rerun with built-in Git merging
or investigate the specific reconstruction before continuing.

## Recover safely

Before rerunning or replacing a result, preserve it or inspect the index
stages. Commands that recreate conflict markers can overwrite Weave's
partially merged `%A` file. Do not perform a destructive abort until any manual
resolution work or unrelated local state that matters has verified recovery
coverage, including intended untracked files.

If Weave was selected but never ran, check attribute precedence, the exact
config scope, executable discovery, and quoting of a driver path containing
spaces. If the driver returned `2`, use its stderr to distinguish missing
inputs, binary detection, and write failure.

If Weave returned `0` with structurally or semantically broken output, do not
repair the result in place. Rerun the whole operation with the built-in merge
machinery. How you return to the recorded candidate depends on whether the
operation is still in progress:

- **Still in progress.** `git rebase --abort`, `git merge --abort`, or
  `git cherry-pick --abort` restores the pre-operation state.
- **Already completed.** A clean driver exit lets Git finish, so the operation
  state those abort commands need is gone and they fail. Restore the recorded
  candidate with `git reset --hard "$OLD_HEAD"` instead, and only once recovery
  evidence for staged, unstaged, and intended untracked work has been captured
  and verified. The reset discards all of it.

Retry against the recorded `TARGET`, not `origin/main`. The remote ref is
mutable and may have moved since the candidate identities were recorded, so
reusing it would silently retry against different history than the audit
covered.

For a global setup, first verify that ignoring the user attributes file makes
`merge` unspecified for a representative affected path, then use the same
override for the rebase, merge, or cherry-pick:

```bash
# Only after recovery evidence is verified. Use the abort for an interrupted
# operation, or the reset for one a clean driver exit allowed to complete.
git rebase --abort
git reset --hard "$OLD_HEAD"

git -c core.attributesFile=/dev/null check-attr merge -- path/to/file.py
# path/to/file.py: merge: unspecified
git -c core.attributesFile=/dev/null rebase "$TARGET"

# For a merge, abort it or reset to "$OLD_HEAD", then retry with the same
# original arguments resolved against the recorded target:
git merge --abort
git -c core.attributesFile=/dev/null merge <same-original-arguments>

# For a cherry-pick, likewise:
git cherry-pick --abort
git -c core.attributesFile=/dev/null cherry-pick <same-original-arguments>
```

For unattended rebase recovery, also force the expected conflict style for the
retry without mutating persistent Git configuration:

```bash
git -c core.attributesFile=/dev/null \
    -c merge.conflictStyle=zdiff3 \
    rebase "$TARGET"
```

This override disables only the user attributes file for those commands.
Repository-tracked `.gitattributes` and `.git/info/attributes` still apply, so
it preserves unrelated repository merge rules. It is suitable when
`weave setup --global` supplied the `merge=weave` rule and no higher-precedence
source selects Weave. For tracked or clone-local setup, use the corresponding
matrix row above; `/dev/null` alone cannot override those rules. A later
path-specific `!merge` line in `.git/info/attributes`
outranks every attribute source for that path, which is why it is the bypass
for tracked and clone-local rules.

Remove repository configuration with `weave unsetup`. It removes the local
`merge.weave` section and Weave rules from `.gitattributes` and
`.git/info/attributes`; it does not remove global setup.
