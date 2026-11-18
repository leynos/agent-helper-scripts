---
name: weave-git-merge
description: >-
  Configure and troubleshoot Weave's entity-aware Git merge driver; verify
  clean results and recover or bypass it safely.
---

# Use Weave with Git

Treat Weave as a per-file Git merge driver, not as a replacement for
`git merge` or `git rebase`. Git selects it through attributes and invokes the
command recorded in `merge.weave.driver` for each selected path. Upstream setup
records `weave-driver %O %A %B %L %P`; the estate baseline described below
records a quoted absolute driver path with `WEAVE_EVENT=1` in front of it.

Read [behaviour.md](references/behaviour.md) before diagnosing a surprising
result or deciding whether an unresolved file is safe to edit. In particular,
Weave 0.3.6 has produced clean-exit semantic corruption that parses, compiles,
and passes tests, so neither the driver's exit code nor a structural gate is
sufficient evidence on its own. The 0.5.1 baseline is a containment change, not
evidence that those defects are fixed.

Every shell example below requires Bash. This matters for the stage-validation
commands and stderr capture in particular: `set -o pipefail` and process
substitution are Bash features with no POSIX `sh` equivalent.

## Know the estate baseline

The `dev-env-rocky` deployment pins `weave-cli` and `weave-driver` to the
upstream `v0.5.1` tag and separates driver registration from attribute-based
activation:

- The driver is registered globally as
  `WEAVE_EVENT=1 '<home>/.cargo/bin/weave-driver' %O %A %B %L %P`. The path is
  absolute and shell-quoted so a PATH-shadowing driver cannot intercept an
  opted-in operation, and every invocation emits one `weave-event:` line.
- Registration defines `merge.weave` and does not select it. A managed,
  marker-delimited block in the global Git attributes file selects it.
- Managed user-wide enrolment selects `merge=weave` for `rs`, `py`, `ts`, and
  `tsx` by default. It refuses data, Markdown, and lock-file extensions
  user-wide: `csv`, `json`, `json5`, `jsonc`, `lock`, `markdown`, `md`, `mdx`,
  `toml`, `xml`, `yaml`, and `yml`.
- Provisioning owns only its managed block. Other rules in the same file,
  custom `core.attributesFile` targets, and repository attributes still need
  inspection.
- `merge.conflictStyle=zdiff3` is set globally, so native text merges keep
  the base section a reviewer needs.
- `weave setup --global` remains prohibited. Managed provisioning owns
  user-wide enrolment; that command writes outside the managed block.
- No `weave-mcp` server, audit sidecar, or findings sidecar is provisioned.

Verify the host before relying on any of this:

```bash
weave --version
weave-driver --version
weave check --help >/dev/null
type -a weave weave-driver
git config --show-origin --show-scope --get-all merge.weave.driver
git config --show-origin --show-scope --get-all merge.conflictStyle
git config --show-origin --show-scope --get-all merge.default
git config --show-origin --show-scope --get-regexp '^merge\.text\.'
git check-attr merge -- src/lib.rs app.py app.ts app.tsx README.md Cargo.toml
```

Both binaries must report `0.5.1`, and the versions resolved on `PATH` must
match the canonical `~/.cargo/bin` binaries. In a repository without its own
attributes, `git check-attr merge` must report `merge: weave` for enrolled
Rust, Python, TypeScript, and TSX paths, and `merge: unspecified` for other
paths unless the repository opts in. Unexpected selection outside the managed
defaults, or from another ambient source, is an environment finding. So is
unexpected Weave selection for a refused category such as Markdown, data, or
lock files. `merge.default` must not name `weave`: `check-attr` still reports
`unspecified` for an unselected path, yet Git consults that fallback and runs
Weave on it, so a `!merge` opt-out does not bypass Weave while the setting
stands. Any `merge.text.*` key is also a finding. Git treats that section as a
custom driver named `text` and resolves custom drivers before its built-ins, so
`merge.text.driver` redirects every `merge=text` rule to its command, and with
only `merge.text.name` set the selection aborts with
`custom merge driver text lacks command line` instead of falling back. The
probe must therefore cover the whole section: printing nothing and exiting 1
means no custom `text` driver, while any other failure is a configuration read
error rather than an absent driver. A repository's own reviewed attribute rule,
and dogfooding the task explicitly requests, are deliberate enrolment rather
than host faults. A host that reports `0.3.6` has not been reconciled either.
Record any unexpected selection as an environment finding and apply the
unattended bypass below rather than assuming the baseline.

