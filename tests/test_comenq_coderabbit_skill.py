"""Contract and decision tests for the comenq-coderabbit skill.

The workflow is prose, so there is no runtime implementation to exercise and
no queue or GitHub behaviour is touched here. These tests hold two contracts
instead:

- The document contract keeps the routing, candidate-evidence, surface
  retrieval, disposition, convergence, and installation rules the workflow
  relies on, across the skill, its references, the users' guide, and the
  migration guide. Negative controls mutate each document in memory to show
  the contract rejects a missing rule.
- The decision contract encodes the documented dispositions for representative
  offline rehearsal cases as an executable specification. Every classification
  cites the skill sentence that states it, and the document contract asserts
  those sentences are still present, so deleting a rule fails the tests.

These tests detect drift between the skill and the decisions the workflow
relies on. They do not prove that an agent follows the skill, and they make no
claim about live queue, reviewer, or integration behaviour.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "comenq-coderabbit"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
FAILURE_MODES_PATH = SKILL_ROOT / "references" / "failure-modes-and-recovery.md"
EVIDENCE_PATH = SKILL_ROOT / "references" / "evidence-and-rehearsal.md"
USERS_GUIDE_PATH = REPO_ROOT / "docs" / "users-guide.md"
MIGRATION_GUIDE_PATH = REPO_ROOT / "docs" / "migration-guide.md"

SKILL_NAME = "comenq-coderabbit"
SKILL_LINK = "../skills/comenq-coderabbit/SKILL.md"
FAILURE_MODES_LINK = (
    "../skills/comenq-coderabbit/references/failure-modes-and-recovery.md"
)
EVIDENCE_LINK = (
    "../skills/comenq-coderabbit/references/evidence-and-rehearsal.md"
)

REQUIRED_DESCRIPTION_TRIGGERS = (
    "review requests",
    "duplicate reviews",
    "clone or service failures",
    "stale pre-merge tables",
    "stale CHANGES_REQUESTED decisions",
    "agent-team triage and remediation",
)

REQUIRED_SKILL_HEADINGS = (
    "## Connection and routing",
    "## The review-response loop",
    "## Delegate verification, repair, and validation",
    "## Collect all review surfaces",
    "## Dispositions and convergence",
    "## Installation boundary",
)

#: Each entry is a rule the workflow depends on and the sentence stating it.
#: `_validate_skill_contract` requires every sentence to remain in the skill.
REQUIRED_SKILL_RULES = {
    "queue-first routing": (
        "Do not send a new full review through a direct GitHub comment or a "
        "personal bot identity."
    ),
    "authorized focused replies": (
        "Focused replies to existing findings or pre-merge rows are a different "
        "operation: use only the project's already authorized reply route and "
        "identity."
    ),
    "candidate-bound evidence": (
        "The comment body does not pin a review to a commit: verify the commit "
        "that CodeRabbit actually inspected after it runs."
    ),
    "incomplete inspection": (
        "A clone failure, missing required inspection, or inconclusive check "
        "cannot establish a clean review."
    ),
    "complete surface retrieval": (
        "Paginate the entire thread list and, where necessary, each thread's "
        "comments; outer pagination does not complete a capped inner connection."
    ),
    "warning dispositions": (
        "Treat both warning and error rows as requiring an explicit disposition; "
        "warnings are not optional or aspirational."
    ),
    "review-state separation": (
        "Resolved inline threads and no new comments do not imply `APPROVED`; "
        "stale `CHANGES_REQUESTED` needs explicit reconciliation and read-back."
    ),
    "convergence": (
        "Convergence requires evidence-backed dispositions for all required "
        "findings, adequate completed inspection of the candidate, the required "
        "current review state, and green required checks on the intended head."
    ),
    "stale candidate handling": (
        "After any rebase, server replay, or relevant new commit, record the new "
        "base/head and treat previous merge eligibility as stale."
    ),
    "separate integration verification": (
        "A green PR or approval cannot discharge a failing main job."
    ),
    "no gate bypass": (
        "Do not tick an Ignore checkbox, suppress a required check, dismiss a "
        "review, manually approve on the bot's behalf, or bypass branch "
        "protection to make the status look green."
    ),
    "installation boundary": (
        "Before rollout, compare any independently installed copy with this "
        "distribution and choose one authoritative version."
    ),
}

QUEUE_INTERFACE = "`list`, `put`, `hist`, and `del`"
QUEUE_EXAMPLES = (
    "comenq list",
    "comenq hist -n 20",
    "comenq put OWNER/REPO PR_NUMBER",
)

FAILURE_MODE_CASE_COUNT = 10
#: Prefixes rather than exact strings: a case may record one incident or several.
FAILURE_MODE_MARKERS = ("**Recorded incident", "**Recovery:**", "**Exit evidence:**")

REHEARSAL_SCENARIO_COUNT = 17

#: The two reconciliation templates are supplied text; preserve them verbatim.
SUPPLIED_TEMPLATES = (
    """@coderabbitai Have the following failed checks now been resolved?

