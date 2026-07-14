#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=4.3,<5"]
# ///
"""Operate the shared en-GB-oxendict rollout from a repository checkout.

``generate`` conditionally refreshes an untracked base cache over HTTP or from
a local source, merges ``typos.local.toml``, and writes deterministic
``typos.toml``. ``check`` enforces exact phrase corrections that Typos cannot
tokenize as one word. ``harvest`` reads Git-tracked UTF-8 text and emits JSON
Lines evidence without changing repository files.

Examples
--------
Generate configuration in the current repository::

    uv run --script scripts/typos_rollout_cli.py generate

Check punctuation-separated phrase policy::

    uv run --script scripts/typos_rollout_cli.py check

Harvest a neighbouring repository::

    uv run --script scripts/typos_rollout_cli.py harvest ../project
"""

import json
from pathlib import Path

import cyclopts
from cyclopts import App

import typos_rollout as rollout

DEFAULT_BASE_URL = (
    "https://raw.githubusercontent.com/leynos/agent-helper-scripts/"
    "refs/heads/main/data/typos-oxendict-base.toml"
)


def cli() -> None:
    """Run the environment-aware Cyclopts command-line interface.

    Returns
    -------
    None
        Cyclopts parses arguments and dispatches the selected command.
    """
    app = App(config=cyclopts.config.Env("TYPOS_ROLLOUT_", command=False))

    @app.command
    def generate(
        repository: Path = Path.cwd(),
        source: str = DEFAULT_BASE_URL,
        offline: bool = False,
    ) -> None:
        """Refresh the shared base and generate a repository's ``typos.toml``.

        Parameters
        ----------
        repository
            Repository root receiving cache, metadata, and generated config.
        source
            Local path or HTTP URL for the authoritative shared base.
        offline
            Reuse an existing valid cache without contacting the source.

        Returns
        -------
        None
            Writes files and prints the stable refresh status.
        """
        cache = repository / ".typos-oxendict-base.toml"
        result = rollout.refresh_base(
            source,
            cache,
            rollout.RefreshOptions(
                metadata=repository / ".typos-oxendict-base.json",
                offline=offline,
            ),
        )
        dictionary = rollout.load_dictionary(cache)
        local_overlay = repository / "typos.local.toml"
        if local_overlay.exists():
            dictionary = rollout.merge_dictionaries(
                dictionary,
                rollout.load_dictionary(local_overlay, local_overlay=True),
            )
        rollout.write_config(repository / "typos.toml", dictionary)
        print(f"{result.status}: {repository / 'typos.toml'}")

    @app.command
    def harvest(repository: Path = Path.cwd()) -> None:
        """Print JSON Lines evidence for Oxford-form candidates.

        Parameters
        ----------
        repository
            Git repository whose tracked UTF-8 text should be inspected.

        Returns
        -------
        None
            Emits one JSON object per matching source line to standard output.
        """
        for finding in rollout.harvest_repository(repository):
            print(json.dumps(finding, sort_keys=True))

    @app.command
    def check(repository: Path = Path.cwd()) -> None:
        """Reject prohibited exact phrases in tracked text.

        Parameters
        ----------
        repository
            Repository root containing the refreshed shared cache and optional
            local spelling overlay.

        Returns
        -------
        None
            Prints actionable findings and exits with status two when any
            prohibited phrase is present.
        """
        dictionary = rollout.load_dictionary(repository / ".typos-oxendict-base.toml")
        local_overlay = repository / "typos.local.toml"
        if local_overlay.exists():
            dictionary = rollout.merge_dictionaries(
                dictionary,
                rollout.load_dictionary(local_overlay, local_overlay=True),
            )
        findings = rollout.check_phrase_corrections(repository, dictionary)
        for finding in findings:
            print(
                f"{finding.path}:{finding.line}:{finding.column}: "
                f"{finding.phrase} -> {finding.correction}"
            )
        if findings:
            raise SystemExit(2)

    app()


if __name__ == "__main__":
    cli()
