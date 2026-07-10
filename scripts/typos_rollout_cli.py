#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=4.3,<5", "plumbum>=1.9,<2"]
# ///
"""Command-line interface for the shared en-GB-oxendict rollout helper."""

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
    """Run the environment-aware Cyclopts command-line interface."""
    app = App(config=cyclopts.config.Env("TYPOS_ROLLOUT_", command=False))

    @app.command
    def generate(
        repository: Path = Path.cwd(),
        source: str = DEFAULT_BASE_URL,
        offline: bool = False,
    ) -> None:
        """Refresh the shared base and generate a repository's typos.toml."""
        cache = repository / ".typos-oxendict-base.toml"
        result = rollout.refresh_base(
            source,
            cache,
            metadata=repository / ".typos-oxendict-base.json",
            offline=offline,
        )
        dictionary = rollout.load_dictionary(cache)
        local_overlay = repository / "typos.local.toml"
        if local_overlay.exists():
            dictionary = rollout.merge_dictionaries(
                dictionary,
                rollout.load_dictionary(local_overlay),
            )
        rollout.write_config(repository / "typos.toml", dictionary)
        print(f"{result.status}: {repository / 'typos.toml'}")

    @app.command
    def harvest(repository: Path = Path.cwd()) -> None:
        """Print JSON Lines evidence for Oxford-form candidates."""
        for finding in rollout.harvest_repository(repository):
            print(json.dumps(finding, sort_keys=True))

    app()


if __name__ == "__main__":
    cli()
