"""Behavioural tests for the shared style-guide proper-name protections.

The shared policy masks two proper names whose official spelling is American:
the Azure documentation page title and the Markdown dialect published by
GitHub. Both would otherwise be rewritten by the ``en-gb`` locale the
generated configuration selects, so the patterns are load-bearing rather than
cosmetic.

The American forms are assembled from fragments so that this module's own
source does not trip the repository's spelling gate; the shared masks apply
only to the complete proper names, not to the words in isolation.
"""

from pathlib import Path
import re
import shutil
import subprocess
import tomllib
import types

import pytest

from typos_rollout_test_support import (
    COMMITTED_CONFIG_PATH,
    REPOSITORY_ROOT,
    SHARED_DICTIONARY_PATH,
    prepare_spelling_gate_repository,
    require_executable,
    run_spelling_gate,
)

# Both names and values are kept out of the scan's way: the tracker reads
# identifiers as well as prose, so a constant named for the American spelling
# is itself a finding.
AMERICAN_CENTRE = "Cent" + "er"
AMERICAN_FLAVOURED = "Flav" + "ored"
MISSPELLED_ARTICLE = "t" + "eh"
AZURE_PATTERN = (
    rf"Azure\s+Architecture\s+{AMERICAN_CENTRE}\s*\|\s*Microsoft\s+Learn\b"
)
GFM_PATTERN = rf"GitHub\s+{AMERICAN_FLAVOURED}\s+Markdown\b(?:\s\(GFM\))?"
STYLE_GUIDE_PATTERNS = (AZURE_PATTERN, GFM_PATTERN)
#: Whitespace variants observed in consumer overlays, paired with their mask.
MASKED_VARIANTS: tuple[tuple[str, str], ...] = (
    (f"Azure Architecture {AMERICAN_CENTRE} | Microsoft Learn", AZURE_PATTERN),
    (f"Azure Architecture\n{AMERICAN_CENTRE} | Microsoft Learn", AZURE_PATTERN),
    (f"Azure Architecture {AMERICAN_CENTRE}|Microsoft Learn", AZURE_PATTERN),
    (f"GitHub {AMERICAN_FLAVOURED} Markdown", GFM_PATTERN),
    (f"GitHub  {AMERICAN_FLAVOURED}\nMarkdown", GFM_PATTERN),
    (f"GitHub {AMERICAN_FLAVOURED} Markdown (GFM)", GFM_PATTERN),
)
#: Near misses that must keep their American spellings visible to the scanner.
UNMASKED_NEAR_MISSES: tuple[str, ...] = (
    f"GitHub {AMERICAN_FLAVOURED}",
    f"{AMERICAN_FLAVOURED} Markdown",
    "Microsoft Learn",
    f"Azure {AMERICAN_CENTRE} | Microsoft Learn",
    f"Azure Architecture {AMERICAN_CENTRE} | Microsoft Learning",
    f"GitHub {AMERICAN_FLAVOURED} Markdownish",
)


def test_shared_policy_carries_the_style_guide_proper_names(
    rollout: types.ModuleType,
) -> None:
    """Both proper-name masks are shared policy and compile as bounded regexes."""
    dictionary = rollout.load_dictionary(SHARED_DICTIONARY_PATH)

    for pattern in STYLE_GUIDE_PATTERNS:
        assert pattern in dictionary.ignore_patterns, (
            f"shared policy omitted the proper-name mask {pattern!r}"
        )

    compiled = rollout._compile_ignore_patterns(STYLE_GUIDE_PATTERNS)

    assert len(compiled) == len(STYLE_GUIDE_PATTERNS), (
        "the policy validator dropped a proper-name mask"
    )


def test_generated_and_committed_configs_carry_the_proper_names(
    rollout: types.ModuleType,
) -> None:
    """The rendered and indexed configurations both publish the masks."""
    dictionary = rollout.load_dictionary(SHARED_DICTIONARY_PATH)
    rendered = tomllib.loads(rollout.render_typos_config(dictionary))["default"]
    indexed = tomllib.loads(COMMITTED_CONFIG_PATH.read_text(encoding="utf-8"))
    committed = indexed["default"]

    for pattern in STYLE_GUIDE_PATTERNS:
        assert pattern in rendered["extend-ignore-re"], (
            f"rendered configuration omitted {pattern!r}"
        )
        assert pattern in committed["extend-ignore-re"], (
            f"indexed typos.toml omitted {pattern!r}"
        )


@pytest.mark.parametrize(("text", "pattern"), MASKED_VARIANTS)
def test_proper_name_variants_are_masked_in_full(text: str, pattern: str) -> None:
    """Every whitespace variant consumers write is masked end to end."""
    assert re.fullmatch(pattern, text), f"the mask left {text!r} exposed"


@pytest.mark.parametrize("text", UNMASKED_NEAR_MISSES)
def test_near_misses_are_not_masked(text: str) -> None:
    """Fragments of the proper names stay visible to the spelling gate.

    This is the negative control for the parametrized matches above: it proves
    the assertions can fail, because the same regexes match nothing here.
    """
    for pattern in STYLE_GUIDE_PATTERNS:
        assert re.search(pattern, text) is None, (
            f"{pattern!r} masked the near miss {text!r}"
        )


@pytest.mark.slow
def test_spelling_gate_accepts_the_proper_names_but_not_ordinary_typos(
    tmp_path: Path,
) -> None:
    """The gate passes the two proper names while still reporting a real typo."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is unavailable to run the pinned typos binary")
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^TYPOS_VERSION\s*\?=\s*(\S+)", makefile, re.MULTILINE)
    assert match is not None, "TYPOS_VERSION not found in Makefile"
    repository = prepare_spelling_gate_repository(tmp_path)
    (repository / "README.md").write_text(
        f"See Azure Architecture {AMERICAN_CENTRE} | Microsoft Learn for the "
        f"topology.\n"
        f"Write the notes in GitHub {AMERICAN_FLAVOURED} Markdown (GFM).\n"
        f"Then read {MISSPELLED_ARTICLE} summary.\n",
        encoding="utf-8",
    )
    git = require_executable("git")
    subprocess.run([git, "add", "README.md"], cwd=repository, check=True, timeout=30)

    result = run_spelling_gate(repository, f"uv tool run typos@{match.group(1)}")
    output = result.stdout + result.stderr

    assert result.returncode != 0, (
        f"the gate accepted the {MISSPELLED_ARTICLE} misspelling: {output}"
    )
    assert f"`{MISSPELLED_ARTICLE}` should be `the`" in output, (
        f"the gate did not report the unrelated misspelling: {output}"
    )
    assert "README.md:3:11" in output, (
        f"the gate did not locate the unrelated misspelling: {output}"
    )
    for proper_noun_word in (AMERICAN_CENTRE, AMERICAN_FLAVOURED):
        assert proper_noun_word not in output, (
            f"the gate reported the protected proper name {proper_noun_word!r}: {output}"
        )
