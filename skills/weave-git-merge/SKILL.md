---
name: weave-git-merge
description: Use and troubleshoot Weave as an entity-aware Git merge driver during merges, rebases, cherry-picks, and conflict resolution. Use when configuring Weave, previewing a merge, checking whether Git will invoke it, interpreting Weave conflict markers or exit behaviour, detecting structurally corrupt clean results, bypassing Weave safely, recovering from driver failures, or explaining what Weave actually resolves versus when it falls back to line-level merging.
---

# Use Weave with Git

Treat Weave as a per-file Git merge driver, not as a replacement for `git merge`
or `git rebase`. Git selects it through attributes and invokes
`weave-driver %O %A %B %L %P` for each selected path.

Read [behaviour.md](references/behaviour.md) before diagnosing a surprising
result or deciding whether an unresolved file is safe to edit.

Every shell example below requires Bash. This matters for the stage-validation
commands in particular: `set -o pipefail` is a Bash builtin option with no
POSIX `sh` equivalent, so running those commands under `sh` silently drops the
guard and lets a failing `git show` pass as success.

## Configure it

Choose one scope deliberately:

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

Do not assume setup succeeded merely because `.gitattributes` contains a rule.
Verify both selection and command:

```bash
git check-attr merge -- path/to/file.ts
git config --show-origin --get merge.weave.driver
command -v weave-driver
weave-driver --version
```

Expect `git check-attr` to report `merge: weave`. `git check-attr -a -- path`
reports only effective attribute values, not which source supplied them.
Inspect `.git/info/attributes`, applicable `.gitattributes` files, and the
configured global attributes file directly (or the default
`$XDG_CONFIG_HOME/git/attributes` / `$HOME/.config/git/attributes` when no file
is configured). Locate an explicitly configured file with
`git config --path --get core.attributesFile`. That command prints nothing and
exits non-zero when the setting is absent, which means the default path applies,
not that no global rule exists; read the default path before concluding that
Weave was selected somewhere else.

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

## Merge or rebase normally

Run the ordinary Git operation. During a rebase, remember that Git's labels
and the human meaning of “ours” and “theirs” are easy to misread. Reason from
the desired rebased result and inspect the stage blobs when provenance matters.

After Git stops:

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

## Guard a multi-commit rebase

A cleanly returned but corrupted early replay becomes an input to later
replays. In a later conflict it may appear as stage 2, so reconstruction damage
can compound before an end-of-rebase test ever runs.

For a branch that relocates or reorders imports, or contains "repair after
rebase" commits, either bypass Weave for the whole operation or run a cheap
syntax or import check after every replayed commit. Git's `--exec` option makes
that check stop the rebase at the first bad intermediate result, for example:

```bash
git rebase --exec 'python -m compileall -q -f path/to/package' origin/main
```

Replace the example with the repository's cheapest suitable structural gate.
Do not rely solely on the full test suite after the final commit.

## Interpret driver outcomes

- Exit `0`: Weave wrote the result to `%A` and considers it clean.
- Exit `1`: Weave wrote a partially merged result with conflicts to `%A`; Git
  keeps the path unmerged for manual or agent resolution.
- Exit `2`: invocation, input, output, or binary-file failure. Do not treat
  this as a semantic conflict; inspect stderr and repair the driver/configuration.

The Git driver uses enhanced seven-character markers with entity names and
hints. The `-l` option selects standard diff3-compatible markers and is meant
for tools such as Jujutsu; Git's positional `%L` does not disable enhanced
markers.

Set `WEAVE_VERBOSE=1` to print per-file statistics. Set `WEAVE_TIMEOUT` to a
whole number of seconds only when the default five-second entity-merge timeout
is unsuitable. A timeout falls back to `git merge-file`; it does not abort the
overall driver invocation.

## Recover safely

Before rerunning or replacing a result, preserve it or inspect the index
stages. Commands that recreate conflict markers can overwrite Weave's
partially merged `%A` file.

If Weave was selected but never ran, check attribute precedence, the exact
config scope, executable discovery, and quoting of a driver path containing
spaces. If the driver returned `2`, use its stderr to distinguish missing
inputs, binary detection, and write failure.

If Weave returned `0` with structurally broken output, abort the operation and
rerun the whole operation with the built-in merge machinery. For a global
setup, first verify that ignoring the user attributes file makes `merge`
unspecified for a representative affected path, then use the same override for
the rebase, merge, or cherry-pick:

```bash
git rebase --abort
git -c core.attributesFile=/dev/null check-attr merge -- path/to/file.py
# path/to/file.py: merge: unspecified
git -c core.attributesFile=/dev/null rebase origin/main

# For an in-progress merge, abort and retry with the same original arguments:
git merge --abort
git -c core.attributesFile=/dev/null merge <same-original-arguments>

# For an in-progress cherry-pick, abort and retry with the same original arguments:
git cherry-pick --abort
git -c core.attributesFile=/dev/null cherry-pick <same-original-arguments>
```

This override disables only the user attributes file for those commands.
Repository-tracked `.gitattributes` and `.git/info/attributes` still apply, so
it preserves unrelated repository merge rules. It is suitable when
`weave setup --global` supplied the `merge=weave` rule and no higher-precedence
source selects Weave. For tracked or clone-local setup, use the corresponding
matrix row above; `/dev/null` alone cannot override those rules.

Remove repository configuration with `weave unsetup`. It removes the local
`merge.weave` section and Weave rules from `.gitattributes` and
`.git/info/attributes`; it does not remove global setup.