If further work is required, please provide an AI agent prompt for the remaining work to be done to address these failures.

Do not treat warnings as optional or aspirational. Where a change is out of scope for this PR, propose a GitHub issue unless one exists already. (Treat o11y, code safety, documentation and validation coverage as in scope).

<table rows here, with heading>""",
    """@coderabbitai Has this now been resolved in the latest commit?

Use codegraph analysis to determine your answer.

If this comment is now resolved, please mark it as such using the API. Otherwise, please provide an AI agent prompt for the remaining work to be done to address this comment.""",
)

INCIDENT_LINKS = (
    "https://github.com/leynos/ortho-config/pull/486",
    "https://github.com/leynos/cuprum/pull/382",
    "https://github.com/leynos/cuprum/pull/385",
    "https://github.com/leynos/vtcode/pull/106",
    "https://github.com/leynos/concordat/pull/159",
)

USERS_GUIDE_HEADING = "## CodeRabbit reviews via comenq"
MIGRATION_GUIDE_HEADING = "## CodeRabbit review skill"

STATE_DIAGRAM = """\
stateDiagram-v2
    [*] --> CandidatePrepared
    CandidatePrepared --> RequestPending: comenq put
    CandidatePrepared --> ReviewActivityFound: existing activity
    RequestPending --> ReviewPosted
    RequestPending --> RequestFailed
    RequestFailed --> InspectionIncomplete
    ReviewPosted --> InspectionComplete
    ReviewActivityFound --> InspectionComplete: current candidate and scope verified
    InspectionComplete --> FindingsPending
    FindingsPending --> DispositionsComplete: fix, rebut, or scope findings
    DispositionsComplete --> ReviewStateReconciled: threads and rows read back
    ReviewStateReconciled --> MergeEligible: approval and required checks on head
    ReviewStateReconciled --> CandidateStale: rebase or later commit
    CandidateStale --> CandidatePrepared
    MergeEligible --> Merged
    Merged --> IntegrationVerified
    Merged --> IntegrationFailed
    IntegrationFailed --> Andon
    InspectionIncomplete --> Andon
    Andon --> [*]
    IntegrationVerified --> [*]
"""

_LINK_RE = re.compile(r"\[[^\]]*\]\((?P<target>[^)\s]+)\)")
_HEADING_RE = re.compile(r"^#{1,6}[ \t]+(?P<title>.+?)[ \t]*$", re.MULTILINE)
_LEVEL_TWO_RE = re.compile(r"^## (?P<title>.+)$", re.MULTILINE)
_SCENARIO_RE = re.compile(r"^(?P<number>\d+)\. \*\*", re.MULTILINE)


def _read(path: Path) -> str:
    """Read one repository contract file."""
    return path.read_text(encoding="utf-8")


def _normalize(markdown: str) -> str:
    """Collapse Markdown line wrapping before checking prose requirements."""
    return " ".join(markdown.split())


def _frontmatter(content: str) -> tuple[dict[str, object], str]:
    """Return the skill's YAML front matter and body."""
    assert content.startswith("---\n"), (
        "the comenq-coderabbit skill must open with the YAML frontmatter "
        "delimiter, with no leading prose"
    )
    parts = content.split("---", maxsplit=2)
    assert len(parts) == 3, "the comenq-coderabbit skill must have YAML frontmatter"
    parsed = yaml.safe_load(parts[1])
    assert isinstance(parsed, dict), "the skill frontmatter must be a YAML mapping"
    return parsed, parts[2]


def _section(markdown: str, heading: str) -> str:
    """Return the body of one level-2 section, up to the next level-2 heading."""
    _, separator, remainder = markdown.partition(f"{heading}\n")
    assert separator, f"the document must define the {heading!r} section"
    body, _, _ = remainder.partition("\n## ")
    return body


def _slugify(heading: str) -> str:
    """Return the GitHub anchor for one Markdown heading."""
    lowered = re.sub(r"[`*_]", "", heading.strip().lower())
    return re.sub(r"[^a-z0-9\- ]", "", lowered).replace(" ", "-")


