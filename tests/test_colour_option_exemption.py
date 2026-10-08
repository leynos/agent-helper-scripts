"""Behavioural tests for the shared exemption of colour flags and properties.

Command-line flags such as `--no-color` and CSS custom properties such as
`--color-primary` carry the US spelling in the tools that define them, so the
shared dictionary exempts them. The exemption once matched any run of flag
characters around the word `color`, which also hid a misspelling elsewhere in
the same token. It now ends at the word `color`, with an optional `s` or `ed`,
so a misspelling after it is reported. The prefix stays open, because custom
properties are named freely; a misspelling in the prefix is still hidden.

Misspelt words are assembled from fragments so that this module's own source
does not trip the repository's spelling gate.
"""

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from spelling_policy_support import REPOSITORY_ROOT, SHARED_DICTIONARY_PATH

COLOUR = "col" + "or"
#: A flag whose prefix word is transposed, and one whose suffix word is.
PREFIX_MISSPELLING = "dis" + "bale"
SUFFIX_MISSPELLING = "sep" + "erate"
#: Genuine forms that must stay exempt, with the part the pattern must cover.
GENUINE: tuple[tuple[str, str], ...] = (
    (f"--{COLOUR}", f"--{COLOUR}"),
    (f"--{COLOUR}=auto", f"--{COLOUR}"),
    (f"--{COLOUR} always", f"--{COLOUR}"),
    (f"--no-{COLOUR}", f"--no-{COLOUR}"),
    (f"--{COLOUR}-primary", f"--{COLOUR}"),
    (f"--tw-{COLOUR}-red-500", f"--tw-{COLOUR}"),
    (f"--my-brand-{COLOUR}", f"--my-brand-{COLOUR}"),
    (f"--tw-text-shadow-{COLOUR}", f"--tw-text-shadow-{COLOUR}"),
    (f"--ifm-font-{COLOUR}-secondary", f"--ifm-font-{COLOUR}"),
    (f"--tw-shadow-{COLOUR}ed", f"--tw-shadow-{COLOUR}ed"),
    (f"--{COLOUR}s", f"--{COLOUR}s"),
    (f"--{COLOUR}-*", f"--{COLOUR}"),
)
#: Tokens with a misspelling after the colour word, which must stay visible:
#: the pattern must either not match at all or stop before the misspelt word.
NEAR_MISSES: tuple[tuple[str, str], ...] = (
    (f"--{COLOUR}-{SUFFIX_MISSPELLING}", SUFFIX_MISSPELLING),
    (f"--{COLOUR}r", f"{COLOUR}r"),
    (f"--{COLOUR}-mode-{SUFFIX_MISSPELLING}", SUFFIX_MISSPELLING),
    (f"--tw-{COLOUR}-{SUFFIX_MISSPELLING}", SUFFIX_MISSPELLING),
)
#: Near misses the real gate reports: typos only flags known misspellings, so the
#: transposed-letter cases above are covered by the pattern checks alone.
CONSUMER_REPORTED = (NEAR_MISSES[0], NEAR_MISSES[2], NEAR_MISSES[3])
#: The known residual. Custom properties are named freely, so the prefix is
#: open and a misspelling in the prefix of a flag that also contains the colour
#: word is hidden. This is recorded rather than asserted away, so that a
#: vocabulary-based design that closes it can flip this expectation.
PREFIX_RESIDUAL: tuple[tuple[str, str], ...] = (
    (f"--{PREFIX_MISSPELLING}-{COLOUR}", PREFIX_MISSPELLING),
)


def colour_patterns() -> list[str]:
    """Return the shared ignore patterns that mention the word `color`.

    Returns
    -------
    list[str]
        The matching patterns, in their original order.
    """
    document = tomllib.loads(SHARED_DICTIONARY_PATH.read_text(encoding="utf-8"))
    return [
        pattern
        for pattern in document["patterns"]["ignore"]
        if pattern.startswith("--") and COLOUR in pattern
    ]


def test_the_dictionary_carries_exactly_one_flag_pattern() -> None:
    """One bounded pattern covers the flag forms, and it compiles."""
    patterns = colour_patterns()

    assert len(patterns) == 1, f"flag patterns: {patterns!r}"
    re.compile(patterns[0])


@pytest.mark.parametrize(("text", "covered"), GENUINE)
def test_genuine_forms_stay_exempt(text: str, covered: str) -> None:
    """Every genuine flag or property form is matched over its colour part."""
    (pattern,) = colour_patterns()
    match = re.search(pattern, text)

    assert match is not None, f"{pattern!r} no longer exempts {text!r}"
    assert match.group(0) == covered, f"{pattern!r} matched {match.group(0)!r}"


@pytest.mark.parametrize(("text", "misspelling"), NEAR_MISSES)
def test_a_misspelling_in_the_same_token_stays_visible(text: str, misspelling: str) -> None:
    """The pattern never covers the misspelt part of a flag-shaped token.

    This is the negative control for the genuine forms above: a pattern that
    reached across the whole token fails here.
    """
    (pattern,) = colour_patterns()
    match = re.search(pattern, text)

    if match is None:
        return
    assert misspelling not in match.group(0), f"{pattern!r} also masks {misspelling!r}"


@pytest.mark.parametrize(("text", "misspelling"), PREFIX_RESIDUAL)
def test_a_misspelling_in_the_prefix_is_the_known_residual(text: str, misspelling: str) -> None:
    """A prefix misspelling is hidden: the documented limit of the open prefix."""
    (pattern,) = colour_patterns()
    match = re.search(pattern, text)

    assert match is not None
    assert misspelling in match.group(0)


def run_consumer_gate(repository: Path, files: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the pinned gate for a scratch consumer against this dictionary.

    Parameters
    ----------
    repository
        Empty directory that becomes the scratch consumer repository.
    files
        Repository-relative file names mapped to their contents.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The finished gate process, with its exit code and captured output.
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
def test_a_consumer_passes_on_the_genuine_forms(tmp_path: Path) -> None:
    """A consumer documenting the genuine flags and properties needs no exemption."""
    forms = ", ".join(f"`{text}`" for text, _ in GENUINE)

    result = run_consumer_gate(tmp_path, {"guide.md": f"The forms are {forms}.\n"})

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.slow
@pytest.mark.parametrize(("text", "misspelling"), CONSUMER_REPORTED)
def test_a_consumer_gate_reports_the_misspelt_flag(
    tmp_path: Path, text: str, misspelling: str
) -> None:
    """A consumer's prose with a misspelling in a flag-shaped token is reported."""
    result = run_consumer_gate(tmp_path, {"guide.md": f"Pass `{text}` to the tool.\n"})

    assert result.returncode == 2, result.stdout + result.stderr
    assert misspelling in result.stdout + result.stderr, (
        "the gate failed without naming the misspelt word"
    )
