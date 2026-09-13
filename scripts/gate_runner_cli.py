#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=4.3,<5"]
# ///
"""Run a repository gate over one explicit file list.

Each subcommand is one command in a repository's Makefile, replacing a recipe
that piped a producer into a checker. The commands themselves live in the
sibling ``gate_runner`` module, which imports nothing beyond the standard
library, so a test can drive one with a command double standing in for its
tool.

Examples
--------
Run the shared spelling gate::

    uv run --script scripts/gate_runner_cli.py spelling

Lint every Markdown file in the tree::

    uv run --script scripts/gate_runner_cli.py markdownlint

Validate every Mermaid diagram::

    uv run --script scripts/gate_runner_cli.py nixie

Parameters are environment-aware, so a caller can set ``GATE_RUNNER_TYPOS`` or
``GATE_RUNNER_LINTER`` instead of passing an option.
"""

import sys

import cyclopts
from cyclopts import App

import gate_runner


def cli() -> None:
    """Run the environment-aware Cyclopts command-line interface.

    Returns
    -------
    None
        Cyclopts parses arguments and dispatches the selected command. A
        discovery or execution failure is reported as one diagnostic line and
        exits with status one rather than surfacing as a traceback.
    """
    app = App(
        name="gate_runner",
        config=cyclopts.config.Env("GATE_RUNNER_", command=False),
        help="Run a repository gate over one explicit file list.",
    )
    app.command(gate_runner.spelling)
    app.command(gate_runner.markdownlint)
    app.command(gate_runner.nixie)
    try:
        app()
    except gate_runner.GATE_ERRORS as error:
        print(f"gate_runner: error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    cli()