def _assert_links_resolve(markdown: str, source: Path, document_name: str) -> None:
    """Require every repository-relative link and anchor to resolve."""
    for target in _LINK_RE.findall(markdown):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path_part, _, anchor = target.partition("#")
        resolved = source if not path_part else (source.parent / path_part).resolve()
        assert resolved.is_file(), (
            f"the {document_name} must link to an existing file: {target}"
        )
        if anchor:
            headings = {
                _slugify(title)
                for title in _HEADING_RE.findall(resolved.read_text(encoding="utf-8"))
            }
            assert anchor in headings, (
                f"the {document_name} anchor {anchor!r} must resolve in "
                f"{resolved.name}"
            )


def _level_two_blocks(markdown: str) -> list[str]:
    """Return each level-2 section body, excluding any preamble."""
    return re.split(r"^## ", markdown, flags=re.MULTILINE)[1:]


def _without(document: str, text: str) -> str:
    """Remove one wrapped prose passage, tolerating the document's line breaks."""
    pattern = re.compile(r"\s+".join(map(re.escape, text.split())))
    mutated, replacements = pattern.subn("", document, count=1)
    assert replacements == 1, f"the negative control must find {text!r} to remove"
    return mutated


def _validate_skill_contract(
    skill: str, failure_modes: str, evidence: str
) -> None:
    """Validate the review workflow's document contract."""
    frontmatter, _ = _frontmatter(skill)
    assert frontmatter.get("name") == SKILL_NAME, (
        "the skill name must match its directory so discovery resolves it"
    )
    description = frontmatter.get("description")
    assert isinstance(description, str), "the skill must declare a description"
    normalized_description = _normalize(description)
    for trigger in REQUIRED_DESCRIPTION_TRIGGERS:
        assert trigger in normalized_description, (
            f"discovery metadata must advertise {trigger!r}"
        )

    for heading in REQUIRED_SKILL_HEADINGS:
        assert heading in skill, f"the skill must retain the {heading!r} section"

    normalized_skill = _normalize(skill)
    for rule, sentence in REQUIRED_SKILL_RULES.items():
        assert _normalize(sentence) in normalized_skill, (
            f"the skill must retain the {rule} rule: `{sentence}`"
        )

    assert QUEUE_INTERFACE in normalized_skill, (
        "the skill must name the managed queue interface it depends on"
    )
    for example in QUEUE_EXAMPLES:
        assert example in skill, f"the skill must document `{example}`"

    _assert_links_resolve(skill, SKILL_PATH, "comenq-coderabbit skill")
    _validate_failure_modes(failure_modes)
    _validate_evidence(evidence)


def _validate_failure_modes(failure_modes: str) -> None:
    """Require every recovery case to keep its incident, recovery, and evidence."""
    titles = _LEVEL_TWO_RE.findall(failure_modes)
    assert len(titles) == FAILURE_MODE_CASE_COUNT, (
        f"the recovery reference must keep {FAILURE_MODE_CASE_COUNT} cases, "
        f"found {len(titles)}: {titles}"
    )
    for block in _level_two_blocks(failure_modes):
        for marker in FAILURE_MODE_MARKERS:
            assert marker in block, (
                f"every recovery case must keep its {marker} evidence"
            )
    _assert_links_resolve(
        failure_modes, FAILURE_MODES_PATH, "failure-mode reference"
    )


def _validate_evidence(evidence: str) -> None:
    """Require the supplied templates, the scenarios, and the source links."""
    for template in SUPPLIED_TEMPLATES:
        assert template in evidence, (
            "the evidence reference must preserve a supplied reconciliation "
            "template verbatim"
        )

    scenarios = [int(number) for number in _SCENARIO_RE.findall(evidence)]
    assert scenarios == list(range(1, REHEARSAL_SCENARIO_COUNT + 1)), (
        "the offline rehearsal scenarios must stay a complete, sequential "
        f"1-{REHEARSAL_SCENARIO_COUNT} list, found {scenarios}"
    )

    for link in INCIDENT_LINKS:
        assert link in evidence, f"the incident sources must keep {link}"

    _assert_links_resolve(evidence, EVIDENCE_PATH, "evidence reference")


