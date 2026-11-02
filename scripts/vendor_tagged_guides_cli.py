#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["cyclopts>=4.3,<5", "cuprum==0.2.0b2"]
# ///
"""Vendor an upstream guide at a pinned tag into a consuming repository.

The conversion itself lives in the sibling ``vendor_tagged_guides`` package,
which imports nothing beyond the standard library. This front end adds the
Cyclopts parameters and the cuprum process boundary that runs the consumer's
Markdown formatter over the converted files.

Examples
--------
Vendor two cuprum guides into this checkout::

    uv run --script scripts/vendor_tagged_guides_cli.py \\
        --tag v0.2.0-beta2 \\
        --repository leynos/cuprum \\
        --source ../cuprum/docs \\
        --output docs \\
        --map users-guide.md=cuprum-users-guide.md \\
        --map v0-2-0-migration-guide.md=cuprum-v0-2-0-migration-guide.md

Skip the formatter when the output is inspected rather than committed::

    uv run --script scripts/vendor_tagged_guides_cli.py ... --no-format

Parameters are environment-aware, so a caller can set
``VENDOR_TAGGED_GUIDES_TAG`` instead of passing an option.
"""

from collections.abc import Sequence
from pathlib import Path
import shlex
import sys
from typing import Annotated

import cyclopts
from cyclopts import App, Parameter
from cuprum import (
    ExecutionContext,
    Program,
    ProgramCatalogue,
    RunOutputOptions,
    scoped,
    sh,
)

import vendor_tagged_guides

#: Formatter the shared Markdown baseline runs. The arguments mirror the
#: repository's own ``make fmt`` rule so a vendored guide matches the files
#: already committed beside it.
DEFAULT_FORMATTER = (
    "mdtablefix",
    "--in-place",
    "--wrap",
    "--renumber",
    "--breaks",
    "--ellipsis",
    "--fences",
)


def _absolute(path: Path) -> Path:
    """Resolve a caller-supplied path from the working directory."""
    return path if path.is_absolute() else Path.cwd() / path


def _mappings(values: Sequence[str] | None) -> tuple[tuple[str, str], ...]:
    """Parse repeatable ``--map SRC=OUT`` values, refusing a missing ``=``."""
    pairs: list[tuple[str, str]] = []
    for value in values or ():
        source, separator, output = value.partition("=")
        if not separator:
            raise vendor_tagged_guides.VendorError(
                f"--map expects SRC=OUT, got {value!r}"
            )
        pairs.append((source, output))
    return tuple(pairs)


def _formatter_command(formatter: str) -> tuple[str, ...]:
    """Split a formatter command line, defaulting when it is blank."""
    try:
        return tuple(shlex.split(formatter)) or DEFAULT_FORMATTER
    except ValueError as error:
        raise vendor_tagged_guides.VendorError(
            f"--formatter is not a valid command line: {error}"
        ) from error


def _format_files(
    command: Sequence[str], paths: Sequence[Path]
) -> None:
    """Run the formatter in place, failing on a missing tool or non-zero status."""
    executable, *arguments = command
    program = Program(executable)
    catalogue = ProgramCatalogue.from_programs(program, name="vendor-tagged-guides")
    try:
        with scoped(catalogue=catalogue):
            formatted = sh.make(program)(
                *arguments,
                "--",
                *(str(path) for path in paths),
            )
            result = formatted.run_sync(
                context=ExecutionContext(cwd=Path.cwd()),
                output=RunOutputOptions(capture=True, echo=True),
            )
    except FileNotFoundError as error:
        raise vendor_tagged_guides.VendorError(
            f"'{executable}' is required, but not installed"
        ) from error
    if not result.ok:
        raise vendor_tagged_guides.VendorError(
            f"'{executable}' exited with status {result.exit_code}"
        )


def cli() -> None:
    """Run the environment-aware Cyclopts command-line interface.

    Returns
    -------
    None
        Cyclopts parses arguments and dispatches the command. A validation or
        formatter failure is reported as one diagnostic line and exits with
        status one rather than surfacing as a traceback.
    """
    app = App(
        name="vendor_tagged_guides",
        config=cyclopts.config.Env("VENDOR_TAGGED_GUIDES_", command=False),
        help="Vendor an upstream guide at a pinned tag.",
    )

    @app.default
    def run(
        *,
        tag: str,
        repository: str,
        source: Path,
        output: Path = Path("docs"),
        mapping: Annotated[list[str] | None, Parameter(name="--map")] = None,
        project: str = "",
        source_path: str = vendor_tagged_guides.DEFAULT_SOURCE_PATH,
        run_formatter: Annotated[
            bool,
            Parameter(name="--format", negative="--no-format"),
        ] = True,
        formatter: str = "",
    ) -> None:
        """Convert every mapped guide and print the paths written.

        Parameters
        ----------
        tag
            Upstream tag to pin.
        repository
            Upstream repository in ``owner/name`` form.
        source
            Directory holding the upstream sources, resolved from the
            caller's working directory.
        output
            Directory the converted files are written to.
        mapping
            Repeatable ``SRC=OUT`` filename pair. Required.
        project
            Display name for the import note; defaults to the repository name.
        source_path
            Repository-relative directory of the upstream sources.
        run_formatter
            Whether to run the formatter. ``--no-format`` disables it.
        formatter
            One command line for the formatter, replacing the shared
            ``mdtablefix`` default. It is split with :func:`shlex.split`, so
            the formatter's own option-like flags stay its arguments.

        Returns
        -------
        None
            Prints one written path per line.
        """
        pairs = _mappings(mapping)
        command = _formatter_command(formatter)
        config = vendor_tagged_guides.VendorConfig(
            tag=tag,
            repository=repository,
            source_directory=_absolute(source),
            output_directory=_absolute(output),
            mappings=pairs,
            project=project,
            source_path=source_path,
        )
        written = vendor_tagged_guides.vendor(
            config,
            format_files=(
                (lambda paths: _format_files(command, paths))
                if run_formatter
                else None
            ),
        )
        for path in written:
            print(path)

    try:
        app()
    except vendor_tagged_guides.VENDOR_ERRORS as error:
        print(f"vendor_tagged_guides: error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    cli()