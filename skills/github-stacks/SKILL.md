---
name: github-stacks
description: >
  Create, navigate, and manage stacks of branches and pull requests with the
  `gh stack` GitHub CLI extension (GitHub's native stacked pull requests,
  public preview). Use whenever the user wants to split work into stacked or
  dependent pull requests, or mentions "stacked PRs", "gh stack", "stack of
  branches", "cascading rebase", "stack sync", "unstack", or asks to submit,
  rebase, restructure, or merge a stack. Also use when an existing chain of
  PRs (each based on the branch below) should be linked into a stack, or when
  branches managed by other tools (Jujutsu, Sapling, git-town) need linking
  into a stack of PRs. Covers the full lifecycle: init, add, submit, sync,
  rebase, modify, merge, and conflict recovery.
---

# GitHub Stacked Pull Requests (`gh stack`)

Stacked pull requests split a large change into a chain of small, dependent
pull requests. Each branch ("layer") builds on the one below it; each PR's
base is the branch beneath, so reviewers see only that layer's diff. GitHub
links the PRs into a first-class stack object with a stack map in the merge
box.

**Status**: public preview — behaviour is subject to change. Requires GitHub
CLI (`gh`) 2.0+ and stacked PRs enabled for the repository (exit code 9 means
they are not).

## Hard constraints

- All branches must live in the **same repository** — cross-fork stacks are
  not supported.
- A stack must have a **linear history** (no merge commits, no diverged
  branches) before it can merge.
- A PR in a stack merges only when it **and every PR below it** meet all
  merge requirements.
- Merged, merging, and queued PRs can never be removed from a stack.
- Merge requirements cannot be bypassed when merging stacked PRs.

## Installation

```shell
gh extension install github/gh-stack
gh stack alias        # optional: installs `gs` wrapper in ~/.local/bin/
```

Uses existing `gh` authentication (`gh auth login` if needed).

## Routing guide

| Task | Approach |
| ---- | -------- |
| Start a new stack | `gh stack init <branch>` (see workflow below) |
| Add a layer on top | `gh stack add <branch>` from the topmost branch |
| Open/update PRs on GitHub | `gh stack submit` |
| Daily catch-up (fetch, rebase, push, prune) | `gh stack sync --prune` |
| Fix something in a lower layer | See "Editing a lower layer" |
| Trunk moved / history not linear | `gh stack rebase`, then `gh stack push` |
| Reorder, rename, fold, drop, insert branches | `gh stack modify` (interactive TUI) |
| Merge some or all of the stack | `gh stack merge` |
| Link pre-existing PRs/branches into a stack | `gh stack link` (no local tracking) |
| Move between layers | `up` / `down` / `top` / `bottom` / `trunk` / `switch` |
| Check out someone else's stack | `gh stack checkout <stack-or-pr-number>` |
| Dissolve a stack | `gh stack unstack` (`--local` to keep it on GitHub) |
| Full flags, exit codes, env vars | `references/cli-reference.md` |

## Core workflow

```shell
# 1. Start the stack: creates and checks out the first branch off the trunk
gh stack init auth-layer            # --base develop to override the trunk

# 2. Commit work on this layer
git add . && git commit

# 3. New layer on top (must be run from the topmost branch)
gh stack add api-routes
# ... commit ...
gh stack add frontend
# ... commit ...

# 4. Push all branches and create the linked PRs
gh stack submit
```

`gh stack init` enables `git rerere` automatically so conflict resolutions
are remembered across rebases. Passing multiple branch names to `init` adopts
existing branches and creates missing ones — this is also the recovery path
after unstacking.

`gh stack add` can stage and commit in one step: `gh stack add -Am "Add
login"` stages everything, commits, and auto-generates a date-slug branch
name (e.g. `03-24-add_login`). `-u` stages tracked files only; `-A` and `-u`
are mutually exclusive and both require `-m`.

### Submitting

`gh stack submit` pushes all branches, creates a PR per branch with the
correct base chaining, and links them into a stack on GitHub. Interactively
it opens a full-screen editor (select branches, draft titles/descriptions,
toggle draft state; `Ctrl+S` submits). Non-interactive contexts and `--auto`
skip the editor; with `--auto`, new PRs are created as **drafts** unless
`--open` is passed. If all PRs in a stack have merged, `submit` starts a
fresh stack rooted at the trunk for the unmerged branches.

For agents: prefer `gh stack submit --auto` (add `--open` if the PRs should
be ready for review), since the interactive editor needs a TTY.

## Editing a lower layer

Make the change in the branch it belongs to, not the top:

```shell
gh stack down                # or: gh stack checkout <branch>
git add . && git commit
gh stack rebase --upstack    # cascade the change into the layers above
gh stack push                # --force-with-lease per branch
gh stack top                 # return to where you were
```