## Establish the operation and evidence boundary

Perform unattended merge and rebase work in a linked worktree. Treat the
primary checkout as a read-only coordination anchor: do not use it as a
scratch, formatting, conflict-repair, or rebase surface.

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

A completed rebase creates a new candidate. Any gate, review, or
merge-eligibility evidence tied to `OLD_HEAD` is stale for acceptance after the
replay. Preserve it as historical evidence, record the new `HEAD`, and rerun
the candidate-bound checks required by the repository.

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
source supplied them. Inspect the clone's `info/attributes`, resolved with
`git rev-parse --git-path info/attributes` (a linked worktree has no
`.git/info/attributes`), the applicable `.gitattributes` files, and the
configured global attributes file directly (or the default
`$XDG_CONFIG_HOME/git/attributes` / `$HOME/.config/git/attributes` when no file
is configured). Locate an explicitly configured file with
`git config --path --get core.attributesFile`. That command prints nothing and
exits non-zero when the setting is absent, which means the default path
applies, not that no global rule exists; read the default path before
concluding that Weave was selected somewhere else.

For unattended agents, ambient selection is not repository consent. Managed
user-wide enrolment selects Weave through the global attributes file, so it is
ambient selection, not repository consent for an unattended multi-commit
replay. When an operation will replay multiple commits, or a long-lived branch
is being rebased across substantial target history, bypass Weave up front when
it is selected only by that managed block, or by other global or clone-local
ambient configuration. Use Git's built-in merge machinery with `zdiff3`
instead. Use Weave for such an operation only when the repository explicitly
opts in through tracked attributes and the task explicitly requests Weave
dogfooding/evidence collection.

For an unattended rebase, use the command-scoped driver override. It replaces
the named driver for every path, whichever attribute source selected Weave,
including a tracked `.gitattributes` rule that a replayed commit introduces
part-way through the operation, so it does not depend on a pre-rebase check. It
does not edit the repository's attribute files:

```bash
git -c merge.conflictStyle=zdiff3 \
    -c merge.weave.driver='git merge-file --zdiff3 --marker-size=%L %A %O %B' \
    -c merge.weave.recursive=text \
    rebase --exec 'cargo check --workspace' "$TARGET"
```

Run `--exec` only on commits trusted to execute as the local user. The guard
compiles the replayed tree, so a contributor's `build.rs` or test harness runs
with the operator's credentials; for an untrusted branch, omit `--exec` and run
the same checks after review in an isolated checkout.

`-c merge.weave.recursive=text` names the driver Git uses to build virtual
ancestors in a criss-cross merge, and that name resolves like any other. A host
`merge.text.*` section would therefore run for virtual-ancestor creation even
though the Weave driver is overridden. Confirm
`git config --get-regexp '^merge\.text\.'` prints nothing before using the
override. A single-base rebase creates no virtual ancestor, but a criss-cross
merge does.

Repeat the same `-c` overrides on every `git rebase --continue`; Git reads the
driver configuration again for each replayed commit. Do not confuse this with
`--ours` or `--theirs`, which discard one side of a conflict. The override
targets Weave only; other custom merge drivers need their own policy.

The override also does not forward `-X` options. Git passes `-Xours`,
`-Xtheirs`, and the other strategy options to its own merge strategy, never to
an external driver, so a path the override resolves with `git merge-file` can
leave conflict markers where native `-Xours` would have taken the current side.
Where native `-X` behaviour matters for particular paths, add a bare `merge`
rule for them in the clone-local attributes file: it selects Git's built-in
text merge, which honours `-X`. Keep the driver override for ordinary text
replays.

