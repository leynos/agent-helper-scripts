#!/usr/bin/env python3
"""Generate the controlled GitHub facts for each readiness scenario.

The facts are what a real `gh` would return for this repository: the PR's
draft and check state, the CodeRabbit commit status, and the issue-comment
thread carrying the assessment request and its reply. The harness supplies
them through an executable `gh` shim, so the agent under test reads fixed
GitHub facts and the only variable is the assessment evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "scenarios"
BASE = "73d32981c7b7e8f52590a074873e28a9f369f0f9"
REPO = "leynos/agent-helper-scripts"
PR = 272

GREEN = [
    {"name": "Makefile gates", "status": "COMPLETED", "conclusion": "SUCCESS"},
    {
        "name": "CodeScene Code Health Review",
        "status": "COMPLETED",
        "conclusion": "SUCCESS",
    },
    {"name": "Gecko Security Review", "status": "COMPLETED", "conclusion": "SUCCESS"},
]

WHOLE_PLAN = "the whole approved plan"
# The approved plan the assessments are judged against. Its blob SHA is served
# from the contents API so a follow-up request can name the revision in force
# instead of stopping for a value the fixture never supplied.
PLAN_PATH = "docs/execplans/issue-271-readiness-handoff.md"
PLAN_BLOB = "5a1c9e4d7b3f28a06c5e1d9b4f7a2c8e6d0b3f15"
# The file an advisory finding names, and the code it names within it. A
# finding about this candidate has to be about a change this candidate makes.
FLAGGED_PATH = "skills/pr-babysitting/scripts/readiness_gate.py"
# The shape the finding describes: one function holding several independent
# checks, which is why its complexity is over the threshold. It is enough for a
# run to see what the finding is about; it is not a working implementation.
FLAGGED_TEXT = '''"""Read the readiness gate's assessments."""

COMPLETENESS = "completeness"
PROOF = "proof"


def _assess_gate(state: dict, plan: dict, threads: list, proofs: list) -> bool:
    """Return whether every applicable assessment clears for this candidate."""
    if not state:
        return False
    if state.get("isDraft") is True:
        return False
    if plan.get("revision") != state.get("revision"):
        return False
    if plan.get("approved") is not True:
        return False
    for thread in threads:
        if thread.get("isOutdated"):
            continue
        if not thread.get("isResolved"):
            return False
        if thread.get("assessment") == PROOF:
            if not thread.get("cleared"):
                return False
        elif thread.get("assessment") == COMPLETENESS:
            if thread.get("subject") != plan.get("subject"):
                return False
        elif thread.get("verdict") != "clear":
            return False
    for proof in proofs:
        if proof.get("changed") and not proof.get("scrutinized"):
            return False
    return True