## Keeping in sync

`gh stack sync` in one command: fetch → reconcile the remote stack →
fast-forward trunk → cascading rebase (only if trunk moved) → push → sync PR
state → link the stack → prune prompt. It never opens PRs (that is
`submit`'s job). Safe in automation: a clean remote-ahead update (PRs added
on GitHub on top of the local stack) is pulled down without prompting; a
genuine divergence aborts the sync in non-interactive terminals without
pushing anything.

After a bottom PR merges: `gh stack sync --prune` fast-forwards trunk,
rebases the remainder, and deletes local branches for merged PRs.

If sync detects a rebase conflict it restores all branches untouched and
tells you to run `gh stack rebase` interactively.

**Diverged stacks** (neither local nor remote is a clean prefix of the
other): interactive sync offers three options — adopt the remote as source
of truth, delete the stack object on GitHub (then recreate with `gh stack
submit`, running `gh stack modify` first if restructuring), or cancel.

## Rebasing and conflicts

`gh stack rebase` fetches, then rebases each branch onto the tip of the one
below, from the trunk upward. `--downstack` limits it to trunk→current,
`--upstack` to current→top, `--no-trunk` skips fetching and the trunk rebase.
Branches whose PR has merged are replayed with `--onto` automatically.

On conflict (exit code 3), the rebase pauses and lists conflicted files:

```shell
# resolve the <<<<<<< markers, then:
git add .
gh stack rebase --continue
# or restore everything to the pre-rebase state:
gh stack rebase --abort
```

The website's **Rebase stack** button performs the same cascade server-side,
but those commits are **not signed** — if the repository requires signed
commits, always rebase locally with `gh stack rebase` and push with
`gh stack push`.

## Restructuring (`gh stack modify`)

Interactive TUI for drop (`x`), fold down/up (`d`/`u`), insert (`i`/`I`),
rename (`r`), reorder (`Shift+↑/↓`), undo (`z`). Changes are staged and
applied together on `Ctrl+S`. Reordering and structural changes cannot mix
in one session. Preconditions: active stack checked out, clean working tree,
no rebase in progress, no PR queued, linear history. Recovery:
`--continue` after resolving an apply-phase conflict, `--abort` to restore
the pre-modify snapshot (works even after a crash). After modifying, run
`gh stack submit` to push and recreate the stack on GitHub.

`gh stack modify` needs a TTY. The non-interactive alternative is:
`gh stack unstack` → `gh stack init <branches in new order>` →
`gh stack submit`.

## Merging

```shell
gh stack merge               # interactive: choose PRs, method, confirm
gh stack merge 42            # merge everything up to and including PR 42
gh stack merge 7             # merge stack number 7 (pure remote operation)
gh stack merge --yes --squash
```

Merging is **all-or-nothing** for the selected range: PRs merge bottom-up,
and if any cannot merge, none do (pre-checked; a mid-merge failure leaves
already-merged PRs landed and the rest open — fix and retry). Each selected
PR must be open and not a draft. With a merge queue, the stack is enqueued
together (method flags are ignored; the queue may split a large stack across
consecutive merge groups).

## Interop with other tools (`gh stack link`)

For branches managed with Jujutsu, Sapling, git-town, etc. — creates or
updates the stack on GitHub with **no local tracking**:

```shell
gh stack link feat-a feat-b feat-c     # bottom → top order
gh stack link 7 48 feature-ui          # append to existing stack number 7
```

Branches are pushed automatically; missing PRs are created with correct base
chaining; wrong bases on existing PRs are corrected. Updates are additive
only — `link` never removes PRs from a stack.

## Troubleshooting quick hits

- **Merge blocked**: check reviews/checks on the PR *and every PR below it*,
  and that history is linear — `gh stack rebase && gh stack push` (or the
  **Rebase stack** button) restores linearity.
- **Closed a mid-stack PR**: everything above it is blocked. Unstack (from
  the website or `gh stack unstack`), restructure, and recreate.
- **PR ejected from the merge queue**: all PRs above it are ejected too;
  re-add the stack once fixed.
- **Exit codes worth branching on**: 2 not in a stack, 3 rebase conflict,
  6 branch belongs to multiple stacks, 9 stacked PRs not enabled for the
  repository. Full table in `references/cli-reference.md`.

## Agent guidance

- Prefer `--auto`, `--yes`, and explicit branch-name arguments; `submit`
  (editor), `modify`, `switch`, and no-argument `checkout` need a TTY.
- Run `gh stack view --json` to inspect stack state programmatically.
- `sync` is safe to run unattended; it aborts cleanly on divergence.
- Never `git push --force` stack branches by hand — use `gh stack push`,
  which applies per-branch `--force-with-lease`.