def _validate_users_guide(users_guide: str) -> None:
    """Require the user-facing entry, its links, and the captioned diagram."""
    section = _section(users_guide, USERS_GUIDE_HEADING)
    normalized = _normalize(section)

    for link in (SKILL_LINK, FAILURE_MODES_LINK, EVIDENCE_LINK):
        assert link in section, f"the users' guide must link to {link}"
    assert "install-skills" in normalized, (
        "the users' guide must state the skill's installation path"
    )
    for example in ("comenq list", "comenq put"):
        assert example in section, f"the users' guide must show `{example}`"
    assert "already authorized reply route" in normalized, (
        "the users' guide must state the authorized queue boundary"
    )

    diagram = f"```mermaid\n{STATE_DIAGRAM}```"
    assert diagram in section, (
        "the users' guide must carry the supplied review-lifecycle state diagram"
    )

    caption = section.partition("```\n\nFigure 1:")[2]
    assert caption, "the state diagram must be followed by its figure caption"
    normalized_caption = _normalize(caption)
    assert "review lifecycle" in normalized_caption, (
        "the caption must name the lifecycle it describes"
    )
    assert "andon" in normalized_caption, (
        "the caption must describe the andon outcomes the diagram shows"
    )


def _validate_migration_guide(migration_guide: str) -> None:
    """Require the migration entry to signpost the skill and its rollout rule."""
    section = _section(migration_guide, MIGRATION_GUIDE_HEADING)
    normalized = _normalize(section)

    assert SKILL_LINK in section, "the migration entry must link to the skill"
    assert "install-skills" in normalized, (
        "the migration entry must state why two copies can coexist"
    )
    assert "one authoritative version" in normalized, (
        "the migration entry must require choosing an authoritative version"
    )


# --------------------------------------------------------------------------
# Document contract
# --------------------------------------------------------------------------


def test_skill_document_contract() -> None:
    """The skill, its references, and the guides keep the documented rules."""
    _validate_skill_contract(
        _read(SKILL_PATH), _read(FAILURE_MODES_PATH), _read(EVIDENCE_PATH)
    )
    _validate_users_guide(_read(USERS_GUIDE_PATH))
    _validate_migration_guide(_read(MIGRATION_GUIDE_PATH))


def test_contract_rejects_missing_installation_boundary() -> None:
    """Removing the installation boundary section must fail the contract."""
    skill = _read(SKILL_PATH).replace("## Installation boundary", "## Deployment", 1)

    with pytest.raises(AssertionError, match=re.escape("## Installation boundary")):
        _validate_skill_contract(
            skill, _read(FAILURE_MODES_PATH), _read(EVIDENCE_PATH)
        )


def test_contract_rejects_missing_queue_routing_rule() -> None:
    """Removing the queue-first routing rule must fail the contract."""
    skill = _without(
        _read(SKILL_PATH), REQUIRED_SKILL_RULES["queue-first routing"]
    )

    with pytest.raises(AssertionError, match=re.escape("queue-first routing")):
        _validate_skill_contract(
            skill, _read(FAILURE_MODES_PATH), _read(EVIDENCE_PATH)
        )


def test_contract_rejects_missing_recovery_evidence() -> None:
    """Removing an exit-evidence marker must fail the contract."""
    failure_modes = _read(FAILURE_MODES_PATH).replace("**Exit evidence:**", "", 1)

    with pytest.raises(AssertionError, match=re.escape("**Exit evidence:**")):
        _validate_skill_contract(
            _read(SKILL_PATH), failure_modes, _read(EVIDENCE_PATH)
        )


def test_contract_rejects_missing_rehearsal_scenario() -> None:
    """Renumbering the rehearsal scenarios must fail the contract."""
    evidence = _read(EVIDENCE_PATH).replace("17. **Uncertain comment", "18. **Uncertain comment", 1)

    with pytest.raises(AssertionError, match="sequential"):
        _validate_skill_contract(
            _read(SKILL_PATH), _read(FAILURE_MODES_PATH), evidence
        )


def test_contract_rejects_missing_users_guide_section() -> None:
    """Removing the users' guide entry must fail the contract."""
    users_guide = _read(USERS_GUIDE_PATH).replace(USERS_GUIDE_HEADING, "## Reviews", 1)

    with pytest.raises(AssertionError, match=re.escape(USERS_GUIDE_HEADING)):
        _validate_users_guide(users_guide)


def test_contract_rejects_missing_state_diagram() -> None:
    """Removing the state diagram must fail the contract."""
    users_guide = _read(USERS_GUIDE_PATH).replace(STATE_DIAGRAM, "", 1)

    with pytest.raises(AssertionError, match="state diagram"):
        _validate_users_guide(users_guide)