'''
PLAN_TEXT = """# Readiness handoff

Plan revision: rev-7
"""
DECLARED_SUBSET = (
    "the declared subset (milestones EP-M1 and EP-M2 only); the whole approved"
    " plan is not cleared by this reply"
)


def comment(ident: int, login: str, body: str, created: str) -> dict[str, object]:
    """Return one issue comment in the shape the REST API returns."""
    return {
        "id": ident,
        "user": {"login": login, "type": "Bot" if login.endswith("[bot]") else "User"},
        "created_at": created,
        "updated_at": created,
        "body": body,
        "html_url": f"https://github.com/{REPO}/pull/{PR}#issuecomment-{ident}",
    }


def request(
    assessment_id: str, revision: str | None, head: str, subject: str = WHOLE_PLAN
) -> str:
    """Return the assessment question the workflow posted for this candidate."""
    lines = [
        "@coderabbitai please assess the implementation in this PR for",
        "completeness and correctness against the execplan:",
        "",
        "Repository: leynos/agent-helper-scripts",
        f"Pull request: {PR}",
        f"Assessed base/head: {BASE}...{head}",
        f"Assessed subject: {subject}.",
    ]
    if revision:
        lines.append(f"Plan revision: {revision}.")
    lines += [
        "Known limitations: <evidential limits only>.",
        "Proof inventory: none affected.",
        f"Assessment-ID: {assessment_id}.",
    ]
    return "\n".join(lines)


def reply(assessment_id: str, revision: str | None, verdict: dict[str, str]) -> str:
    """Return a substantive assessment reply as CodeRabbit posts it."""
    lines = [
        f"**Verdict: {verdict['label']}**",
        "",
        f"- **Assessment-ID:** `{assessment_id}`",
        f"- **Assessed base/head:** {BASE}...{verdict['head']}",
        f"- **Assessed subject:** {verdict['subject']}",
    ]
    if revision:
        lines.append(f"- **Plan revision:** {revision}")
    lines += ["", verdict["prose"]]
    return "\n".join(lines)


def check_run(index: int, check: dict[str, object]) -> dict[str, object]:
    """Return one check run, carrying the hosted output for CodeScene."""
    scene = "CodeScene" in str(check["name"])
    advisories = [str(item) for item in check.get("advisories", [])]
    return {
        "id": 7701 + index,
        "name": check["name"],
        "status": check["status"],
        "conclusion": check["conclusion"],
        # The hosted CodeScene check's own output. Without it the agent can see
        # the check passed but not that it listed no advisory findings, and the
        # skill makes an outstanding issue block readiness even on a passing
        # check. A scenario can carry findings here while the conclusion stays
        # SUCCESS, which is the case the skill says a green check does not clear.
        "output": {
            "title": "Issues found" if advisories else "No issues found" if scene else "",
            "summary": (
                "\n".join(advisories)
                if advisories
                else "No advisory findings, gate failures or code-health declines."
                if scene
                else ""
            ),
            "annotations_count": len(advisories),
        },
    }


def flagged_span() -> tuple[int, int]:
    """Return the line range the advisory covers, derived from the file.

    A range written by hand drifts from the code it describes, and a finding
    that points past the end of its own file is evidence a reader has to
    discount. The range is computed from the served text so the two agree.
    """
    lines = FLAGGED_TEXT.splitlines()
    start = next(
        index for index, line in enumerate(lines, 1) if line.startswith("def _assess_gate")
    )
    return start, len(lines)


def annotations() -> list[dict[str, object]]:
    """Return the annotation entries the flagged check lists.

    The check's output advertises a count, so a run that asks for the entries
    itself is making the read the count implies. Answering 404 there would
    report the annotation as unreadable rather than as the finding it is.
    """
    start, end = flagged_span()
    return [
        {
            "path": FLAGGED_PATH,
            "start_line": start,
            "end_line": end,
            "annotation_level": "warning",
            "title": "Complex Method",
            "message": "`_assess_gate` has a cyclomatic complexity of 12 (threshold 9).",
        }
    ]


def check_set(advisories: list[str] | None = None) -> list[dict[str, object]]:
    """Return the passing check set, with CodeScene's findings in its output.

    Every check passes in every scenario. A scenario that should stay in draft
    for CodeScene's reason carries its findings in the check's own output while
    the conclusion stays `SUCCESS`, so a run can only be blocked by reading that
    output rather than by seeing a failed check.
    """
    return [
        {**check, "advisories": advisories or []} if "CodeScene" in str(check["name"]) else check
        for check in GREEN
    ]


def plan_contents() -> dict[str, object]:
    """Return the contents-API entry for the approved plan file."""
    return {
        "name": PLAN_PATH.rsplit("/", 1)[-1],
        "path": PLAN_PATH,
        "sha": PLAN_BLOB,
        "size": len(PLAN_TEXT),
        # Served as plain text rather than the API's base64 envelope: the
        # fixture records which plan was assessed, and an encoder would put an
        # unreadable blob in a reviewed file for no gain.
        "encoding": "utf-8",
        "content": PLAN_TEXT,
        "type": "file",
    }


def flagged_contents() -> dict[str, object]:
    """Return the contents-API entry for the file the advisory names.

    The body is a stub: the fixture records which code the finding is about,
    and a run reading it learns the function and its shape, not a real
    implementation. Plain text is used for the same reason as the plan file.
    """
    text = FLAGGED_TEXT
    return {
        "name": FLAGGED_PATH.rsplit("/", 1)[-1],
        "path": FLAGGED_PATH,
        "sha": "b41d0c8e5f2a7d9c3e6b1048fa2c7d5e9b3a6f02",
        "size": len(text),
        "encoding": "utf-8",
        "content": text,
        "type": "file",
    }


def pull_files(head: str, paths: list[str]) -> list[dict[str, object]]:
    """Return the PR's changed files, as the files route lists them.

    A readiness run reads the diff to judge whether the delivered work matches
    the plan, and a 404 there is a gap in the recording rather than evidence
    about the candidate.
    """
    return [
        {
            "filename": path,
            "status": "modified",
            "additions": 12,
            "deletions": 0,
            "changes": 12,
            "sha": head,
        }
        for path in paths
    ]


def api_map(case: Case) -> dict[str, object]:
    """Return every recorded API route for one scenario."""
    head = case.head
    checks = check_set(case.advisories)
    paths = case.paths
    return {
        # The PR itself and its file list, which a readiness run reads to judge
        # whether the delivered work matches the plan. The bare `pulls/N` route
        # must be anchored, or it would also swallow `pulls/N/comments`.
        r"/pulls/\d+$": {
            "number": PR,
            "base": {"sha": BASE},
            "head": {"sha": head},
            "draft": True,
            "changed_files": 1,
        },
        r"/pulls/\d+/files(?:[?#]|$)": pull_files(head, paths),
        # The PR's commits, which a readiness run counts to see whether a
        # reviewed head is still the tip. One commit carrying the head.
        r"/pulls/\d+/commits(?:[?#]|$)": [
            {"sha": head, "commit": {"message": "Deliver the plan"}}
        ],
        # The review-thread state. A readiness run asks `graphql` for it, and
        # every recorded review is already resolved with no outstanding
        # thread, so an empty connection is the honest answer.
        r"graphql$": {"data": {"repository": {"pullRequest": {
            "reviewThreads": {"nodes": []},
        }}}},
        r"/issues/\d+/comments": case.comments,
        r"/commits/[0-9a-f]+/status$": {
            "state": "success",
            "statuses": [
                {
                    "context": "CodeRabbit",
                    "state": "success",
                    "description": "Review completed",
                }
            ],
        },
        r"/pulls/\d+/reviews$": [],
        r"/pulls/\d+/comments$": [],
        r"/commits/[0-9a-f]+/check-runs(?:[?#]|$)": {
            "total_count": len(checks),
            "check_runs": [
                check_run(index, check) for index, check in enumerate(checks)
            ],
        },
        # The annotation entries behind that count, which a run asks for when
        # it wants the finding rather than a summary line. Only the CodeScene
        # check carries any, so only its id has a listing.
        r"/check-runs/\d+/annotations(?:[?#]|$)": (
            annotations() if case.advisories else []
        ),
        # The flagged file itself, so a run can see the code the finding names.
        # It is part of this PR's change, and a 404 would report its content as
        # unavailable rather than as read.
        r"/contents/skills/[^?#]+(?:[?#]|$)": flagged_contents(),
        # The plan file itself, which a run reads to confirm the approved
        # revision is still the one in force. The path below `execplans/` is
        # the plan, and `?ref=` carries the head being checked; anchoring on
        # the directory alone left the file unreadable, so a run could not
        # confirm a revision before readiness.
        r"/contents/docs/execplans/[^/?#]+(?:[?#]|$)": plan_contents(),
        # The same directory without a file name, for a run that lists the
        # plans rather than reading one.
        r"/contents/docs/execplans(?:[?#]|$)": [plan_contents()],
        # The originating issue and its discussion, which a readiness run reads
        # to recover the accepted scope. The issue is this PR's own topic.
        r"/issues/\d+$": {
            "number": PR - 1,
            "title": "Bind the draft-to-ready gate to the implementation handoff",
            "state": "open",
            "body": "The approved plan is `docs/execplans/issue-271-readiness-handoff.md`.",
        },
    }


@dataclass(frozen=True)
class Case:
    """One scenario's description.

    Everything except the assessment evidence is shared, so a case names its
    evidence and takes the rest from the defaults below. Grouping it here keeps
    the writer to one argument as cases gain evidence dimensions.
    """

    name: str
    head: str
    draft: bool
    comments: list[dict[str, object]]
    advisories: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=lambda: [PLAN_PATH])


def scenario(case: Case) -> None:
    """Write one scenario's facts."""
    checks = check_set(case.advisories)
    facts = {
        "login": "experiment-owner",
        "pr_checks": "".join(
            f"{check['name']}\t{check['status']}\t{check['conclusion']}\n"
            for check in checks
        ),
        "pr": {
            "number": PR,
            "url": f"https://github.com/{REPO}/pull/{PR}",
            "baseRefOid": BASE,
            "headRefOid": case.head,
            "isDraft": case.draft,
            "mergeStateStatus": "BLOCKED" if case.draft else "CLEAN",
            "reviewDecision": "",
            "statusCheckRollup": checks,
        },
        "pr_ready_response": f"Pull request {REPO}#{PR} is marked as ready for review",
        # `gh pr diff --name-only` output, one changed path per line.
        "pr_diff": "".join(f"{path}\n" for path in case.paths),
        "api": api_map(case),
        "coords": {"repository": REPO, "pull_request": PR},
    }
    directory = OUT / case.name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "facts.json").write_text(
        json.dumps(facts, indent=2) + "\n", encoding="utf-8"
    )


scenario(Case(
    name="subset-only",
    head="aaaa1111",
    draft=True,
    comments=[
        comment(
            9001,
            "wafflecat-df12",
            request("271-ab-subset", "rev-7", "aaaa1111"),
            "2026-11-07T20:00:00Z",
        ),
        comment(
            9002,
            "coderabbitai[bot]",
            reply(
                "271-ab-subset",
                "rev-7",
                {
                    "label": "not clear",
                    "head": "aaaa1111",
                    "subject": DECLARED_SUBSET,
                    "prose": (
                        "EP-M1 and EP-M2 are substantially complete. The"
                        " remaining milestones, EP-M3 through EP-M6, are not"
                        " implemented, so the whole approved plan has not"
                        " cleared."
                    ),
                },
            ),
            "2026-11-07T20:05:00Z",
        ),
    ],
))

scenario(Case(
    name="superseded-revision",
    head="bbbb2222",
    draft=True,
    comments=[
        comment(
            9101,
            "pandalump",
            request("271-ab-superseded", "rev-7", "bbbb2222"),
            "2026-11-07T20:10:00Z",
        ),
        comment(
            9102,
            "coderabbitai[bot]",
            reply(
                "271-ab-superseded",
                "rev-6",
                {
                    "label": "clear",
                    "head": "bbbb2222",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "This verdict was recorded against plan revision"
                        " `rev-6`. Revision `rev-7` is the approved revision in"
                        " force for this request."
                    ),
                },
            ),
            "2026-11-07T20:15:00Z",
        ),
    ],
))

scenario(Case(
    name="current-whole-plan",
    head="cccc3333",
    draft=True,
    comments=[
        comment(
            9201,
            "buzzybee-df12",
            request("271-ab-current", "rev-7", "cccc3333"),
            "2026-11-07T20:20:00Z",
        ),
        comment(
            9202,
            "coderabbitai[bot]",
            reply(
                "271-ab-current",
                "rev-7",
                {
                    "label": "clear",
                    "head": "cccc3333",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "The whole approved plan is implemented at this head."
                        " No in-scope rework remains."
                    ),
                },
            ),
            "2026-11-07T20:25:00Z",
        ),
    ],
))

scenario(Case(
    name="subset-clear",
    head="ffff6666",
    draft=True,
    comments=[
        comment(
            9501,
            "buzzybee-df12",
            request("271-ab-subset-clear", "rev-7", "ffff6666"),
            "2026-11-07T20:45:00Z",
        ),
        comment(
            9502,
            "coderabbitai[bot]",
            reply(
                "271-ab-subset-clear",
                "rev-7",
                {
                    "label": "clear",
                    "head": "ffff6666",
                    "subject": DECLARED_SUBSET,
                    "prose": (
                        "EP-M1 and EP-M2 are complete for the declared subset."
                        " This verdict covers that subset only and does not"
                        " clear the whole approved plan."
                    ),
                },
            ),
            "2026-11-07T20:50:00Z",
        ),
    ],
))

scenario(Case(
    name="codescene-advisory",
    head="9999aaaa",
    draft=True,
    comments=[
        comment(
            9601,
            "wafflecat-df12",
            request("271-ab-codescene", "rev-7", "9999aaaa"),
            "2026-11-07T20:55:00Z",
        ),
        comment(
            9602,
            "coderabbitai[bot]",
            reply(
                "271-ab-codescene",
                "rev-7",
                {
                    "label": "clear",
                    "head": "9999aaaa",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "The whole approved plan is implemented at this head."
                        " No in-scope rework remains."
                    ),
                },
            ),
            "2026-11-07T21:00:00Z",
        ),
    ],
    # The CodeScene check passes, yet its own output lists an advisory finding.
    # The skill says a passing check with advisory findings still has
    # outstanding issues, so this scenario is the one that shows whether the
    # gate reads the check's output or only its conclusion. Nothing else is
    # outstanding: the assessment is a clear whole-plan verdict on the revision
    # in force and every other check is green.
    advisories=[
        "Complex Method: `_assess_gate` has a cyclomatic complexity of 12"
        " (threshold 9).",
    ],
    # The flagged function has to be in the change for the finding to be about
    # this candidate at all. A finding that names code the PR does not touch is
    # incoherent evidence, and a run reading it would be reasoning about a
    # different PR from the one the fixture describes.
    paths=[PLAN_PATH, FLAGGED_PATH],
))

scenario(Case(
    name="proof-only-pending",
    head="dddd4444",
    draft=True,
    comments=[
        comment(
            9301,
            "wafflecat-df12",
            "\n".join(
                [
                    "@coderabbitai are you satisfied that the introduced proof(s)",
                    "(proofs/refinement/Theorem.lean#refinement_sound) is",
                    "substantive, rigorous, and well-founded?",
                    "",
                    "Repository: leynos/agent-helper-scripts",
                    f"Pull request: {PR}",
                    f"Assessed base/head: {BASE}...dddd4444",
                    "Plan revision: <omitted; no ExecPlan applies>.",
                    "Assessment-ID: 271-ab-proof-only.",
                ]
            ),
            "2026-11-07T20:30:00Z",
        )
    ],
))

scenario(Case(
    name="proof-only-cleared",
    head="eeee5555",
    draft=True,
    comments=[
        comment(
            9401,
            "pandalump",
            "\n".join(
                [
                    "@coderabbitai are you satisfied that the introduced proof(s)",
                    "(proofs/refinement/Theorem.lean#refinement_sound) is",
                    "substantive, rigorous, and well-founded?",
                    "",
                    "Repository: leynos/agent-helper-scripts",
                    f"Pull request: {PR}",
                    f"Assessed base/head: {BASE}...eeee5555",
                    "Plan revision: <omitted; no ExecPlan applies>.",
                    "Assessment-ID: 271-ab-proof-only.",
                ]
            ),
            "2026-11-07T20:35:00Z",
        ),
        comment(
            9402,
            "coderabbitai[bot]",
            "\n".join(
                [
                    "**Verdict: clear**",
                    "",
                    "- **Assessment-ID:** `271-ab-proof-only`",
                    f"- **Assessed base/head:** {BASE}...eeee5555",
                    "- **Assessed subject:** `refinement_sound`",
                    "",
                    "The refinement proof is substantive and non-vacuous. No"
                    " plan revision is named, so none is echoed.",
                ]
            ),
            "2026-11-07T20:40:00Z",
        ),
    ],
))

print("wrote", sorted(path.name for path in OUT.iterdir()))
