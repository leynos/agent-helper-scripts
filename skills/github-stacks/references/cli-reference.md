# `gh stack` CLI reference

Condensed from the GitHub Docs reference (public preview, retrieved
2026-07-31):
<https://docs.github.com/en/pull-requests/reference/stacked-prs-cli-commands>

Install: `gh extension install github/gh-stack` (requires `gh` 2.0+; uses
`gh` authentication).

## Stack management

### `gh stack init [flags] [branches...]`

Initialize a new stack. Interactive with no arguments; with branch names,
existing branches are adopted and missing ones created. Enables `git rerere`
automatically.

| Flag | Description |
| ---- | ----------- |
| `-b, --base <branch>` | Trunk branch (defaults to the repository default branch) |

### `gh stack add [flags] [branch]`

Create a branch at HEAD, add it to the top of the stack, and check it out.
Must be run from the topmost branch. With `-m` and no branch name, the name
is auto-generated in date-slug form (`03-24-add_login`).

| Flag | Description |
| ---- | ----------- |
| `-A, --all` | Stage all changes, including untracked. Requires `-m`. |
| `-u, --update` | Stage tracked files only. Requires `-m`. |
| `-m, --message <string>` | Commit with this message before branching |

`-A` and `-u` are mutually exclusive.

### `gh stack view [flags]`

Show branches, ordering, PR links, and latest commit. Paged via
`GIT_PAGER`/`PAGER` (default `less -R`).

| Flag | Description |
| ---- | ----------- |
| `-s, --short` | Branch names only |
| `--json` | JSON output |

### `gh stack checkout [<stack-number> | <pr-number> | <pr-url> | <branch>]`

Check out a stack. A bare number is tried as a stack or PR number first,
then as a branch name. Remote stacks are fetched and set up locally;
mismatched compositions prompt for resolution. Branch names resolve against
local stacks only. With no arguments (interactive terminal), opens a
searchable picker of local and remote stacks (fully merged stacks omitted;
selecting a remote-only stack clones it).

### `gh stack modify [flags]`

Interactive TUI to restructure the stack. Staged changes apply on `Ctrl+S`.
Cannot modify branches from merged PRs. Reordering and structural changes
cannot mix in one session.

Preconditions: active stack checked out; clean working tree; no rebase in
progress; no PR queued for merge; linear history.

| Key | Operation |
| --- | --------- |
| `x` | Drop branch and its commits (branch and PR preserved) |
| `d` | Fold into the branch below |
| `u` | Fold into the branch above |
| `i` / `I` | Insert empty branch below / above |
| `Shift+↓` / `Shift+↑` | Reorder down / up |
| `r` | Rename |
| `z` | Undo last staged action |

| Flag | Description |
| ---- | ----------- |
| `--continue` | Continue after resolving apply-phase conflicts |
| `--abort` | Restore the pre-modify snapshot (also works after a crash) |

After modifying a submitted stack, run `gh stack submit` to replace the old
stack on GitHub.

### `gh stack unstack [<stack-number>] [flags]` (alias: `gh stack delete`)

Unstack on GitHub and remove local tracking. No argument targets the active
stack; a stack number works from anywhere (remote API operation). Merged,
merging, and queued PRs cannot be removed and remain in the stack; the stack
dissolves only when every PR is removed.

| Flag | Description |
| ---- | ----------- |
| `--local` | Remove local tracking only, keep the stack on GitHub |

## Remote operations

### `gh stack submit [flags]`

Push all branches, create or update PRs, and create/extend the stack on
GitHub. Interactive full-screen editor: left panel selects branches
(`Ctrl+X` toggles; dependencies cascade), right panel drafts title,
description (pre-filled from the PR template or commits; `$EDITOR` escape),
and draft state; `Ctrl+S` submits; `Ctrl+B` links existing PRs into a stack;
`o` opens a locked branch's PR. If every PR has merged, starts a new stack
from the trunk. Editor defaults new PRs to ready-for-review; `--auto`
defaults them to drafts.

| Flag | Description |
| ---- | ----------- |
| `--auto` | Skip the editor; auto-generate titles (new PRs are drafts) |
| `--open` | Create/mark PRs as ready for review |
| `--remote <name>` | Remote to push to |

### `gh stack sync [flags]`

Single-command synchronization: fetch → reconcile remote stack (remote-ahead
updates pulled automatically; true divergence prompts, or aborts
non-interactively) → fast-forward trunk → cascading rebase (only if trunk
moved; conflicts restore all branches and defer to `gh stack rebase`) → push
(`--force-with-lease` if rebased) → sync PR state → link the stack on GitHub
(2+ PRs; never opens PRs) → prune prompt.

Divergence options (interactive): use remote as source of truth (requires
clean working tree); delete the stack object on GitHub (recreate with
`submit`); cancel.

| Flag | Description |
| ---- | ----------- |
| `--remote <name>` | Remote to fetch from and push to |
| `--prune` | Delete local branches for merged PRs |