A narrower alternative is safe only when no tracked, clone-local, or system
rule can select Weave for any path in the replay, and no custom `text` driver
is configured:

```bash
git config --get-regexp '^merge\.text\.'   # must print nothing and exit 1
git -c core.attributesFile=/dev/null \
    -c merge.default=text \
    -c merge.conflictStyle=zdiff3 \
    rebase "$TARGET"
```

`-c merge.default=text` closes the other route to Weave: disabling the user
attributes file leaves each formerly enrolled path unspecified, and Git then
consults `merge.default`. The value `text` is a driver name, and Git resolves
custom drivers before its built-ins, so a host `merge.text.*` section registers
a custom driver that runs instead; a `merge.text.name` on its own aborts the
operation rather than restoring the built-in. That is why the preflight must
print nothing and exit 1. `core.attributesFile=/dev/null` does not disable the
system attributes file, so also confirm that file selects nothing for the
replay, or run the operation with `GIT_ATTR_NOSYSTEM=1` as well. `check-attr`
reports the working tree's attributes at the moment it runs, not those Git
applies to a later replayed commit, so a `.gitattributes` rule that the target
or a replay introduces is invisible to that check. Verify every path the replay
can already see, and use the driver override for any replay that can add such a
rule: `/dev/null` alone cannot override those rules.

This prefix belongs on every command of the operation, not only the first:
repeat the same `-c` overrides — and `GIT_ATTR_NOSYSTEM=1`, when the system
attributes file had to be excluded — on each `git rebase --continue` and any
authorized `git rebase --skip`. Git reads the merge configuration again for
each replayed commit, so a prefix applied only to the opening invocation does
not cover the rest of the replay.

If tracked `.gitattributes` selects Weave, that is explicit repository policy
for attended merges and for dogfooding the repository has asked for. Do not
silently bypass it for attended work. The estate baseline still routes an
unattended long-lived branch rebase through Git's text merge unless the
operator explicitly requests dogfooding, so record the override in the
operation receipt.

Choose one setup scope deliberately when configuring Weave:

```bash
# Tracked for this repository; suitable when the whole team should use Weave.
weave setup

# Untracked for this clone only; writes .git/info/attributes.
weave setup --local

# All repositories for this user; writes global Git config and attributes.
weave setup --global
```

Under the estate baseline, do not run `weave setup --global`: it writes
user-wide attributes outside the managed block, claims nearly every extension
the parser registry supports — the registry minus the extensions it declines at
the source (`.hs`, `.vue`, `.erb`, and the `.svelte*` family) — which includes
refused data and Markdown formats such as `*.csv` and `*.md` but not `.lock`,
and rewrites user-wide Git configuration, which can replace the managed driver
registration. Managed provisioning owns user-wide enrolment. Review the output
of a bare `weave setup` before accepting it; since 0.4.0 its claim set is
derived from the parser registry with the same declines subtracted, so it grows
whenever a grammar is added upstream. Prefer a handwritten, narrow tracked or
clone-local rule for reviewed paths beyond the managed defaults, such as
`src/*.rs merge=weave`, and do not add JSON, TOML, YAML, Markdown, or lock
files to an experiment by default.

Pass `--driver /absolute/path/to/weave-driver` when auto-detection is
unreliable. Prefer a stable installed path over a versioned build directory.

Both per-repository scopes also write `merge.weave.driver` to the repository's
local Git config. That command is the bare driver path followed by
`%O %A %B %L %P`, without `WEAVE_EVENT=1` and without shell quoting, and local
config outranks the global registration for every path Git sends to Weave,
including paths selected only by the managed block. A repository-local setup
therefore replaces event capture and the quoted canonical path for that clone,
whatever attributes select. On a managed host, verify the effective value with
`git config --show-origin --get merge.weave.driver`; it must keep
`WEAVE_EVENT=1` and the quoted absolute path, or the local setup has to be
reversed with `weave unsetup`.

