"""Behavioural tests for the OpenTofu guide's deliberately misspelt variable.

The OpenTofu guide illustrates an undeclared-variable error with a variable
name whose first word is transposed. That example must pass this repository's
spelling gate, but the exemption belongs to this repository alone: as a
shared pattern it hid the same transposition in every consumer's real
Terraform or OpenTofu source.

The transposed word is assembled from fragments so that this module's own
source does not trip the repository's spelling gate.
"""

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from spelling_policy_support import (
    COMMITTED_CONFIG_PATH,
    LOCAL_DICTIONARY_PATH,
    REPOSITORY_ROOT,
    SHARED_DICTIONARY_PATH,
)

TRANSPOSED = "iam" + "ge"
MISSPELT_REFERENCE = f"var.{TRANSPOSED}_id"
GUIDE_PATH = REPOSITORY_ROOT / "documentation-library" / "opentofu-hcl-syntax-guide.md"
#: The overlay entry that exempts only the guide's worked example.
LOCAL_PATTERN = rf"`var\.{TRANSPOSED}_id` instead of `var\.image_id`"
#: Uses of the misspelt reference that must stay visible to the scanner.
NEAR_MISSES: tuple[str, ...] = (
    MISSPELT_REFERENCE,
    f"ami = {MISSPELT_REFERENCE}",
    f"`{MISSPELT_REFERENCE}`",
    f"`{MISSPELT_REFERENCE}` instead of `var.image_ids`",
)


def ignore_patterns(path: Path, table: str = "patterns", key: str = "ignore") -> list[str]:
    """Return one TOML file's ignore patterns."""
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    return document[table][key]


def test_shared_policy_does_not_exempt_the_misspelt_variable() -> None:
    """No shared ignore pattern mentions the transposed word."""
    offenders = [p for p in ignore_patterns(SHARED_DICTIONARY_PATH) if TRANSPOSED in p]

    assert not offenders, f"shared policy still exempts {offenders!r}"


def test_the_local_overlay_exempts_the_guide_example() -> None:
    """This repository's overlay carries the narrow entry, and it compiles."""
    assert LOCAL_PATTERN in ignore_patterns(LOCAL_DICTIONARY_PATH), (
        "the local overlay lost the guide example's exemption"
    )
    re.compile(LOCAL_PATTERN)


def test_the_local_entry_matches_the_guide_as_written() -> None:
    """The entry protects text the guide actually contains.

    An exemption whose text has drifted from the guide would protect nothing
    while the example fails the gate.
    """
    guide = GUIDE_PATH.read_text(encoding="utf-8")

    assert re.search(LOCAL_PATTERN, guide), (
        "the exemption no longer matches the guide's worked example"
    )


def test_the_generated_configuration_renders_only_the_local_entry() -> None:
    """The committed rendering carries the narrow entry and nothing broader."""
    rendered = ignore_patterns(COMMITTED_CONFIG_PATH, "default", "extend-ignore-re")
    mentions = [p for p in rendered if TRANSPOSED in p]

    assert mentions == [LOCAL_PATTERN], f"typos.toml exempts {mentions!r}"


@pytest.mark.parametrize("text", NEAR_MISSES)
def test_other_uses_of_the_misspelt_variable_are_not_exempt(text: str) -> None:
    """Every overlay entry naming the word leaves other uses visible.

    This is the negative control for the guide match above. It reads the
    overlay as committed, so an entry widened to the bare reference fails here.
    """
    entries = [p for p in ignore_patterns(LOCAL_DICTIONARY_PATH) if TRANSPOSED in p]

    for entry in entries:
        assert re.search(entry, text) is None, f"{entry!r} also masks {text!r}"


@pytest.mark.slow
def test_a_consumer_gate_reports_the_misspelt_variable(tmp_path: Path) -> None:
    """A consumer checked against this dictionary reports a real misspelling.

    The consumer tracks one OpenTofu file that references the transposed
    variable and runs the pinned `typos-config-builder gate` with this
    checkout's dictionary as its source, exactly as a consumer receives it.
    """
    uv = shutil.which("uv")
    git = shutil.which("git")
    if uv is None or git is None:
        pytest.skip("uv and git are needed to run the consumer gate")
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    version = re.search(
        r"^TYPOS_CONFIG_BUILDER_VERSION\s*\?=\s*(\S+)$", makefile, re.MULTILINE
    )
    assert version is not None, "the builder version is not pinned"
    (tmp_path / "main.tf").write_text(
        f'variable "image_id" {{}}\nresource "x" "y" {{ ami = {MISSPELT_REFERENCE} }}\n',
        encoding="utf-8",
    )
    (tmp_path / ".gitignore").write_text(
        ".typos-oxendict-base.json\n.typos-oxendict-base.toml\n", encoding="utf-8"
    )
    subprocess.run([git, "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run([git, "add", "main.tf", ".gitignore"], cwd=tmp_path, check=True)
    builder = (
        "git+https://github.com/leynos/typos-config-builder.git@" + version.group(1)
    )

    result = subprocess.run(
        [uv, "tool", "run", "--python", "3.14", "--from", builder,
         "typos-config-builder", "gate", "--repository", str(tmp_path),
         "--source", str(SHARED_DICTIONARY_PATH), "--scope", "all"],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert TRANSPOSED in result.stdout + result.stderr, (
        "the gate failed without naming the misspelt variable"
    )