### `gh stack rebase [flags] [branch]`

Fetch, then cascade-rebase each branch onto the tip of the layer below, from
the trunk upward. Merged-PR branches switch to `--onto` replay
automatically. Conflicts pause the operation and print conflicted files with
line numbers.

| Flag | Description |
| ---- | ----------- |
| `--downstack` | Only trunk → current branch |
| `--upstack` | Only current branch → top |
| `--no-trunk` | No fetch, no trunk rebase; stack branches only |
| `--continue` | Continue after resolving conflicts |
| `--abort` | Restore all branches to the pre-rebase state |
| `--remote <name>` | Remote to fetch from |
| `--committer-date-is-author-date` | Preserve author date as committer date (alias `--preserve-dates`) |

### `gh stack push [flags]`

Push active branches (excluding merged/queued) in one `git push` with
per-branch `--force-with-lease`. Not atomic: passing leases update even if
another branch is rejected — fix and re-run. Does not touch PRs.

| Flag | Description |
| ---- | ----------- |
| `--remote <name>` | Remote to push to |

### `gh stack link [flags] <stack-number | branch-or-pr> <branch-or-pr> [...]`

Create or update a stack on GitHub with no local tracking (for Jujutsu,
Sapling, git-town, etc.). Arguments in bottom-to-top order; branches are
pushed automatically; missing PRs are created with correct base chaining and
wrong bases are corrected. Additive only. A numeric first argument matching
an existing stack appends the remaining arguments to that stack's top.

| Flag | Description |
| ---- | ----------- |
| `--base <branch>` | Base for the bottom of a new stack (ignored when appending) |
| `--open` | Mark new and existing PRs ready for review |
| `--remote <name>` | Remote to push to |

### `gh stack merge [<stack-number> | <pr-number>] [flags]`

Merge every PR up to and including the chosen one, bottom-up, as a single
all-or-nothing operation. No argument uses the active stack; a stack number
merges remotely; a PR number merges up to that PR. Each PR must be open and
not a draft; branch protection is evaluated at merge time and cannot be
bypassed. With a merge queue, the selection is enqueued together (method
flags ignored; a large stack may split across consecutive merge groups —
groups may exceed their maximum size by up to 50% to keep a stack together).

| Flag | Description |
| ---- | ----------- |
| `--merge-method <method>` | `merge`, `squash`, or `rebase` |
| `--merge` / `--squash` / `--rebase` | Method shorthands |
| `-y, --yes` | No confirmation prompt |

## Navigation

All navigation clamps to stack bounds. Bottom = closest to trunk; top =
furthest.

| Command | Effect |
| ------- | ------ |
| `gh stack switch` | Interactive branch picker (requires TTY) |
| `gh stack up [n]` | Move `n` layers away from trunk (from trunk, moves to the first layer) |
| `gh stack down [n]` | Move `n` layers toward trunk |
| `gh stack top` | Check out the topmost branch |
| `gh stack bottom` | Check out the bottommost branch |
| `gh stack trunk` | Check out the trunk branch |

## Utilities

| Command | Effect |
| ------- | ------ |
| `gh stack alias [name] [--remove]` | Install a wrapper script in `~/.local/bin/` (default `gs`). Not automated on Windows. |
| `gh stack feedback [title]` | Open a feedback discussion on github/gh-stack |

## Environment variables

| Variable | Values | Description |
| -------- | ------ | ----------- |
| `GH_STACK_THEME` | `auto` (default), `light`, `dark` | Force the palette when the terminal does not report its background (some SSH/tmux setups) |

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | Success |
| 1 | Generic error |
| 2 | Not in a stack, or stack not found |
| 3 | Rebase conflict |
| 4 | GitHub API failure |
| 5 | Invalid arguments or flags |
| 6 | Disambiguation required (branch belongs to multiple stacks) |
| 7 | Rebase already in progress |
| 8 | Stack locked by another process |
| 9 | Stacked pull requests not enabled for this repository |
| 10 | Modify session interrupted; recovery required |

## Website equivalents

- **Create**: set each PR's base to the branch below and choose **Create
  stack**; or accept the recommendation banner on an eligible PR chain; or
  **Add to stack** from a stack PR's header.
- **Rebase stack** button (merge box): server-side cascading rebase +
  force-push. Server-side commits are **not signed** — repositories
  requiring signed commits must rebase locally.
- **Unstack**: removes open, draft, and closed PRs from the stack; merged
  and queued PRs remain.

## Further reading

- Quickstart: <https://docs.github.com/en/pull-requests/get-started/stacked-prs-quickstart>
- Creating: <https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/creating-stacked-pull-requests>
- Managing: <https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/managing-stacked-pull-requests>
- Troubleshooting: <https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-stacked-pull-requests>
- Copilot/agent skill: `gh skill install github/gh-stack`
