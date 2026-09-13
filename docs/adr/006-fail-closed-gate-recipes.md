# ADR 006 — Gate recipes discover their own file list

**Status:** Accepted **Date:** 2026-09-12

## Context

Estate repositories lint Markdown, validate Mermaid diagrams, and check
spelling through Makefile recipes copied from this repository's template. The
recipes piped a producer into the gate:

```make
markdownlint:
	find . -type f -name '*.md' -not -path './target/*' -print0 | xargs -0 -r markdownlint-cli2
```

A pipeline reports the status of its last command. `.SHELLFLAGS` is unset, so
no recipe runs under `pipefail`, and `xargs -r` exits zero when it receives no
input. A producer that fails, or that matches nothing because the checkout is
shallow, the branch is dead, or the paths root is wrong, therefore leaves the
gate green having examined no file. A read-only sample of 41 estate
repositories found the shape in 39 of them; the same shape reached the spelling
gate's `git ls-files -z '*.md' | xargs -0 -r ... typos` and the Mermaid
recipe's `find ... | xargs -0 -r nixie`.

The failure is silent in the direction that matters. A gate that examines no
file and a gate that examines a clean tree report the same status, so anything
that weakens the producer makes the pipeline greener.

## Decision

Replace each recipe with one command that lists the files itself, raises when
that list is empty, and invokes the tool once over the whole list. This
repository ships the command as `scripts/gate_runner_cli.py`; consumers
regenerate their recipes from the template, so the fix lands once here.

Discovery lives in `scripts/gate_discovery.py` and fails closed. A producer
that exits non-zero raises with the producer's own diagnostic, and a producer
that succeeds with no output raises rather than handing a tool an empty list.
Both name the gate. The spelling gate reads every Git-tracked file; the
Markdown and Mermaid gates walk the tree, pruning build, cache and vendored
directories.

The commands live in `scripts/gate_runner.py`, apart from the Cyclopts front
end that reaches them, because that module imports nothing beyond the standard
library. Tests then drive a gate with a command double standing in for its
tool, and assert what the recipes could not: that a failing or empty producer
fails the gate before the tool is invoked, that the tool receives the whole
list in one invocation, and that the tool's status is the gate's status.

Where a repository has not yet regenerated its recipes, the interim guard is
`set -o pipefail` at the head of the recipe, or
`.SHELLFLAGS := -eo pipefail -c` for the file. The guard is not the fix: it
catches a producer that fails, but not one that succeeds with an empty list,
which is how a glob that matches nothing reads as a pass.

Two glob-shaped gaps remain outside this decision. The `markdownlint` wrapper
shipped to consumers widens a bare invocation to `**/*.md`, which can match no
file while `markdownlint-cli2` still reports a clean pass, and the CI workflow
passes the same glob to `DavidAnson/markdownlint-cli2-action`. Neither is a
pipeline, so neither loses a producer's status, but a consumer that wants the
same guarantee in its own recipes should call the runner rather than the
wrapper.

## Consequences

**Positives:**

- A gate can no longer pass without having read a file; the failure mode that
  motivated this record is gone rather than guarded.
- The tool's status is the recipe's status, so a finding and a crash are
  distinguishable by exit status alone.
- The file list is deterministic and named, so a gate's evidence is
  reproducible between runs and reviewable in a log.
- Discovery, invocation and error reporting are tested once here rather than
  re-tested in every consumer.
- A missing tool is reported as `'<tool>' is required, but not installed`,
  which is actionable where a shell's `command not found` inside a pipeline
  was not.

**Costs and trade-offs:**

- Consumers carry one more script and must regenerate their recipes to benefit.
- A gate now resolves its tool through `PATH` in Python rather than by shell
  lookup, so an override such as `MDLINT=./stub` must be executable.
- A tool that reads a directory operand is no longer given one; the exclusion
  policy belongs to the walk, and a consumer with different exclusions passes
  them to the runner.
- Each gate spends one `uv run --script` start-up before the tool runs, which
  is paid once per gate rather than once per batch.