def test_contract_rejects_missing_migration_entry() -> None:
    """Removing the migration entry must fail the contract."""
    migration_guide = _read(MIGRATION_GUIDE_PATH).replace(
        "one authoritative version", "a version", 1
    )

    with pytest.raises(AssertionError, match="authoritative"):
        _validate_migration_guide(migration_guide)


# --------------------------------------------------------------------------
# Decision contract
# --------------------------------------------------------------------------

INSPECTION_INCOMPLETE = "inspection-incomplete"
RETRIEVAL_INCOMPLETE = "surface-retrieval-incomplete"
CANDIDATE_STALE = "candidate-stale"
DUPLICATE_REQUEST = "duplicate-request"
DISPOSITIONS_PENDING = "dispositions-pending"
REVIEW_STATE_UNRESOLVED = "review-state-unresolved"
CHECKS_NOT_GREEN = "checks-not-green"
MERGE_ELIGIBLE = "merge-eligible"
INTEGRATION_FAILED = "integration-failed"

#: The sentence in the skill that states each documented disposition. The
#: document contract asserts these are present, so a classification cannot
#: outlive the rule it applies.
VERDICT_CITATIONS = {
    INSPECTION_INCOMPLETE: REQUIRED_SKILL_RULES["incomplete inspection"],
    RETRIEVAL_INCOMPLETE: (
        "An absent reply in a partial page is not proof of an unanswered thread."
    ),
    CANDIDATE_STALE: REQUIRED_SKILL_RULES["stale candidate handling"],
    DUPLICATE_REQUEST: "Reuse an existing request rather than adding another.",
    DISPOSITIONS_PENDING: (
        "Treat both warning and error rows as requiring an explicit disposition"
    ),
    REVIEW_STATE_UNRESOLVED: REQUIRED_SKILL_RULES["review-state separation"],
    CHECKS_NOT_GREEN: "green required checks on the intended head",
    MERGE_ELIGIBLE: REQUIRED_SKILL_RULES["convergence"],
    INTEGRATION_FAILED: REQUIRED_SKILL_RULES["separate integration verification"],
}


@dataclass(frozen=True)
class ReviewObservation:
    """Observed review facts for one candidate, named after the skill surfaces."""

    head: str
    inspected: str | None
    coverage_complete: bool
    retrieval_complete: bool
    request_state: str
    review_activity: bool
    unresolved_threads: int
    undispositioned_rows: int
    review_decision: str
    required_checks_green: bool
    integration: str | None


@dataclass(frozen=True)
class Rehearsal:
    """One documented rehearsal case and the disposition it must produce."""

    scenario: int | None
    description: str
    observation: ReviewObservation
    expected: str


def _observation(
    *,
    head: str = "head1",
    inspected: str | None = "head1",
    coverage_complete: bool = True,
    retrieval_complete: bool = True,
    request_state: str = "posted",
    review_activity: bool = True,
    unresolved_threads: int = 0,
    undispositioned_rows: int = 0,
    review_decision: str = "APPROVED",
    required_checks_green: bool = True,
    integration: str | None = None,
) -> ReviewObservation:
    """Return a fully converged review state with selected facts overridden."""
    return ReviewObservation(
        head=head,
        inspected=inspected,
        coverage_complete=coverage_complete,
        retrieval_complete=retrieval_complete,
        request_state=request_state,
        review_activity=review_activity,
        unresolved_threads=unresolved_threads,
        undispositioned_rows=undispositioned_rows,
        review_decision=review_decision,
        required_checks_green=required_checks_green,
        integration=integration,
    )


def classify(observation: ReviewObservation) -> str:
    """Return the documented disposition for one observed review state.

    Order matters and follows the skill: integration is verified separately
    from the pull request, an incomplete inspection can never be a clean
    review, a changed candidate invalidates earlier eligibility before any
    duplicate or disposition question is answered, and a pending request is
    redundant only once the current candidate's inspection is complete.
    """
    if observation.integration == "failed":
        return INTEGRATION_FAILED
    if not observation.coverage_complete:
        return INSPECTION_INCOMPLETE
    if not observation.retrieval_complete:
        return RETRIEVAL_INCOMPLETE
    if observation.inspected is not None and observation.inspected != observation.head:
        return CANDIDATE_STALE
    if observation.request_state == "pending" and observation.review_activity:
        return DUPLICATE_REQUEST
    if observation.unresolved_threads or observation.undispositioned_rows:
        return DISPOSITIONS_PENDING
    if observation.review_decision != "APPROVED":
        return REVIEW_STATE_UNRESOLVED
    if not observation.required_checks_green:
        return CHECKS_NOT_GREEN
    return MERGE_ELIGIBLE


