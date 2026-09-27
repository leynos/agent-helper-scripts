"""Behavioural tests for the OpenTofu guide's deliberately misspelt variable.

The OpenTofu guide illustrates an undeclared-variable error with a variable
name whose first word is transposed. Every repository that carries the guide
must pass the spelling gate on that example, so the shared dictionary exempts
it; but only the example's exact text, because a broader shared pattern hid
the same transposition in every consumer's real Terraform or OpenTofu source.

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
#: The one shared pattern, which exempts only the guide's worked example.
EXAMPLE_PATTERN = rf"`var\.{TRANSPOSED}_id` instead of `var\.image_id`"
#: Uses of the misspelt reference that must stay visible to the scanner.
NEAR_MISSES: tuple[str, ...] = (
    MISSPELT_REFERENCE,
    f"ami = {MISSPELT_REFERENCE}",
    f"`{MISSPELT_REFERENCE}`",
    f"{MISSPELT_REFERENCE} instead of var.image_id",
    f"`{MISSPELT_REFERENCE}` instead of `var.image_ids`",
)


def ignore_patterns(path: Path, table: str = "patterns", key: str = "ignore") -> list[str]:
    """Return one TOML file's ignore patterns."""
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    return document.get(table, {}).get(key, [])


def naming_the_word(patterns: list[str]) -> list[str]:
    """Return the patterns that mention the transposed word."""
    return [pattern for pattern in patterns if TRANSPOSED in pattern]


def test_shared_policy_exempts_only_the_guide_example() -> None:
    """The shared dictionary carries the narrow pattern and nothing broader."""
    mentions = naming_the_word(ignore_patterns(SHARED_DICTIONARY_PATH))

    assert mentions == [EXAMPLE_PATTERN], f"shared policy exempts {mentions!r}"
    re.compile(EXAMPLE_PATTERN)


def test_this_repository_needs_no_local_exemption() -> None:
    """The shared pattern covers this repository's copy of the guide."""
    mentions = naming_the_word(ignore_patterns(LOCAL_DICTIONARY_PATH))

    assert not mentions, f"the local overlay still exempts {mentions!r}"


def test_the_shared_pattern_matches_the_guide_as_written() -> None:
    """The exemption protects text the guide actually contains.

    An exemption whose text has drifted from the guide would protect nothing
    while the example fails every consumer's gate.
    """
    guide = GUIDE_PATH.read_text(encoding="utf-8")

    assert re.search(EXAMPLE_PATTERN, guide), (
        "the exemption no longer matches the guide's worked example"
    )


def test_the_generated_configuration_renders_only_the_narrow_pattern() -> None:
    """The committed rendering carries the narrow pattern and nothing broader."""
    rendered = ignore_patterns(COMMITTED_CONFIG_PATH, "default", "extend-ignore-re")

    assert naming_the_word(rendered) == [EXAMPLE_PATTERN], (
        f"typos.toml exempts {naming_the_word(rendered)!r}"
    )


@pytest.mark.parametrize("text", NEAR_MISSES)
def test_other_uses_of_the_misspelt_variable_are_not_exempt(text: str) -> None:
    """Every shared pattern naming the word leaves other uses visible.

    This is the negative control for the guide match above. It reads the
    dictionary as committed, so a pattern loosened to the bare reference
    fails here.
    """
    for pattern in naming_the_word(ignore_patterns(SHARED_DICTIONARY_PATH)):
        assert re.search(pattern, text) is None, f"{pattern!r} also masks {text!r}"


def run_consumer_gate(repository: Path, files: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the pinned gate for a scratch consumer against this dictionary.

    The consumer tracks the given files and takes this checkout's dictionary as
    its source, exactly as a consumer receives it once this change merges.
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
    files = {**files, ".gitignore": ".typos-oxendict-base.json\n.typos-oxendict-base.toml\n"}
    for name, text in files.items():
        (repository / name).write_text(text, encoding="utf-8")
    subprocess.run([git, "init", "-q"], cwd=repository, check=True)
    subprocess.run([git, "add", *files], cwd=repository, check=True)
    builder = (
        "git+https://github.com/leynos/typos-config-builder.git@" + version.group(1)
    )
    return subprocess.run(
        [uv, "tool", "run", "--python", "3.14", "--from", builder,
         "typos-config-builder", "gate", "--repository", str(repository),
         "--source", str(SHARED_DICTIONARY_PATH), "--scope", "all"],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )


@pytest.mark.slow
def test_a_consumer_passes_on_the_guide_example(tmp_path: Path) -> None:
    """A consumer carrying the guide's example needs no exemption of its own."""
    example = (
        "The error follows a typo in a reference (for example,\n"
        f"`{MISSPELT_REFERENCE}` instead of `var.image_id`).\n"
    )

    result = run_consumer_gate(tmp_path, {"guide.md": example})

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.slow
def test_a_consumer_gate_reports_the_misspelt_variable(tmp_path: Path) -> None:
    """A consumer's real OpenTofu source with the misspelling is reported."""
    source = f'variable "image_id" {{}}\nresource "x" "y" {{ ami = {MISSPELT_REFERENCE} }}\n'

    result = run_consumer_gate(tmp_path, {"main.tf": source})

    assert result.returncode == 2, result.stdout + result.stderr
    assert TRANSPOSED in result.stdout + result.stderr, (
        "the gate failed without naming the misspelt variable"
    )
