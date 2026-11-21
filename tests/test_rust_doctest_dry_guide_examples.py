"""Exercise the Rust doctest guide's published helper pattern with Cargo.

The Rust doctest guide ships seven marked Rust fences. This module executes
only the Section 4.2 ``doctest-helpers-library`` example, which is a complete
``src/lib.rs`` for a small crate named ``mycrate``. The other six fences remain
with issue #141, which covers execution or shape checks for every example in
the Rust testing and verification guides.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil

import pytest
from cuprum import (
    CommandResult,
    ExecutionContext,
    Program,
    ProgramCatalogue,
    scoped,
    sh,
)

from tested_example_test_support import load_tested_examples

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUST_DOCTEST_DRY_GUIDE_PATH = (
    REPOSITORY_ROOT / "documentation-library" / "rust-doctest-dry-guide.md"
)
EXAMPLES = {
    example.identifier: example
    for example in load_tested_examples(RUST_DOCTEST_DRY_GUIDE_PATH)
}
HELPER_EXAMPLE_IDENTIFIER = "doctest-helpers-library"
SUPPORTED_EDITIONS = ("2021", "2024")

#: The only external program this module runs. Rooted in a local catalogue, as
#: the scripting standards require of standalone tests.
CARGO = Program("cargo")
CATALOGUE = ProgramCatalogue.from_programs(CARGO, name="rust-doctest-dry-guide")

#: A cold doctest run compiles the library and then the generated doctest
#: crate, so it is slower than running a prebuilt test binary. The timeout is
#: deliberately generous, but still far above the 30-second floor that would
#: mask a hung Cargo invocation.
CARGO_DOCTEST_TIMEOUT_SECONDS = 600

_PASSED_RE = re.compile(r"(?P<count>\d+) passed")
_FAILED_RE = re.compile(r"(?P<count>\d+) failed")


def _helper_source() -> str:
    """Return the shipped Section 4.2 source for the helper example."""
    example = EXAMPLES[HELPER_EXAMPLE_IDENTIFIER]
    assert example.language == "rust", (
        f"tested example {HELPER_EXAMPLE_IDENTIFIER!r} must be a Rust fence"
    )
    return example.body


def _require_cargo() -> None:
    """Skip locally, or fail in CI, when Cargo is not installed."""
    if shutil.which("cargo") is not None:
        return
    if os.environ.get("CI"):
        pytest.fail(
            "cargo is required to validate the published Rust doctest helper "
            "pattern in CI; install stable Rust 1.85 or later"
        )
    pytest.skip(
        "cargo is not installed; install stable Rust 1.85 or later to run "
        "the Rust doctest guide examples"
    )


def _write_crate(tmp_path: Path, *, edition: str, source: str) -> Path:
    """Write a dependency-free ``mycrate`` package for one edition."""
    crate = tmp_path / f"mycrate-edition-{edition}"
    source_directory = crate / "src"
    source_directory.mkdir(parents=True)
    (crate / "Cargo.toml").write_text(
        "\n".join(
            (
                "[package]",
                'name = "mycrate"',
                'version = "0.1.0"',
                f'edition = "{edition}"',
                "",
                "[workspace]",
                "",
            )
        ),
        encoding="utf-8",
    )
    (source_directory / "lib.rs").write_text(source, encoding="utf-8")
    return crate


def _run_doctests(crate: Path) -> CommandResult:
    """Run ``cargo test --doc --offline`` against one scratch crate."""
    with scoped(catalogue=CATALOGUE):
        cargo = sh.make(CARGO)
        return cargo("test", "--doc", "--offline").run_sync(
            context=ExecutionContext(
                cwd=crate,
                env={
                    "CARGO_TARGET_DIR": str(crate / "target"),
                    "CARGO_TERM_COLOR": "never",
                },
            ),
            timeout=CARGO_DOCTEST_TIMEOUT_SECONDS,
        )


def _assert_a_doctest_passed(result: CommandResult, *, context: str) -> None:
    """Assert a successful run reported at least one pass and no failures."""
    output = result.stdout + result.stderr
    assert result.exit_code == 0, (
        f"{context}: expected cargo test --doc to succeed\n{output}"
    )
    passed = [int(match.group("count")) for match in _PASSED_RE.finditer(output)]
    failed = [int(match.group("count")) for match in _FAILED_RE.finditer(output)]
    assert passed and max(passed) >= 1, (
        f"{context}: expected at least one passed doctest\n{output}"
    )
    assert failed and max(failed) == 0, (
        f"{context}: expected zero failed doctests\n{output}"
    )


def _negative_control_source(source: str) -> str:
    """Return the published source with the helper guarded by ``cfg(doctest)``."""
    attribute = "#[doc(hidden)]"
    assert source.count(attribute) == 1, (
        "the published helper example must carry exactly one #[doc(hidden)] "
        "attribute so the negative control can replace it"
    )
    control = source.replace(attribute, "#[cfg(doctest)]")
    assert control != source, "the negative control must change the source"
    return control


@pytest.mark.slow
@pytest.mark.parametrize("edition", SUPPORTED_EDITIONS)
def test_published_helper_example_runs_its_doctest(
    tmp_path: Path, edition: str
) -> None:
    """The published ``mycrate`` source passes ``cargo test --doc`` per edition."""
    _require_cargo()
    crate = _write_crate(tmp_path, edition=edition, source=_helper_source())
    result = _run_doctests(crate)
    _assert_a_doctest_passed(result, context=f"edition {edition}")


@pytest.mark.slow
def test_cfg_doctest_helper_is_absent_from_the_doctest_dependency(
    tmp_path: Path,
) -> None:
    """The old pattern fails because the linked library omits the helper module."""
    _require_cargo()
    source = _negative_control_source(_helper_source())
    crate = _write_crate(tmp_path, edition="2021", source=source)
    result = _run_doctests(crate)
    output = result.stdout + result.stderr
    assert result.exit_code != 0, (
        "the cfg(doctest) helper must not be importable from an external "
        f"doctest crate\n{output}"
    )
    assert "unresolved import" in output, (
        f"expected an unresolved import diagnostic\n{output}"
    )
    assert "doctest_helpers" in output, (
        f"expected the diagnostic to name the missing helper module\n{output}"
    )