"""Verbatim content the comenq-coderabbit contract requires.

Most values here are either text the distribution supplies and must preserve
word for word, or a requirement stated as the exact document wording that
satisfies it; the counts and the scenario fixtures are the exceptions.
Keeping the values in one module lets the focused test modules assert against
them without duplicating any of the text.
"""

from __future__ import annotations

from dataclasses import dataclass

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
#: `validate_skill_contract` requires every sentence to remain in the skill.
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
    "current-code verification": (
        "Use a wyvern agent team to verify every inline finding and pre-merge row "
        "against the current code before editing."
    ),
    "role assignment for large sets": (
        "For large volumes of verified findings, use journeyman and "
        "artisan/scribe agent teams."
    ),
    "role ownership split": (
        "Journeymen own substantive implementation repairs; scribes own "
        "documentation repairs; artisans handle repeated mechanical changes that "
        "need an agent."
    ),
    "scrutineer execution role": (
        "Use a scrutineer agent for execution of tests and summarizing the "
        "results."
    ),
    "bounded ownership": (
        "Group work by underlying defect and affected boundary, assign bounded "
        "batches with explicit file ownership, and avoid competing edits to the "
        "same files."
    ),
    "codemod scope": (
        "Restrict them to verified findings and owned paths, preview their diff, "
        "and check representative cases before applying a batch."
    ),
    "codemod restraint": (
        "Do not apply a repository-wide replacement merely because several "
        "comments look similar."
    ),
    "sequential gate ownership": (
        "Preserve exclusive sequential ownership of shared build/test resources; "
        "workers must not start competing gates."
    ),
    "uncertainty handling": (
        "Uncertainty is not a reason to mark a finding resolved or silently "
        "discard it: keep it pending"
    ),
}

#: Rules that assign work to a named agent role, and the role each names.
REQUIRED_AGENT_ROLES = {
    "wyvern": "current-code verification",
    "journeyman": "role assignment for large sets",
    "artisan": "role ownership split",
    "scribe": "role ownership split",
    "scrutineer": "scrutineer execution role",
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
USERS_GUIDE_LINK = "docs/users-guide.md"

#: The README signpost is required as wording, not only as a link: the README
#: must name the queue the workflow routes through.
README_SIGNPOST = "CodeRabbit reviews through the `comenq` queue"

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


@dataclass(frozen=True)
class ScenarioContract:
    """One offline rehearsal scenario and the semantics it must keep stating."""

    number: int
    title: str
    required: tuple[str, ...]


#: Every documented scenario, with the claims that make it a real acceptance
#: check rather than a numbered heading. Phrase matching tolerates wrapping.
REHEARSAL_SCENARIOS = (
    ScenarioContract(
        number=1,
        title="Clone failed, no findings",
        required=(
            "report incomplete inspection, not zero findings or approval",
            "retains its limited scope",
        ),
    ),
    ScenarioContract(
        number=2,
        title="Approval plus service warning",
        required=(
            "identify the missing inspection",
            "hold merge if required coverage remains unknown",
        ),
    ),
    ScenarioContract(
        number=3,
        title="Automatic review and pending request",
        required=(
            "cancel only a genuinely redundant pending ID",
            "verify whether it had already posted",
        ),
    ),
    ScenarioContract(
        number=4,
        title="Wrong direct identity used",
        required=(
            "route subsequent full reviews through the queue",
            "do not try another token as a workaround",
        ),
    ),
    ScenarioContract(
        number=5,
        title="Four rows, two defects",
        required=(
            "plan two bounded repairs",
            "instead of making four unrelated changes",
        ),
    ),
    ScenarioContract(
        number=6,
        title="Percentage changes from Rustdoc to runtime coverage",
        required=(
            "define the population and count",
            "without inventing a number",
        ),
    ),
    ScenarioContract(
        number=7,
        title="Wire name versus unknown input",
        required=(
            "correct the unsupported rejection claim",
            "without altering runtime behaviour merely to match the review "
            "response",
        ),
    ),
    ScenarioContract(
        number=8,
        title="No unresolved threads, CHANGES_REQUESTED remains",
        required=(
            "reconcile metadata and observe the required approval state",
            "do not infer approval or bypass it",
        ),
    ),
    ScenarioContract(
        number=9,
        title="Replayed branch",
        required=(
            "mark prior eligibility stale",
            "never label an earlier review as a new full review",
        ),
    ),
    ScenarioContract(
        number=10,
        title="Capped nested comments and edited walkthrough",
        required=(
            "finish relevant pagination",
            "re-read the edited comment",
        ),
    ),
    ScenarioContract(
        number=11,
        title="Unsafe suggested test",
        required=(
            "keep the valid error-path concern",
            "reject the invalid ownership construction",
            "supply a safe discriminating alternative",
        ),
    ),
    ScenarioContract(
        number=12,
        title="Green PR, main coverage cannot find Conftest",
        required=(
            "record integration failure",
            "route the environment repair to its owner",
            "instead of declaring a service delay or success",
        ),
    ),
    ScenarioContract(
        number=13,
        title="Large mixed finding set",
        required=(
            "wyverns verify each finding on the current candidate",
            "explicit file ownership",
            "uncertain findings stay pending",
        ),
    ),
    ScenarioContract(
        number=14,
        title="Small documentation and mechanical batch",
        required=(
            "use scribes for documentation",
            "prefer automated fixes or codemods for repeated changes",
        ),
    ),
    ScenarioContract(
        number=15,
        title="Codemod and validation handoff",
        required=(
            "preview only verified, owned paths",
            "have one scrutineer execute focused tests and required gates",
            "without upgrading a worker's inspection into a pass",
        ),
    ),
    ScenarioContract(
        number=16,
        title="Pre-merge warning remains",
        required=(
            "use the checks template with the live heading and rows, not the "
            "placeholder",
            "Warnings remain actionable",
            "propose one for genuinely out-of-scope work",
        ),
    ),
    ScenarioContract(
        number=17,
        title="Uncertain comment and unavailable codegraph",
        required=(
            "send the thread template",
            "retain the analysis limitation",
            "without claiming the graph ran",
            "do not infer approval",
        ),
    ),
)