REHEARSALS = (
    Rehearsal(
        scenario=1,
        description="clone failed with no findings is incomplete inspection",
        observation=_observation(
            coverage_complete=False, review_decision="REVIEW_REQUIRED"
        ),
        expected=INSPECTION_INCOMPLETE,
    ),
    Rehearsal(
        scenario=None,
        description="a completed review on the current candidate converges",
        observation=_observation(),
        expected=MERGE_ELIGIBLE,
    ),
    Rehearsal(
        scenario=2,
        description="approval with unknown required coverage still holds merge",
        observation=_observation(
            coverage_complete=False, review_decision="APPROVED"
        ),
        expected=INSPECTION_INCOMPLETE,
    ),
    Rehearsal(
        scenario=3,
        description="a pending request is redundant beside completed activity",
        observation=_observation(request_state="pending", review_activity=True),
        expected=DUPLICATE_REQUEST,
    ),
    Rehearsal(
        scenario=5,
        description="four rows for two defects stay undispositioned work",
        observation=_observation(undispositioned_rows=4),
        expected=DISPOSITIONS_PENDING,
    ),
    Rehearsal(
        scenario=8,
        description="resolved threads do not clear stale CHANGES_REQUESTED",
        observation=_observation(review_decision="CHANGES_REQUESTED"),
        expected=REVIEW_STATE_UNRESOLVED,
    ),
    Rehearsal(
        scenario=9,
        description="a replayed candidate invalidates earlier eligibility",
        observation=_observation(inspected="old1", head="new1"),
        expected=CANDIDATE_STALE,
    ),
    Rehearsal(
        scenario=10,
        description="a capped inner comment page is incomplete retrieval",
        observation=_observation(retrieval_complete=False),
        expected=RETRIEVAL_INCOMPLETE,
    ),
    Rehearsal(
        scenario=12,
        description="a green pull request cannot discharge a failing main job",
        observation=_observation(integration="failed"),
        expected=INTEGRATION_FAILED,
    ),
    Rehearsal(
        scenario=None,
        description="required checks on the intended head gate merge eligibility",
        observation=_observation(required_checks_green=False),
        expected=CHECKS_NOT_GREEN,
    ),
)


@pytest.mark.parametrize(
    "rehearsal",
    REHEARSALS,
    ids=[rehearsal.description for rehearsal in REHEARSALS],
)
def test_documented_decisions_for_rehearsal_cases(rehearsal: Rehearsal) -> None:
    """Each recorded rehearsal case produces its documented disposition."""
    assert classify(rehearsal.observation) == rehearsal.expected


def test_every_classification_cites_a_rule_the_skill_states() -> None:
    """No classification may outlive the skill sentence that grounds it."""
    normalized_skill = _normalize(_read(SKILL_PATH))
    for verdict, citation in VERDICT_CITATIONS.items():
        assert _normalize(citation) in normalized_skill, (
            f"the {verdict} classification must stay grounded in the skill: "
            f"`{citation}`"
        )


def test_rehearsal_fixtures_reference_documented_scenarios() -> None:
    """Every fixture that names a scenario must name a documented one."""
    documented = {
        int(number) for number in _SCENARIO_RE.findall(_read(EVIDENCE_PATH))
    }
    used = {
        rehearsal.scenario
        for rehearsal in REHEARSALS
        if rehearsal.scenario is not None
    }
    assert used, "at least one fixture must be tied to a documented scenario"
    assert used <= documented, (
        f"fixtures must reference documented scenarios, unknown: "
        f"{sorted(used - documented)}"
    )


def test_clone_failure_cannot_be_reported_as_a_clean_review() -> None:
    """Incomplete coverage must never classify as merge eligible."""
    observation = _observation(
        coverage_complete=False, review_decision="REVIEW_REQUIRED"
    )

    assert classify(observation) != MERGE_ELIGIBLE
    assert classify(observation) == INSPECTION_INCOMPLETE


def test_approval_on_a_superseded_candidate_is_not_merge_eligible() -> None:
    """An approval inspected an earlier candidate, so eligibility is stale."""
    observation = _observation(inspected="old1", head="new1")

    assert classify(observation) == CANDIDATE_STALE


def test_green_pull_request_does_not_discharge_a_failing_integration_job() -> None:
    """Integration state is checked before any pull-request convergence."""
    observation = _observation(integration="failed")

    assert classify(observation) == INTEGRATION_FAILED