Repository attributes take precedence over the managed user-wide block, so a
repository can opt out persistently. `*.rs !merge` in `.git/info/attributes`
makes the attribute unspecified for this clone without sharing the change.
Unspecified is not itself a driver: Git then consults `merge.default`, which is
the built-in text merge unless configured. If `merge.default` names Weave,
`!merge` does not bypass it. Prefer a rule that selects Git's built-in text
merge directly: a bare `merge` attribute (`*.rs merge`) does that, and
`git check-attr merge` reports `merge: set`. `*.rs merge=text` in
`.gitattributes` is tracked and opts out every clone that does not already
select Weave from a higher-precedence source, but it names the `text` driver,
and Git resolves custom drivers before its built-ins, so a host `merge.text.*`
section runs instead, or aborts when the section has no driver command; use
that form only when `git config --get-regexp '^merge\.text\.'` prints nothing.
`merge=text` is unaffected by `merge.default`, and so is the bare form.
Attribute precedence still decides the result: a `.git/info/attributes` rule,
or a closer `.gitattributes` rule, can keep Weave selected, so verify the
change with `git check-attr merge -- path/to/file.rs`.

`info/attributes` is not always inside a `.git` directory: a linked worktree
has a `.git` file, so resolve the real path with
`git rev-parse --git-path info/attributes` before reading or editing it. That
file is shared by every worktree of the clone, so a clone-local opt-out there
affects the others too; prefer the command-scoped override when they must
remain unaffected. These persistent forms differ from the command-scoped
bypasses below, which leave attribute files untouched.

Use this compact matrix when bypassing Weave after preserving the current
attribute state:

| Setup scope           | Rule location                                                                 | Make `merge` unspecified                                                                                                                                                                                     | Verify, then retry                                                                                                                                                                                                                                                             |
| --------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Any (driver override) | Any attribute source; the rule stays in place                                 | Run Git with `-c merge.weave.driver='git merge-file --zdiff3 --marker-size=%L %A %O %B' -c merge.weave.recursive=text`. `merge` stays `weave`; the named driver is replaced for that command.                | `git -c merge.weave.driver='git merge-file --zdiff3 --marker-size=%L %A %O %B' -c merge.weave.recursive=text config --get merge.weave.driver` must print the `git merge-file` command; rerun the original operation, and every `--continue`, under the same `-c` overrides.    |
| Global                | Configured global attributes file's managed block (or the default path above) | Run Git with `-c core.attributesFile=/dev/null`, and confirm no system attributes file selects Weave (`GIT_ATTR_NOSYSTEM=1` for the command).                                                                | With `GIT_ATTR_NOSYSTEM=1` set when the system file had to be excluded, `git -c core.attributesFile=/dev/null check-attr merge -- path/to/file.py` must report `unspecified`; rerun the original operation with the same arguments and the same environment and `-c` settings. |
| Tracked               | Repository `.gitattributes`                                                   | Preserve the clone-local attributes file, resolved with `git rev-parse --git-path info/attributes`; add a later path-specific `path/to/file.py !merge` there; restore it only after the operation completes. | `git check-attr merge -- path/to/file.py` must report `unspecified`; rerun the original operation with the same arguments.                                                                                                                                                     |
| Clone-local           | The clone's `info/attributes`, shared by its worktrees                        | Preserve the file; add a later path-specific `path/to/file.py !merge`; restore it only after the operation completes.                                                                                        | `git check-attr merge -- path/to/file.py` must report `unspecified`; rerun the original operation with the same arguments.                                                                                                                                                     |

Prefer the driver override for an opted-in repository: it leaves the tracked
and clone-local attribute files untouched and needs no restore step. Use the
attribute rows when the override is unavailable or when the goal is to make Git
report the path as unselected. `-c core.attributesFile=/dev/null` now
suppresses managed user-wide enrolment for one command; it cannot override
tracked, clone-local, or system rules. Because `!merge` leaves the path
unspecified, also confirm that `merge.default` does not select Weave; use a bare
`merge` attribute, or `merge=text` when `merge.text.driver` is unset, or add
`-c merge.default=text` after the same check, to force the built-in text merge.
Whatever the rule, confirm the effective result with
`git check-attr merge -- path`: a higher-precedence source can still select
Weave.

