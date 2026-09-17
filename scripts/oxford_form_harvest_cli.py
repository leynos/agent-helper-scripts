#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=4.3,<5"]
# ///
"""Print JSON Lines evidence for Oxford-form candidates in tracked text.

The harvesting itself lives in the sibling ``oxford_form_harvest`` module,
which imports nothing beyond the standard library, so a test drives it without
this front end.

Examples
--------
Harvest this checkout::

    uv run --script scripts/oxford_form_harvest_cli.py

Harvest a neighbouring repository::

    uv run --script scripts/oxford_form_harvest_cli.py --repository ../project
"""

import json
from pathlib import Path

import cyclopts
from cyclopts import App

import oxford_form_harvest


def cli() -> None:
    """Run the environment-aware Cyclopts command-line interface.

    Returns
    -------
    None
        Cyclopts parses arguments and dispatches the command, which writes one
        JSON object per matching source line to standard output.
    """
    app = App(
        name="oxford-form-harvest",
        config=cyclopts.config.Env("OXFORD_FORM_HARVEST_", command=False),
        help="Print JSON Lines evidence for Oxford-form candidates.",
    )

    @app.default
    def run(repository: Path = Path.cwd()) -> None:
        """Print evidence for every candidate form in tracked text.

        Parameters
        ----------
        repository
            Git repository whose tracked UTF-8 text should be inspected.

        Returns
        -------
        None
            Writes one JSON object per matching source line.
        """
        for finding in oxford_form_harvest.harvest(repository):
            print(json.dumps(finding, sort_keys=True))

    app()


if __name__ == "__main__":
    cli()
