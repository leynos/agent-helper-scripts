"""Merge a repository's local spelling overlay into the shared policy.

A local overlay may add words, corrections and masking patterns, and may
withdraw shared ignore patterns. It may not weaken the shared policy: a
correction that contradicts the base, or an exclusion broad enough to skip the
repository's own prose, is rejected here rather than merged quietly.

Examples
--------
Merge an overlay into a validated base::

    from typos_rollout_merge import merge_dictionaries
    from typos_rollout_policy import Dictionary

    policy = merge_dictionaries(base, Dictionary(accepted=("oxendict",)))
"""

from typos_rollout_policy import Dictionary, validate_local_exceptions


def _merge_correction_items(
    base: tuple[tuple[str, str], ...],
    local: tuple[tuple[str, str], ...],
    *,
    label: str,
) -> tuple[tuple[str, str], ...]:
    """Merge corrections while rejecting conflicting replacements."""
    merged = dict(base)
    for source, correction in local:
        existing = merged.get(source)
        if existing is not None and existing != correction:
            message = (
                f"conflicting {label} for {source!r}: "
                f"{existing!r} != {correction!r}"
            )
            raise ValueError(message)
        merged[source] = correction
    return tuple(sorted(merged.items()))


def _merge_ignore_patterns(base: Dictionary, local: Dictionary) -> tuple[str, ...]:
    """Merge ignore patterns, then apply explicit local withdrawals."""
    removed = set(local.removed_patterns)
    contradictory = removed & set(local.ignore_patterns)
    if contradictory:
        message = (
            "local overlay both ignores and removes patterns: "
            f"{', '.join(sorted(contradictory))}"
        )
        raise ValueError(message)
    return tuple(
        sorted((set(base.ignore_patterns) | set(local.ignore_patterns)) - removed)
    )


def merge_dictionaries(base: Dictionary, local: Dictionary) -> Dictionary:
    """Merge a shared dictionary with a non-conflicting local overlay.

    Parameters
    ----------
    base
        Complete shared spelling policy.
    local
        Sparse repository-specific policy additions.

    Returns
    -------
    Dictionary
        Deterministically ordered union of both policies.

    Raises
    ------
    ValueError
        If corrections conflict or local exceptions weaken shared policy.
    """
    validate_local_exceptions(
        local.ignore_patterns,
        local.excluded_files,
    )
    return Dictionary(
        stems=tuple(sorted(set(base.stems) | set(local.stems))),
        accepted=tuple(sorted(set(base.accepted) | set(local.accepted))),
        corrections=_merge_correction_items(
            base.corrections,
            local.corrections,
            label="correction",
        ),
        phrase_corrections=_merge_correction_items(
            base.phrase_corrections,
            local.phrase_corrections,
            label="phrase correction",
        ),
        ignore_patterns=_merge_ignore_patterns(base, local),
        removed_patterns=tuple(
            sorted(set(base.removed_patterns) | set(local.removed_patterns))
        ),
        excluded_files=tuple(
            sorted(set(base.excluded_files) | set(local.excluded_files))
        ),
    )