## Preview before changing Git state

```bash
weave preview other-branch
weave preview other-branch --file path/to/file.ts
```

Use preview as an estimate. It reads the merge base, `HEAD`, and the named
branch directly; it does not reproduce every higher-level Git operation or
pre-existing conflicted stage exactly.

## Merge or rebase with observable driver output

Run the ordinary Git operation. During a rebase, remember that Git's labels and
the human meaning of “ours” and “theirs” are easy to misread. Reason from the
desired rebased result and inspect the stage blobs when provenance matters.

Never discard driver stderr. A line such as
`weave: 5 entities auto-resolved (conflict confidence)` identifies a file or
operation whose clean reconstruction deserves scrutiny; it is not proof of
correctness. Weave 0.5.x adds two machine-parseable channels with stable
prefixes, each followed by one space: `weave-warning:` carries one JSON line
per semantic warning, and a merge can exit `0` while emitting these, which is
the "clean with warnings" state; `weave-event:` carries one JSON line per merge
when `WEAVE_EVENT=1` is set. The baseline driver command already sets
`WEAVE_EVENT=1`. On an installation that does not, keep the environment
override command-scoped rather than exporting it across an agent session:

```bash
WEAVE_STDERR=$(mktemp -t weave-rebase.stderr.XXXXXX) || exit 1
env WEAVE_EVENT=1 git rebase origin/main 2>"$WEAVE_STDERR"
REBASE_STATUS=$?
cat -- "$WEAVE_STDERR" >&2

# Fail closed. `grep` exits 1 for "no match" and 2 for "could not read the
# file", so only the latter is a capture failure; an empty capture means the
# driver said nothing, which is itself worth recording rather than assuming.
grep -E 'auto-resolved|^weave-warning: |^weave-event: ' -- "$WEAVE_STDERR"
GREP_STATUS=$?
if [ "$GREP_STATUS" -gt 1 ]; then
  echo 'andon: driver stderr capture unreadable; stop before the audit' >&2
  exit 1
fi
printf 'rebase_status=%s\nevidence=%s\n' "$REBASE_STATUS" "$WEAVE_STDERR"
```

Read the captured stderr after the operation and correlate every auto-resolved,
warning-reported, or event-reported path with the post-operation audit below. A
clean exit and a high-confidence label are evidence about Weave's decision, not
evidence that the merged semantics are correct.

After Git stops on a conflict:

```bash
git status --short
git diff --name-only --diff-filter=U
git ls-files -u -- path/to/file.ts
weave summary path/to/file.ts
weave explain path/to/file.ts
```

In 0.5.x each enhanced marker box opens with a `refused_by:` comment naming the
guard that declined to auto-merge and quoting the disputed lines, and the
driver appends one trailing comment to a conflicted file of the form
`# weave: run 'weave explain <path>' ...` in the file's own comment syntax.
`weave explain` reads the three index stages and reports the guard, confidence,
and hunks per conflicted entity. Remove the trailing comment with the markers;
`weave check` reports it if it is left behind.

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
garbled markers, parse each available stage as well. These commands inspect the
blobs without changing the working file:

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
already contain an earlier silently corrupted replay. A stage must both exist
and parse before it is trusted as a baseline, and the resolved working file
must parse before `git add` records the resolution.

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
is therefore strict: even when the next replay's own output parses, never
accept a structurally invalid result as a safe stage 2 for the next replay.

For agents, a per-replay guard is the default whenever Weave participates in a
multi-commit rebase. Use `git rebase --exec` with the repository's cheapest
credible structural gate, rather than reserving this only for import-relocation
branches.

Run a per-replay guard only on commits trusted to execute as the local user.
`--exec` runs in the replayed tree, so a contributor's `build.rs` or test
harness executes with the operator's credentials; for an untrusted branch, omit
`--exec` and run the same gate on the reviewed result in an isolated checkout.

