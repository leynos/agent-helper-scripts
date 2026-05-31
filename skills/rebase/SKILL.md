---
description: Rebase the current branch onto origin/main, resolve conflicts carefully, validate, and commit.
---

Please rebase this branch onto `origin/main`.

Each time you encounter a conflict, examine the situation carefully with the
tools you have available and formulate a plan before acting.

Git has been configured to use `zdiff3` for three-way merge. Keep pertinent
changes for both branches. In the case of a conflict, try to identify a
solution that preserves the purpose of the current branch whilst incorporating
any improvements that have been committed in `main` if possible. Do your best
to understand the "why" of a change, and use your best judgement to resolve
situations where a merge will result in breakage.  For packaging lock files,
use the changes on the main branch only, then rebuild the lock file following
merge. Run `make check-fmt`, `make test`, `make typecheck`, and `make lint` to
validate the merge.

Note that not all projects have a `typecheck` target. If this is the case, do
not be alarmed. There is no need to report this.

Following the rebase, validate and commit any outstanding changes.
