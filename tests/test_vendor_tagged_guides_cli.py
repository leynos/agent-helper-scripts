"""Tests for the command-line boundary.

The fast cases check that a declared input error leaves the front end as one
diagnostic line. The slow case drives the real formatter and the repository's
Markdown configuration from a separate consumer checkout.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from vendor_tagged_guides_test_support import (
    FORMATTER_ARGUMENTS,
    MARKDOWNLINT_CONFIG,
    REAL_FORMATTER,
    REAL_LINTER,
    run_cli,
    write_upstream,
)


def test_the_command_line_reports_an_invalid_mapping_without_a_traceback(
    tmp_path: Path,
) -> None:
    """A declared input error is one diagnostic line and status one."""
    result = run_cli(
        "--tag",
        "v0.2.0-beta2",
        "--repository",
        "leynos/cuprum",
        "--source",
        str(tmp_path),
        "--output",
        str(tmp_path),
        "--map",
        "not-a-pair",
        "--no-format",
        cwd=tmp_path,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert (
        "vendor_tagged_guides: error: --map expects SRC=OUT" in result.stderr
    ), result.stderr
    assert "Traceback" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("formatter", "message"),
    [
        (
            "definitely-absent-tool",
            "vendor_tagged_guides: error: 'definitely-absent-tool' is required, "
            "but not installed",
        ),
        (
            "unbalanced 'quote",
            "vendor_tagged_guides: error: --formatter is not a valid command line",
        ),
    ],
)
def test_the_command_line_reports_a_bad_formatter_without_a_traceback(
    tmp_path: Path, formatter: str, message: str
) -> None:
    """A missing or malformed formatter is a named failure, not a traceback."""
    source = tmp_path / "source"
    output = tmp_path / "docs"
    source.mkdir()
    output.mkdir()
    (source / "users-guide.md").write_text(
        "# Title\n\nBody.\n", encoding="utf-8", newline="\n"
    )

    result = run_cli(
        "--tag",
        "v0.2.0-beta2",
        "--repository",
        "leynos/cuprum",
        "--source",
        str(source),
        "--output",
        str(output),
        "--map",
        "users-guide.md=vendored.md",
        "--formatter",
        formatter,
        cwd=tmp_path,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert message in result.stderr, result.stderr
    assert "Traceback" not in result.stderr, result.stderr


@pytest.mark.slow
def test_the_real_command_line_and_markdown_gates_reach_a_fixed_point(
    tmp_path: Path,
) -> None:
    """A consumer checkout converts twice with no diff and passes both gates."""
    tools = {
        name: shutil.which(name) or str(Path.home() / ".bun" / "bin" / name)
        for name in (REAL_FORMATTER, REAL_LINTER)
    }
    for name, path in tools.items():
        if not Path(path).exists():
            pytest.skip(f"{name} is unavailable; the end-to-end run is skipped")

    source_directory = write_upstream(
        tmp_path,
        {
            "users-guide.md": (
                "# Users' guide\n\n"
                "## Program catalogue\n\n"
                "See the [migration guide](v0-2-0-migration-guide.md#moving)\n"
                "and the [developers' guide](developers-guide.md).\n\n"
                "A line with two adjacent links that the formatter rejoins: "
                "[the first guide](https://example.com/one) and "
                "[the second guide](https://example.com/two) are both useful.\n"
            ),
            "v0-2-0-migration-guide.md": (
                "# Migration guide\n\n"
                "## Moving from 0.1\n\n"
                "Start with the [users' guide](users-guide.md#program-catalogue).\n"
            ),
        },
    )
    consumer = tmp_path / "consumer"
    (consumer / "docs").mkdir(parents=True)
    (consumer / ".markdownlint-cli2.jsonc").write_bytes(
        MARKDOWNLINT_CONFIG.read_bytes()
    )

    def invoke() -> None:
        """Run the vendoring front end from the consumer checkout."""
        result = run_cli(
            "--tag",
            "v0.2.0-beta2",
            "--repository",
            "leynos/cuprum",
            "--source",
            str(source_directory),
            "--output",
            "docs",
            "--map",
            "users-guide.md=cuprum-users-guide.md",
            "--map",
            "v0-2-0-migration-guide.md=cuprum-v0-2-0-migration-guide.md",
            cwd=consumer,
            timeout=600,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    invoke()
    written = sorted((consumer / "docs").glob("*.md"))
    first = {path.name: path.read_bytes() for path in written}
    invoke()
    second = {path.name: path.read_bytes() for path in written}

    assert first == second, (first, second)

    formatter = subprocess.run(  # noqa: S603 - controlled arguments, no shell.
        [tools[REAL_FORMATTER], "--check", *FORMATTER_ARGUMENTS, *map(str, written)],
        cwd=consumer,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert formatter.returncode == 0, formatter.stdout + formatter.stderr

    linter = subprocess.run(  # noqa: S603 - controlled arguments, no shell.
        [tools[REAL_LINTER], *map(str, written)],
        cwd=consumer,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert linter.returncode == 0, linter.stdout + linter.stderr