For Python, for example:

```bash
git rebase --exec 'python -m compileall -q -f path/to/package' origin/main
```

For Rust, `rustfmt` is a useful parser-level tripwire, but it does not
establish workspace type correctness. `cargo check --workspace` is the honest
default when its cost is acceptable:

```bash
git rebase --exec 'cargo check --workspace' origin/main
```

A deliberately cheaper Rust parse guard such as `cargo fmt --all -- --check`
may be used when a workspace check per commit would be prohibitive, but record
that reduced scope explicitly. In every language, the per-replay structural
gate is necessary but not sufficient: the cfg-gated Rust test replacement
recorded in [behaviour.md](references/behaviour.md) parsed, compiled, and
passed tests. Do not rely solely on the full test suite after the final commit.

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
   to an intended branch change from
   `git diff "$BRANCH_BASE".."$OLD_HEAD" -- <path>` or to a named, reviewed
   conflict-resolution decision. An unexplained deletion is an andon event even
   if the file compiles and tests pass.
3. **Look for newly repeated blocks.** Scan each resulting text file for a
   multi-line block repeated more often at `HEAD` than at `TARGET`, then
   inspect every new repetition. This catches duplicated re-export/import
   blocks and similar reconstruction artefacts that may remain syntactically
   valid.

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
`weave check`, run it while Git still holds the three-way context and before
accepting the result:

```bash
weave --version
weave check --help >/dev/null
weave check
```

`weave check` with no arguments verifies the working tree against the merge
inputs and can report leftover markers, including its own trailing comment,
lines present on both sides that went missing, content repeated more often than
either side supplied, and dangling references. Exit `0` means nothing was found
and exit `1` means findings.

Know what the no-argument mode can see. In 0.5.1 it finds a three-way scope
only when `MERGE_HEAD` exists or `HEAD` is a merge commit. A rebase or
cherry-pick stop has `REBASE_HEAD` or `CHERRY_PICK_HEAD` but no `MERGE_HEAD`,
and a completed rebase leaves a single-parent `HEAD`, so in those states the
command prints a sentence containing `NOTHING WAS CHECKED` and exits `0`. That
is an explicit "unchecked" state, never a pass. Confirm the scope before
running it and fail closed on the sentence:

```bash
if ! git rev-parse -q --verify MERGE_HEAD >/dev/null; then
  echo 'weave check: no MERGE_HEAD; working-tree mode has no three-way scope' >&2
fi
WEAVE_CHECK_OUT=$(mktemp -t weave-check.XXXXXX) || exit 1
weave check | tee -- "$WEAVE_CHECK_OUT"
# Copy the array in one step: any later command, even an assignment, resets it.
PIPE_STATUSES=("${PIPESTATUS[@]}")
CHECK_STATUS=${PIPE_STATUSES[0]}
TEE_STATUS=${PIPE_STATUSES[1]}
if [ "$TEE_STATUS" -ne 0 ]; then
  echo 'andon: weave check output was not captured; stop before the audit' >&2
  exit 1
fi
if grep -q 'NOTHING WAS CHECKED' -- "$WEAVE_CHECK_OUT"; then
  echo 'andon: weave check verified nothing; record unchecked, not clean' >&2
  exit 1
fi
printf 'weave_check_status=%s\nevidence=%s\n' "$CHECK_STATUS" "$WEAVE_CHECK_OUT"
if [ "$CHECK_STATUS" -ne 0 ]; then
  echo 'andon: weave check reported findings or failed; stop before accepting' >&2
  exit "$CHECK_STATUS"
fi
```

The wrapper keeps the evidence file and then propagates the checker's own
status: `1` for findings, `127` for a missing `weave`, and any other non-zero
value for a checker failure. A workflow that gates on the wrapper's exit status
therefore cannot accept a result the checker rejected.

