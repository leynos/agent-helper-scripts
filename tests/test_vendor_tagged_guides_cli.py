"""Tests for the command-line boundary.

The fast cases check that a declared input error leaves the front end as one
diagnostic line. The slow case drives the real formatter and the repository's
Markdown configuration from a separate consumer checkout.
"""

from __future__ import annotations

import os
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
            (
                "vendor_tagged_guides: error: 'definitely-absent-tool' is "
                "required, but not installed"
            ),
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


def test_the_documented_environment_variables_stand_in_for_the_options(
    tmp_path: Path,
) -> None:
    """The list and boolean variables take effect under their flag names."""
    source = tmp_path / "source"
    output = tmp_path / "docs"
    source.mkdir()
    output.mkdir()
    for name in ("first.md", "second.md"):
        (source / name).write_text(
            "# Title\n\nBody.\n", encoding="utf-8", newline="\n"
        )

    result = run_cli(
        cwd=tmp_path,
        env={
            "VENDOR_TAGGED_GUIDES_TAG": "v0.2.0-beta2",
            "VENDOR_TAGGED_GUIDES_REPOSITORY": "leynos/cuprum",
            "VENDOR_TAGGED_GUIDES_SOURCE": str(source),
            "VENDOR_TAGGED_GUIDES_OUTPUT": str(output),
            "VENDOR_TAGGED_GUIDES_MAP": (
                "first.md=vendored-first.md second.md=vendored-second.md"
            ),
            "VENDOR_TAGGED_GUIDES_FORMAT": "false",
            "VENDOR_TAGGED_GUIDES_FORMATTER": "definitely-absent-tool",
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert sorted(path.name for path in output.glob("*.md")) == [
        "vendored-first.md",
        "vendored-second.md",
    ], result.stdout


@pytest.mark.parametrize(
    ("arguments", "environment", "exempted"),
    [
        ((), None, False),
        (("--line-length", "40", "--code-line-length", "20"), None, True),
        (
            (),
            {
                "VENDOR_TAGGED_GUIDES_LINE_LENGTH": "40",
                "VENDOR_TAGGED_GUIDES_CODE_LINE_LENGTH": "20",
            },
            True,
        ),
    ],
    ids=["default", "options", "environment"],
)
def test_the_line_limits_are_configurable_through_options_and_environment(
    tmp_path: Path,
    arguments: tuple[str, ...],
    environment: dict[str, str] | None,
    exempted: bool,
) -> None:
    """The exemption pass can match a consumer's own MD013 limits."""
    source = tmp_path / "source"
    output = tmp_path / "docs"
    source.mkdir()
    output.mkdir()
    (source / "users-guide.md").write_text(
        "# Title\n\n"
        "This prose line is deliberately longer than forty characters.\n\n"
        "```text\n"
        "alpha beta gamma delta epsilon\n"
        "```\n",
        encoding="utf-8",
        newline="\n",
    )
    written = output / "vendored.md"

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
        "--no-format",
        *arguments,
        cwd=tmp_path,
        env=environment,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    text = written.read_text(encoding="utf-8")
    if not exempted:
        assert "markdownlint-disable MD013" not in text, text
        return
    assert "<!-- markdownlint-disable MD013 -->\n\nThis prose line" in text, text
    assert "<!-- markdownlint-disable MD013 -->\n\n```text" in text, text


@pytest.mark.slow
def test_the_real_command_line_and_markdown_gates_reach_a_fixed_point(
    tmp_path: Path,
) -> None:
    """A consumer checkout converts twice with no diff and passes both gates."""
    # Resolve both tools against one search path, and give the command the same
    # path. The `.bun/bin` fallback is common on this host, but a tool found only
    # there is invisible to the subprocess when it inherits the plain `PATH`.
    bun_bin = Path.home() / ".bun" / "bin"
    search_path = os.pathsep.join([os.environ.get("PATH", ""), str(bun_bin)])
    tools: dict[str, str] = {}
    for name in (REAL_FORMATTER, REAL_LINTER):
        path = shutil.which(name, path=search_path)
        if path is None:
            pytest.skip(f"{name} is unavailable; the end-to-end run is skipped")
        tools[name] = path

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
            env={"PATH": search_path},
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


def test_the_command_line_reports_an_inaccessible_source_without_a_traceback(
    tmp_path: Path,
) -> None:
    """A permission error while inspecting the source is one diagnostic line."""
    if os.geteuid() == 0:
        pytest.skip("root bypasses directory permissions")
    outer = tmp_path / "outer"
    (outer / "docs").mkdir(parents=True)
    (tmp_path / "output").mkdir()
    outer.chmod(0)
    try:
        result = run_cli(
            "--tag",
            "v0.2.0-beta2",
            "--repository",
            "leynos/cuprum",
            "--source",
            "outer/docs",
            "--output",
            "output",
            "--map",
            "users-guide.md=cuprum-users-guide.md",
            "--no-format",
            cwd=tmp_path,
        )
    finally:
        outer.chmod(0o755)

    assert result.returncode == 1, result.stdout + result.stderr
    lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(lines) == 1, result.stderr
    assert lines[0].startswith(
        "vendor_tagged_guides: error: cannot inspect the import paths"
    ), result.stderr
    assert "Traceback" not in result.stderr, result.stderr