For a merge, run it after resolving and before `git commit`, or immediately
after the merge commit while `HEAD` still has two parents. For a rebase, run it
per file while the conflict stop still has unmerged index stages, or use
`weave check --base <rev> --ours <rev> --theirs <rev>`; that mode runs a
cross-file binding pass between two revisions and emits findings JSON, so it
describes a three-input comparison rather than the exact resolved tree being
accepted. No 0.5.1 mode verifies a completed rebase's tree. Treat findings or
an unsupported/missing checker as explicit evidence states; do not translate
"checker unavailable" or "nothing checked" into success.

When the Weave MCP server is available, the read-only `weave_check` tool is the
agent-facing equivalent. The estate baseline does not provision `weave-mcp`;
use the tool only where that integration is established, and retain its
findings with the same candidate identity. Neither interface replaces the
target/branch semantic audit above.

As a read-only verifier, `weave check` or MCP `weave_check` must not mutate the
working tree. Unexpected mutation is an andon event.

## Interpret driver outcomes

- Exit `0`: Weave wrote the result to `%A` and considers it clean. This is not
  semantic acceptance.
- Exit `1`: Weave wrote a partially merged result with conflicts to `%A`; Git
  keeps the path unmerged for manual or agent resolution.
- Exit `2`: invocation, input, output, or binary-file failure. Do not treat
  this as a semantic conflict; inspect stderr and repair the
  driver/configuration.

The Git driver uses enhanced seven-character markers with entity names and
hints. The `-l` option selects standard diff3-compatible markers and is meant
for tools such as Jujutsu; Git's positional `%L` does not disable enhanced
markers.

Set `WEAVE_VERBOSE=1` to print per-file statistics. Prefer command-scoped
`env WEAVE_VERBOSE=1 ...` rather than a session-wide export. Other 0.5.x
environment switches:

- `WEAVE_MAX_DUPLICATES=<n>` sets how often one name may repeat in a file
  before the merge takes the line-level route; the default is 10.
- `WEAVE_STATS=1` re-enables the lifetime counters in `~/.weave/stats.json`;
  0.5.x no longer records them by default.
- `WEAVE_AUDIT=1` and `WEAVE_FINDINGS=1` write sidecar files into the working
  tree beside the merged path. Leave both unset for unattended work; the
  baseline does not enable them, and an unexpected untracked file would
  contaminate recovery evidence.

`WEAVE_TIMEOUT` and the five-second entity-merge watchdog belong to 0.3.x only.
Version 0.5.x removed the watchdog thread, so a slow merge no longer falls back
to `git merge-file` on its own; setting `WEAVE_TIMEOUT` there has no effect.

## Andon triggers

Stop advancing the branch, preserve the current state, and establish the
candidate again when any of these occurs:

- Weave, a parser, compiler, formatter, linter, test, or `weave check` reports a
  failure after a replay;
- a target-only path differs from `TARGET` after the operation;
- a branch-touched path contains an unexplained deletion against `TARGET`;
- a repeated-block scan finds a new duplication that cannot be justified;
- driver stderr records an auto-resolution or a `weave-warning:` line whose
  affected path has not yet been audited;
- `weave check` reports `NOTHING WAS CHECKED` and the receipt would otherwise
  record the result as clean;
- the installed `weave` and `weave-driver` versions disagree unexpectedly, or
  the required post-merge checker is unavailable;
- a host selects Weave unexpectedly: outside the managed defaults for `rs`,
  `py`, `ts`, and `tsx`, for a refused category such as Markdown, data, or a
  lock file, or from a source the receipt has not classified; or it resolves a
  driver on `PATH` that differs from the canonical `~/.cargo/bin` binary;
- source or compiled artefact provenance disagrees;
- recovery evidence omits staged, unstaged, or intended untracked work;
- the rebase changes the candidate head while old gate/review evidence is still
  being treated as current.

An andon event is not an instruction to guess a repair. Preserve evidence,
identify the authoritative inputs, and either rerun with built-in Git merging
or investigate the specific reconstruction before continuing.

## Recover safely

Before rerunning or replacing a result, preserve it or inspect the index
stages. Commands that recreate conflict markers can overwrite Weave's partially
merged `%A` file. Do not perform a destructive abort until any manual
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

For a retry, use the command-scoped driver override for the rebase, merge, or
cherry-pick. It replaces the named driver for the whole operation whichever
attribute source selects Weave, including a tracked rule that a replayed commit
introduces, so it does not depend on inspecting a representative path. Repeat
the original operation's arguments, including any `--onto` boundary, and add
only the `-c` overrides: aborting an `--onto` replay and retrying with a plain
`rebase "$TARGET"` can replay inherited parent commits. Carry an original
`--exec` guard forward only when the replayed commits are trusted to execute as
the local user, on the same condition as the first attempt; otherwise omit it
and run the checks on the reviewed result. Confirm
`git config --get-regexp '^merge\.text\.'` prints nothing before using the
`merge.weave.recursive=text` override.

```bash
# Only after recovery evidence is verified. Use the abort for an interrupted
# operation, or the reset for one a clean driver exit allowed to complete.
git rebase --abort
git reset --hard "$OLD_HEAD"

# An originally plain rebase on the recorded target:
git -c merge.conflictStyle=zdiff3 \
    -c merge.weave.driver='git merge-file --zdiff3 --marker-size=%L %A %O %B' \
    -c merge.weave.recursive=text \
    rebase "$TARGET"

# An --onto replay keeps its recorded boundaries, and its guard only for
# commits trusted to execute as the local user:
git -c merge.conflictStyle=zdiff3 \
    -c merge.weave.driver='git merge-file --zdiff3 --marker-size=%L %A %O %B' \
    -c merge.weave.recursive=text \
    rebase --onto "$TARGET" "$OLD_BASE" --exec '<original guard>'

# For a merge, abort it or reset to "$OLD_HEAD", then retry with the same
# original arguments resolved against the recorded target:
git merge --abort
git -c merge.weave.driver='git merge-file --zdiff3 --marker-size=%L %A %O %B' \
    -c merge.weave.recursive=text \
    merge <same-original-arguments>

# For a cherry-pick, likewise:
git cherry-pick --abort
git -c merge.weave.driver='git merge-file --zdiff3 --marker-size=%L %A %O %B' \
    -c merge.weave.recursive=text \
    cherry-pick <same-original-arguments>
```

Carry the same overrides on each `git rebase --continue`, each
`git cherry-pick --continue`, and any authorized `--skip` that resumes a
replay: every continuation starts a new merge, and Git reads the driver
configuration again.

To diagnose why Weave ran at all,
`git -c core.attributesFile=/dev/null check-attr merge -- path` shows what the
working tree selects once the user attributes file is ignored, and
`git config --get merge.default` shows the fallback for an unspecified path.
Neither check sees a `.gitattributes` rule that a replayed commit has not yet
delivered, which is why the override, not the pre-rebase check, is the
safeguard for the whole operation.

This override preserves unrelated repository merge rules: it replaces only the
`merge.weave` driver command, so a path still selected as `merge=weave` in
tracked or clone-local attributes runs Git's text merge through the override. A
later path-specific `!merge` line in the clone's `info/attributes`, resolved
with `git rev-parse --git-path info/attributes`, outranks every attribute
source for that path, so it remains the attribute-level bypass when the goal is
for Git to report the path as unselected.

The override assumes text input. `git merge-file` looks for NUL only in the
first 8,000 bytes of each input, so a file with a NUL in that window is refused
(`Cannot merge binary files`) and exits non-zero, and Git reports a merge error
instead of leaving the ordinary binary conflict that running without Weave
would produce. A NUL beyond that window is not detected and can pass into a
line merge, so do not rely on this check to classify a large file. For a path
that may be binary, keep the attribute-level route instead: when Weave selected
it only through the managed user-wide block, the narrower prefix leaves it to
native Git, or add `path/to/file -merge` to the clone-local attributes file to
select Git's built-in binary driver for that path, which leaves the conflict
for the operator to resolve.

Remove repository configuration with `weave unsetup`. It removes the local
`merge.weave` section and Weave rules from `.gitattributes` and
`.git/info/attributes`; it does not remove global setup.
