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
import re

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
# The blob of the plan revision that supersedes `rev-7` in the scenario where
# the plan file, rather than either reply, is what moved. Two revisions of one
# plan are two blobs, so a reply quoting the old blob for the new revision
# would be describing a file the fixture never served.
PLAN_BLOB_REV8 = "e3b7c04d9a6f5128b47d0c3e8a15f96d2c4b70a8"
# The proof the two `proof-only-*` scenarios introduce. It is the subject of
# their proof assessment, and the only changed file in those runs.
PROOF_PATH = "proofs/refinement/Theorem.lean"
# The named reference inside that proof. The template asks about "proof file
# paths with named proof references", and the recorded replies name the
# reference alone, so the recording carries it beside the path: a receiver that
# reconciles the changed proof with the inventory those replies are compared
# against needs both halves of the identity from the same premise.
PROOF_REFERENCE = "refinement_sound"
# The inventory line for a candidate that changes this proof and asks a proof
# question about it. Every `combined-*` scenario is one, so none of them may
# say "none affected": that sentence and the sibling proof request state two
# things the run cannot both believe, and a run reading both then holds on the
# contradiction instead of on the rule the case exists to demonstrate.
COMBINED_INVENTORY = (
    "Proof inventory: `proofs/refinement/Theorem.lean` (`refinement_sound`),"
    " covered by the separate proof assessment."
)
# The file an advisory finding names, and the code it names within it. A
# finding about this candidate has to be about a change this candidate makes.
FLAGGED_PATH = "skills/pr-babysitting/scripts/readiness_gate.py"
# The shape the finding describes: one function holding several independent
# checks, which is why its complexity is over the threshold. It is enough for a
# run to see what the finding is about; it is not a working implementation.
#
# It is deliberately longer than the real Large Method threshold, so the local
# finding the simulated `cs` reports is true of the code this fixture serves.
# A finding whose stated size the served file contradicts is one a careful run
# discounts, and the run would then hold for a reason the scenario is not
# testing.
# The stub is data, not code: it is served verbatim, its size is measured
# from the text, and linting it as Python would only invite edits that make
# the served file drift from the finding that describes it.
FLAGGED_TEXT = (Path(__file__).resolve().parent / "flagged_gate_stub.txt").read_text(
    encoding="utf-8"
)
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
    assessment_id: str,
    revision: str | None,
    head: str,
    subject: str = WHOLE_PLAN,
    blob: str = PLAN_BLOB,
    proof_inventory: str = "Proof inventory: none affected.",
) -> str:
    """Return the assessment question the workflow posted for this candidate.

    The body is the one `execplan-assessment.md` specifies, not a shorthand of
    it. Two fields were missing here and the gap mattered: a request naming only
    the revision leaves base/head and a label to identify which file was
    inspected, and `Known limitations:` with an unfilled placeholder reads as a
    request that never stated its evidential limits. A run could only reach the
    same conclusion by treating the missing values as unimportant, so a fixture
    that seeded them was rehearsing a request the skill would not post.

    The blob SHA is the plan file's at this head, which is why it is a
    parameter: `combined-proof-stale-plan-revision` serves a superseding
    revision, and a request naming `rev-8` with the `rev-7` blob would describe
    a file the fixture never served.

    Parameters
    ----------
    assessment_id : str
        The unique request marker the reply is expected to echo.
    revision : str or None
        The approved revision in force, or None when no ExecPlan applies.
    head : str
        The candidate head the question was posted for.
    subject : str, optional
        The assessed subject; the whole approved plan unless a case declares a
        subset.
    blob : str, optional
        The plan file's blob SHA at `head`.
    proof_inventory : str, optional
        The inventory line. It defaults to "none affected", which is true of
        every plan-only case and false of a candidate that changes a proof: a
        request that says otherwise contradicts the PR it is about, and a run
        reading both cannot tell which statement to believe. Every
        `combined-*` case therefore passes `COMBINED_INVENTORY` explicitly,
        because each changes a proof and asks a proof question about it.

    Returns
    -------
    str
        The request body as the workflow posts it.
    """
    lines = [
        "@coderabbitai please assess the implementation in this PR for",
        "completeness and correctness against the execplan:",
        "",
        f"> `{PLAN_PATH}`",
        "",
        f"Assessed subject: {subject}.",
        f"Published head: {head}; comparison base: {BASE}.",
    ]
    if revision:
        lines.append(
            f"Plan revision: {revision} (approved revision in force);"
            f" plan file blob SHA at this head: {blob}."
        )
    else:
        lines.append("Plan revision: <omitted; no ExecPlan applies>.")
    lines += [
        (
            "Acceptance evidence: the hosted checks recorded for this head,"
            " and the local `cs delta` result where the run consulted one."
        ),
        (
            "Known limitations: the local CodeScene result is the rehearsal"
            " stand-in's, which discloses in its own output that it is"
            " simulated rather than a CodeScene analysis."
        ),
        proof_inventory,
        f"Assessment-ID: {assessment_id}.",
        "",
        "Please echo the Assessment-ID, assessed base/head, and plan revision in",
        "your substantive reply.",
        "This is an assessment conversation, not a request to start a formal PR",
        "review.",
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


def proof_request(
    assessment_id: str,
    head: str,
    revision: str | None,
    blob: str = PLAN_BLOB,
) -> str:
    """Return the proof scrutiny question the workflow posted for this candidate.

    The request names the plan revision only when an ExecPlan applies. A
    proof-only assignment with no ExecPlan keeps the base/head as its whole
    candidate, and asking it for a revision echo would demand a value that
    does not exist. Both the request and its reply are generated from here so
    the two halves of one conversation cannot disagree about which they are.

    Parameters
    ----------
    assessment_id : str
        The unique request marker the reply is expected to echo.
    head : str
        The candidate head the question was posted for.
    revision : str or None
        The approved revision in force, or None when no ExecPlan applies.
    blob : str, optional
        The plan file's blob SHA at `head`. A revision alone cannot identify
        which file was inspected, and the template asks for both.
    """
    return "\n".join(
        [
            "@coderabbitai are you satisfied that the introduced proof(s)",
            "(proofs/refinement/Theorem.lean#refinement_sound) is",
            "substantive, rigorous, and well-founded?",
            "",
            "Repository: leynos/agent-helper-scripts",
            f"Pull request: {PR}",
            f"Assessed base/head: {BASE}...{head}",
            (
                "Proof inventory and claims: `proofs/refinement/Theorem.lean`,"
                " theorem `refinement_sound : forall (s : State), refine s = s"
                " -> sound s`, discharged by `sound_of_refine s h`."
            ),
            (
                "Production correspondence: the theorem states that a state is"
                " sound whenever refining it returns it unchanged; the"
                " refinement transition it constrains is the implementation"
                " this candidate ships."
            ),
            (
                "Assumptions, trusted boundaries, domain, and bounds: the"
                " candidate states no axioms, stubs or trusted boundaries of"
                " its own beyond the names the file uses, and no tool, backend"
                " or version is recorded for it in this fixture."
            ),
            (
                "Verifier evidence: the hosted `Makefile gates` check is the"
                " only verifier surface this fixture records for the head; no"
                " Lean build log, command or per-obligation outcome is served,"
                " and none is claimed here."
            ),
            (
                "Non-vacuity and limitations: the fixture records no witness,"
                " negative control or counterexample for the claim, and states"
                " that limitation rather than presenting a finite example as an"
                " unbounded proof."
            ),
            (
                f"Plan revision: {revision} (approved revision in force);"
                f" plan file blob SHA at this head: {blob}."
                if revision
                else "Plan revision: <omitted; no ExecPlan applies>."
            ),
            f"Assessment-ID: {assessment_id}.",
        ]
    )


def proof_reply(
    assessment_id: str,
    revision: str | None,
    head: str,
    *,
    label: str = "clear",
    prose: str,
) -> str:
    """Return a substantive proof-assessment reply as CodeRabbit posts it.

    The subject is the named proof the question asked about, not the plan: a
    proof verdict is evidence for the proofs it covers, and recording the plan
    as its subject would let a reader treat it as a completeness verdict.

    Parameters
    ----------
    assessment_id : str
        The marker the request was posted under and the reply echoes.
    revision : str or None
        The revision the reply echoes, or None when it echoes none.
    head : str
        The head the reply claims to have assessed.
    label : str, optional
        The verdict, ``clear`` unless a case needs another.
    prose : str
        The substantive body the reply gives.
    """
    return reply(
        assessment_id,
        revision,
        {
            "label": label,
            "head": head,
            "subject": "`refinement_sound`",
            "prose": prose,
        },
    )


def hosted_output(check: dict[str, object]) -> dict[str, object]:
    """Return the hosted output a check carries, in `check-runs` shape.

    One helper serves both routes the agent can read a check through — the
    `check-runs` listing and `gh pr view --json statusCheckRollup` — so the two
    cannot say different things about the same check.

    Without the output the agent can see that CodeScene passed but not whether
    it listed advisory findings, and the skill makes an outstanding issue block
    readiness even on a passing check. A scenario can therefore carry findings
    here while the conclusion stays `SUCCESS`, which is the case the skill says
    a green check does not clear.
    """
    scene = "CodeScene" in str(check["name"])
    advisories = [str(item) for item in check.get("advisories", [])]
    return {
        "title": "Issues found" if advisories else "No issues found" if scene else "",
        "summary": (
            "\n".join(advisories)
            if advisories
            else "No advisory findings, gate failures or code-health declines."
            if scene
            else ""
        ),
        "annotations_count": len(advisories),
    }


def check_run(index: int, check: dict[str, object]) -> dict[str, object]:
    """Return one check run, carrying the hosted output for CodeScene."""
    return {
        "id": 7701 + index,
        "name": check["name"],
        "status": check["status"],
        "conclusion": check["conclusion"],
        "output": hosted_output(check),
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

    The metrics are CodeScene's own, measured on this stub with the real CLI:
    `cs check` reports `Complex Method (cc = 44)` and `Large Method (LoC = 87
    lines)`. A hosted finding that quoted different numbers from the local one
    would make the two sources disagree about the same file.
    """
    start, end = flagged_span()
    return [
        {
            "path": FLAGGED_PATH,
            "start_line": start,
            "end_line": end,
            "annotation_level": "warning",
            "title": "Complex Method",
            "message": "`_assess_gate` has a cyclomatic complexity of 44 (threshold 9).",
        },
        {
            "path": FLAGGED_PATH,
            "start_line": start,
            "end_line": end,
            "annotation_level": "warning",
            "title": "Large Method",
            "message": (
                f"`_assess_gate` has {local_loc()} lines,"
                f" threshold = {LOC_THRESHOLD}."
            ),
        },
    ]


# CodeScene's own Large Method threshold, quoted from `cs delta` on a stub like
# this one. The finding must be true of the served text: a report the recorded
# file contradicts is one a careful run rightly discounts, and the run would
# then hold for a reason the scenario is not testing.
LOC_THRESHOLD = 70


def local_loc() -> int:
    """Return the flagged function's line count as CodeScene reports it.

    Measured on the real CLI for a function of this shape: the count excludes
    the signature line, so a function whose body ends on line `end` and starts
    on line `start` is reported as `end - start` lines. Deriving it from the
    served text keeps the simulated report and the recorded file in agreement.
    """
    start, end = flagged_span()
    return end - start


def local_finding() -> str:
    """Return the local delta finding, describing the file the fixture serves.

    The shape is the real `cs delta` block, captured from the CLI on this very
    stub, so a run reads the same wording it would see locally.
    """
    start, _ = flagged_span()
    return "\n".join(
        [
            "─" * 52,
            "",
            FLAGGED_PATH,
            "Code Health: (8.69)",
            "",
            "  🚩 New issue: Large Method",
            f"     Function: _assess_gate at line {start}",
            f"     Status: _assess_gate has {local_loc()} lines, threshold = {LOC_THRESHOLD}",
            "",
        ]
    )


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


def plan_contents(case: Case) -> dict[str, object]:
    """Return the contents-API entry for the approved plan file at this head.

    The revision is read from the case rather than fixed, because the plan file
    is the only source that can say which revision is actually in force at the
    candidate. A scenario whose verdict was recorded against an earlier
    revision can only be distinguished from a current one by this file, so
    hard-coding it here would make that distinction unrepresentable.

    The blob SHA moves with the revision for the same reason: two revisions of
    one plan are two blobs, and a reply that quotes a blob SHA for the
    superseding revision would be describing a file this fixture never served.
    """
    text = f"# Readiness handoff\n\nPlan revision: {case.plan_revision}\n"
    return {
        "name": PLAN_PATH.rsplit("/", 1)[-1],
        "path": PLAN_PATH,
        "sha": PLAN_BLOB if case.plan_revision == "rev-7" else case.plan_blob,
        "size": len(text),
        # Served as plain text rather than the API's base64 envelope: the
        # fixture records which plan was assessed, and an encoder would put an
        # unreadable blob in a reviewed file for no gain.
        "encoding": "utf-8",
        "content": text,
        "type": "file",
    }


def proof_contents() -> dict[str, object]:
    """Return the contents-API entry for the proof a proof-only PR introduces.

    The proof-only scenarios assess a named proof, and a run that reads the
    file it is judging is asking about the candidate's own change. Answering
    404 there would report the subject of the assessment as unreadable.
    """
    text = "\n".join(
        [
            "theorem refinement_sound :",
            "  forall (s : State), refine s = s → sound s := by",
            "  intro s h",
            "  exact sound_of_refine s h",
            "",
        ]
    )
    return {
        "name": PROOF_PATH.rsplit("/", 1)[-1],
        "path": PROOF_PATH,
        "sha": "c7e5a12b9d4f860312ab7c5e9d1846f0a2b3c761",
        "size": len(text),
        "encoding": "utf-8",
        "content": text,
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


def commit_message(*, plan_route: bool) -> str:
    """Return the one commit message every route serving this head must give.

    `pulls/N/commits`, `commits/<sha>` and `pr view --json commits` all describe
    the same commit. Computing the text once keeps them from disagreeing, which
    a careful run would otherwise read as two different commits on one head.
    """
    return "Deliver the plan" if plan_route else "Introduce the refinement proof"


def serves_plan(case: Case, paths: list[str]) -> bool:
    """Return whether this scenario's routes serve an ExecPlan.

    The commit text, the file contents and the issue body all branch on the
    same fact, and `commit_message` exists because three commit routes
    disagreeing about one head read as two commits. Two copies of the input
    predicate can drift apart and reintroduce exactly that, so both callers
    use this one.
    """
    return case.plan or any(path.startswith("docs/execplans/") for path in paths)


def pull_routes(
    head: str, paths: list[str], *, plan_route: bool
) -> dict[str, object]:
    """Return the routes describing the PR itself and its delivered change."""
    message = commit_message(plan_route=plan_route)
    return {
        # The PR itself and its file list, which a readiness run reads to judge
        # whether the delivered work matches the plan. The bare `pulls/N` route
        # must be anchored, or it would also swallow `pulls/N/comments`.
        r"/pulls/\d+$": {
            "number": PR,
            "base": {"sha": BASE},
            "head": {"sha": head},
            "draft": True,
            # Derived, not fixed: the file-list route serves `paths`, so a
            # hard-coded 1 contradicts it for every scenario that changes two.
            # A careful run would then hold on the fixture's own disagreement
            # rather than on the rule the scenario exists to exercise.
            "changed_files": len(paths),
        },
        r"/pulls/\d+/files(?:[?#]|$)": pull_files(head, paths),
        # The PR's commits, which a readiness run counts to see whether a
        # reviewed head is still the tip. One commit carrying the head.
        r"/pulls/\d+/commits(?:[?#]|$)": [
            {
                "sha": head,
                "commit": {"message": message},
            }
        ],
        # The head commit on its own. The skill records the PR author, head
        # repository and head commit with the trust decision, and a run may
        # read the commit object itself to report who wrote it. Anchored at the
        # end of the path so it cannot swallow the `/status` or `/check-runs`
        # sub-routes, which carry different shapes.
        #
        # Pinned to this scenario's head rather than to any hex SHA. A route
        # matching any commit answers a request for another SHA with this
        # head's metadata, so a run checking commit identity reads false
        # evidence — the served object would be answering about a commit the
        # fixture never recorded.
        rf"/commits/{head}$": {
            "sha": head,
            "author": {"login": "experiment-owner", "type": "User"},
            "committer": {"login": "experiment-owner", "type": "User"},
            "commit": {
                "message": message,
                "author": {"name": "experiment-owner"},
            },
        },
    }


def review_routes(case: Case, checks: list[dict[str, object]]) -> dict[str, object]:
    """Return the routes carrying the assessment and review state."""
    return {
        # The review-thread state. A readiness run asks `graphql` for it, and
        # every recorded review is already resolved with no outstanding
        # thread, so an empty connection is the honest answer.
        r"graphql$": {"data": {"repository": {"pullRequest": {
            "reviewThreads": {"nodes": []},
        }}}},
        r"/issues/\d+/comments": case.comments,
        # Pinned to the head for the same reason as the commit object: a status
        # route answering any SHA reports this head's review state for a commit
        # it never recorded.
        rf"/commits/{case.head}/status$": {
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
        # Head-pinned: a check-runs route keyed on any SHA would report this
        # head's CI for an unrecorded commit.
        rf"/commits/{case.head}/check-runs(?:[?#]|$)": {
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
    }


def content_routes(case: Case, plan_route: bool) -> dict[str, object]:
    """Return the routes serving the files a run reads to judge the change."""
    return {
        # The changed files themselves. A run that reads a file it is judging is
        # asking about this candidate's own change, so the route serves the same
        # content the finding or the plan describes.
        r"/contents/proofs/[^?#]+(?:[?#]|$)": proof_contents(),
        # The flagged file itself, so a run can see the code the finding names.
        # It is part of this PR's change, and a 404 would report its content as
        # unavailable rather than as read.
        r"/contents/skills/[^?#]+(?:[?#]|$)": flagged_contents(),
        # The plan file itself, which a run reads to confirm the approved
        # revision is still the one in force. The route names the approved
        # path rather than any file below `execplans/`: a wildcard served the
        # approved payload for a request naming some other plan, so a run
        # could report the approved plan inspected when it had asked for a
        # different one. `?ref=` carries the head being checked; anchoring on
        # the directory alone left the file unreadable, so a run could not
        # confirm a revision before readiness. A proof-only scenario has no
        # plan, so the route is absent there and answers 404, rather than
        # serving a plan its premise says does not apply.
        **(
            {
                rf"/contents/{re.escape(PLAN_PATH)}(?:[?#]|$)": plan_contents(case),
                # The same directory without a file name, for a run that lists
                # the plans rather than reading one.
                r"/contents/docs/execplans(?:[?#]|$)": [plan_contents(case)],
            }
            if plan_route
            else {}
        ),
    }


def issue_route(plan_route: bool) -> dict[str, object]:
    """Return the originating issue, which carries the accepted scope."""
    return {
        # The originating issue and its discussion, which a readiness run reads
        # to recover the accepted scope. The issue is this PR's own topic.
        r"/issues/\d+$": {
            "number": PR - 1,
            "title": (
                "Bind the draft-to-ready gate to the implementation handoff"
                if plan_route
                else "Prove refinement soundness"
            ),
            "state": "open",
            "body": (
                f"The approved plan is `{PLAN_PATH}`."
                if plan_route
                else "There is no ExecPlan; this PR is the proof work."
            ),
        },
    }


def api_map(case: Case) -> dict[str, object]:
    """Return every recorded API route for one scenario.

    The routes are grouped by what they describe — the PR and its change, the
    review and assessment state, the files being judged, the originating issue
    — so each group stays readable and one group's edit cannot reflow another.
    """
    checks = check_set(case.advisories)
    paths = changed_paths(case)
    plan_route = serves_plan(case, paths)
    return {
        **pull_routes(case.head, paths, plan_route=plan_route),
        **review_routes(case, checks),
        **content_routes(case, plan_route),
        **issue_route(plan_route),
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
    paths: list[str] | None = None
    # The two `proof-only-*` scenarios exist to show that a proof assessment is
    # judged without an ExecPlan. A PR body naming an approved plan would
    # contradict their premise and make the run ask for a completeness
    # assessment instead of deciding the proof one. Every other case is plan
    # work, so the body names the plan.
    plan: bool = True
    # The local CodeScene result the simulated `cs` reports: `clean` when the
    # delta introduces nothing, `finding` when it lists a new issue, and
    # `unavailable` when the tool cannot evaluate. A case that does not set it
    # takes `clean`, so every permitting scenario must state its local evidence
    # rather than inherit silence.
    cs_mode: str = "clean"
    # The revision the served plan file carries, and the blob SHA of that
    # revision. The plan file is the only fixture surface that says which
    # revision is in force, so a scenario cannot demonstrate revision binding
    # without being able to move it independently of the assessment replies.
    plan_revision: str = "rev-7"
    plan_blob: str = PLAN_BLOB
    # Verdicts the stand-in answers with, keyed by question kind. Most cases
    # record an answer that was already in the thread; a case that scripts one
    # is the only shape in which a single run both posts a question and clears
    # it. The marker is echoed from the request the run minted, so a fixture
    # never has to predict the Assessment-ID the agent chooses.
    scripted_replies: dict[str, dict[str, str]] = field(default_factory=dict)
    # Which shipped skill the run starts at. A case that sets
    # `sdlc-implementation` rehearses the implementation handoff itself: the
    # run has to open the sender, produce the packet and carry it into
    # `pr-babysitting`. The crossing cannot be inferred from the GitHub facts,
    # because both prompts read the same PR, so the scenario states it. Every
    # other case starts at the receiver, and the runner treats the key's
    # absence as that default so the recordings made before the crossing
    # existed stay attached to the prompt they were made under.
    start_skill: str = "pr-babysitting"


def changed_paths(case: Case) -> list[str]:
    """Return the files this scenario's PR changes.

    A case that names none takes the files its premise implies: plan work
    changes the plan, and proof work changes the proof it introduces. Both the
    file list and the diff read from here, so the two cannot disagree about
    what the candidate touches.
    """
    if case.paths is not None:
        return case.paths
    return [PLAN_PATH] if case.plan else [PROOF_PATH]


def scenario(case: Case) -> None:
    """Write one scenario's facts."""
    checks = check_set(case.advisories)
    paths = changed_paths(case)
    body = (
        f"Implements the approved plan `{PLAN_PATH}`. Closes #271."
        if case.plan
        else (
            "Introduces one Lean refinement proof and changes no ExecPlan."
            " Closes #271."
        )
    )
    facts = {
        "login": "experiment-owner",
        "pr_checks": "".join(
            f"{check['name']}\t{check['status']}\t{check['conclusion']}\n"
            for check in checks
        ),
        "pr": {
            "number": PR,
            "url": f"https://github.com/{REPO}/pull/{PR}",
            "title": (
                "Bind the draft-to-ready gate to the implementation handoff"
                if case.plan
                else "Prove refinement soundness"
            ),
            "body": body,
            "state": "OPEN",
            "author": {"login": "experiment-owner", "type": "User"},
            "baseRefName": "main",
            "baseRefOid": BASE,
            "headRefName": "issue-271-readiness-handoff",
            "headRefOid": case.head,
            "headRepository": {
                "name": REPO.split("/")[1],
                "nameWithOwner": REPO,
            },
            "headRepositoryOwner": {"login": REPO.split("/")[0]},
            # The candidate-trust check reads whether the head lives in the base
            # repository. A recorded PR that omitted it made every run report
            # itself unable to decide trust, which is not the variable any
            # scenario is testing.
            "isCrossRepository": False,
            "isDraft": case.draft,
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "BLOCKED" if case.draft else "CLEAN",
            "reviewDecision": "",
            # The rollup is the shape `gh pr view --json statusCheckRollup`
            # returns: a check run carries its own hosted output, not the
            # generator's `advisories` field. Both routes go through the same
            # helper, so a run reading either source sees the same finding.
            "statusCheckRollup": [
                {
                    "name": check["name"],
                    "status": check["status"],
                    "conclusion": check["conclusion"],
                    "output": hosted_output(check),
                }
                for check in checks
            ],
            # `--json files` on the same object; a run reads them to see whether
            # the delivery matches the plan.
            "files": pull_files(case.head, paths),
            # The same head and the same commit text the API routes give. A
            # hard-coded headline disagreed with them for every proof-only
            # scenario, which read as two commits on one head.
            "commits": [
                {
                    "sha": case.head,
                    "messageHeadline": commit_message(
                        plan_route=serves_plan(case, paths)
                    ),
                }
            ],
        },
        "pr_ready_response": f"Pull request {REPO}#{PR} is marked as ready for review",
        # `gh pr diff --name-only` output, one changed path per line.
        "pr_diff": "".join(f"{path}\n" for path in paths),
        "api": api_map(case),
        "coords": {"repository": REPO, "pull_request": PR},
        # The local CodeScene result the simulated `cs` answers this run with.
        # It lives beside the GitHub facts because it is one more recorded
        # input the agent reads, and the runner writes it into the sandbox.
        "cs_mode": case.cs_mode,
        # The plan a permitting run reconciles the revision against, so the
        # plan-read assertion names the approved file rather than accepting any
        # `contents/docs/execplans/` route. A read of another ExecPlan that
        # carried the approved payload would otherwise clear the check whose
        # subject is the revision in force in this file.
        "plan_path": PLAN_PATH,
        # The proof a combined run is asked about, so the proof-read assertion
        # names the assessed file rather than accepting any `contents/proofs/`
        # route. A run that read some other proof, or read this one at another
        # ref, has not inspected the subject its verdict covers.
        "proof_path": PROOF_PATH,
        # The reference the proof is assessed under, as its inventory entry
        # names it. The diff names a file and the reply names a reference, so a
        # receiver reconciling the two needs both from one premise: the same
        # recording says which file it changes and what that file is called in
        # the inventory the reply is compared against.
        "proof_reference": PROOF_REFERENCE,
        # The finding text accompanies the mode, so the size the local result
        # reports is derived from the same file the `contents` route serves. A
        # finding written twice could disagree with the code it describes, and
        # a careful run would then discount it for a reason the scenario is not
        # testing.
        "cs_finding": local_finding() if case.cs_mode == "finding" else "",
    }
    # Only a case that scripts an answer carries the key. Emitting an empty
    # mapping for every scenario would rewrite sixteen files to say nothing,
    # and a reader of those facts would have to decide whether `{}` meant "no
    # answer is scripted" or "an answer was scripted and lost".
    if case.scripted_replies:
        facts["scripted_replies"] = case.scripted_replies
    # Only a crossing case names a start skill, for the same reason: the
    # default belongs in the reader, and writing `"pr-babysitting"` into every
    # facts file would suggest the value was recorded rather than assumed.
    if case.start_skill != "pr-babysitting":
        facts["start_skill"] = case.start_skill
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
    name="posted-then-answered",
    head="eeee6666",
    draft=True,
    # No assessment is in the thread. This is the one case where the run must
    # post the question itself, and the stand-in answers it, so a single run
    # both asks and clears. Every other permitting case starts with the answer
    # already recorded, which is why none of them can show this path.
    comments=[
        comment(
            9401,
            "buzzybee-df12",
            (
                "Preparing the readiness run for `eeee6666`. No assessment has"
                " been requested yet."
            ),
            "2026-11-07T20:40:00Z",
        ),
    ],
    cs_mode="clean",
    scripted_replies={
        "completeness": {
            "verdict": "clear",
            "prose": (
                "The whole approved plan is implemented at this head."
                " No in-scope rework remains."
            ),
        },
    },
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
    # The positive case must supply both CodeScene halves: a hosted check with
    # no findings and a local delta that reports none. Its whole purpose is to
    # show that a fully-evidenced candidate does transition, so a missing local
    # result would make it demonstrate the opposite of what it claims.
    cs_mode="clean",
))

scenario(Case(
    name="local-codescene-finding",
    head="1111bbbb",
    draft=True,
    comments=[
        comment(
            9701,
            "wafflecat-df12",
            request("271-ab-local-finding", "rev-7", "1111bbbb"),
            "2026-11-07T21:10:00Z",
        ),
        comment(
            9702,
            "coderabbitai[bot]",
            reply(
                "271-ab-local-finding",
                "rev-7",
                {
                    "label": "clear",
                    "head": "1111bbbb",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "The whole approved plan is implemented at this head."
                        " No in-scope rework remains."
                    ),
                },
            ),
            "2026-11-07T21:15:00Z",
        ),
    ],
    # Hosted CodeScene is clean and every check passes; only the local delta
    # reports an issue. That isolates the local half, which no hosted source
    # can stand in for. The flagged file is in the change, because a local
    # finding about code this PR does not touch is not evidence about this
    # candidate: a run would rightly discount it and hold for the wrong reason.
    paths=[PLAN_PATH, FLAGGED_PATH],
    cs_mode="finding",
))

scenario(Case(
    name="local-codescene-unavailable",
    head="2222cccc",
    draft=True,
    comments=[
        comment(
            9801,
            "wafflecat-df12",
            request("271-ab-local-unavailable", "rev-7", "2222cccc"),
            "2026-11-07T21:20:00Z",
        ),
        comment(
            9802,
            "coderabbitai[bot]",
            reply(
                "271-ab-local-unavailable",
                "rev-7",
                {
                    "label": "clear",
                    "head": "2222cccc",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "The whole approved plan is implemented at this head."
                        " No in-scope rework remains."
                    ),
                },
            ),
            "2026-11-07T21:25:00Z",
        ),
    ],
    # Every other source is green and the assessment clears; the tool simply
    # cannot evaluate. The run must treat that as unverified rather than clean,
    # because "I could not check" is not "nothing was found".
    cs_mode="unavailable",
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
    # Derived from the same annotation entries the check exposes on its own
    # route. The summary and the annotations describe one analysis of one file,
    # so a handwritten summary drifted from them (it kept complexity 12 after
    # the stub changed to the CLI's measured 44) and the run rightly stopped on
    # the mismatch instead of on the rule.
    advisories=[f"{entry['title']}: {entry['message']}" for entry in annotations()],
    # The flagged function has to be in the change for the finding to be about
    # this candidate at all. A finding that names code the PR does not touch is
    # incoherent evidence, and a run reading it would be reasoning about a
    # different PR from the one the fixture describes.
    paths=[PLAN_PATH, FLAGGED_PATH],
    # The local delta reports the same finding the hosted check does. Two
    # sources that are supposed to describe one candidate must agree; setting
    # this to `clean` while the check lists a warning would manufacture a
    # contradiction that is not part of what this scenario tests.
    cs_mode="finding",
))

scenario(Case(
    name="proof-only-pending",
    head="dddd4444",
    draft=True,
    comments=[
        comment(
            9301,
            "wafflecat-df12",
            proof_request("271-ab-proof-only", "dddd4444", None),
            "2026-11-07T20:30:00Z",
        )
    ],
    # No ExecPlan applies to this PR, so its body must not describe one.
    plan=False,
))

scenario(Case(
    name="proof-only-cleared",
    head="eeee5555",
    draft=True,
    comments=[
        comment(
            9401,
            "pandalump",
            proof_request("271-ab-proof-only", "eeee5555", None),
            "2026-11-07T20:35:00Z",
        ),
        comment(
            9402,
            "coderabbitai[bot]",
            proof_reply(
                "271-ab-proof-only",
                None,
                "eeee5555",
                prose=(
                    "The refinement proof is substantive and non-vacuous. No"
                    " plan revision is named, so none is echoed."
                ),
            ),
            "2026-11-07T20:40:00Z",
        ),
    ],
    # No ExecPlan applies to this PR, so its body must not describe one.
    plan=False,
))

scenario(Case(
    name="combined-plan-and-proof",
    head="3333dddd",
    draft=True,
    comments=[
        comment(
            9951,
            "buzzybee-df12",
            request(
                "271-ab-combined",
                "rev-7",
                "3333dddd",
                proof_inventory=COMBINED_INVENTORY,
            ),
            "2026-11-08T09:00:00Z",
        ),
        comment(
            9952,
            "coderabbitai[bot]",
            reply(
                "271-ab-combined",
                "rev-7",
                {
                    "label": "clear",
                    "head": "3333dddd",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "The whole approved plan is implemented at this head."
                        " No in-scope rework remains."
                    ),
                },
            ),
            "2026-11-08T09:05:00Z",
        ),
        # Both applicable assessments, posted as separate questions under
        # separate markers. A combined assignment asks for the proof scrutiny
        # as well as the completeness verdict, and this case is the one where
        # both must clear for one candidate.
        comment(
            9953,
            "pandalump",
            proof_request("271-ab-combined-proof", "3333dddd", "rev-7"),
            "2026-11-08T09:10:00Z",
        ),
        comment(
            9954,
            "coderabbitai[bot]",
            proof_reply(
                "271-ab-combined-proof",
                "rev-7",
                "3333dddd",
                prose=(
                    "`refinement_sound` is substantive and non-vacuous, its"
                    " preconditions are satisfiable, and its correspondence to"
                    " the shipped transition is stated. No unresolved proof"
                    " concern remains, and this reply echoes the revision in"
                    " force."
                ),
            ),
            "2026-11-08T09:15:00Z",
        ),
    ],
    # Both deliverables are in the change: the plan the completeness verdict is
    # about and the proof the proof verdict is about. A candidate carrying only
    # one of them would leave the other assessment describing a file this PR
    # does not touch, and a careful run would hold for that reason instead of
    # on the combined rule.
    paths=[PLAN_PATH, PROOF_PATH],
    cs_mode="clean",
))

scenario(Case(
    name="combined-proof-pending",
    head="8888cccc",
    draft=True,
    comments=[
        comment(
            9981,
            "buzzybee-df12",
            request("271-ab-combined-pending", "rev-7", "8888cccc",
                proof_inventory=COMBINED_INVENTORY
            ),
            "2026-11-08T11:00:00Z",
        ),
        # Completeness is clear for the whole plan at this head and the
        # revision in force. It is current, so nothing about it can hold the
        # run; any hold here is the proof assessment's alone.
        comment(
            9982,
            "coderabbitai[bot]",
            reply(
                "271-ab-combined-pending",
                "rev-7",
                {
                    "label": "clear",
                    "head": "8888cccc",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "The whole approved plan is implemented at this head."
                        " No in-scope rework remains."
                    ),
                },
            ),
            "2026-11-08T11:05:00Z",
        ),
        comment(
            9983,
            "pandalump",
            proof_request("271-ab-combined-pending-proof", "8888cccc", "rev-7"),
            "2026-11-08T11:10:00Z",
        ),
        # The proof assessment is still being decided: the reply says so in
        # words rather than stating a verdict. A reply that is neither clear nor
        # a finding is pending, and a pending assessment cannot clear.
        comment(
            9984,
            "coderabbitai[bot]",
            proof_reply(
                "271-ab-combined-pending-proof",
                "rev-7",
                "8888cccc",
                label="pending",
                prose=(
                    "I have not finished the proof scrutiny. The lemma"
                    " `sound_of_refine` that `refinement_sound` applies is not"
                    " among the declarations in the proof file, and I have not"
                    " yet established whether its starting condition can hold."
                    " I will answer once that is settled; treat this as pending"
                    " rather than clear."
                ),
            ),
            "2026-11-08T11:15:00Z",
        ),
    ],
    paths=[PLAN_PATH, PROOF_PATH],
    cs_mode="clean",
))

scenario(Case(
    name="combined-proof-stale-verdict",
    head="9999dddd",
    draft=True,
    comments=[
        comment(
            9991,
            "buzzybee-df12",
            request("271-ab-combined-stale-verdict", "rev-7", "9999dddd",
                proof_inventory=COMBINED_INVENTORY
            ),
            "2026-11-08T12:00:00Z",
        ),
        # Completeness is clear, current, and echoes the revision in force, so
        # the completeness side is not what holds this run. Only the proof
        # verdict is out of date, which is what separates this case from
        # `combined-proof-stale-revision`, where both verdicts are stale and
        # the hold does not isolate the proof assessment.
        comment(
            9992,
            "coderabbitai[bot]",
            reply(
                "271-ab-combined-stale-verdict",
                "rev-7",
                {
                    "label": "clear",
                    "head": "9999dddd",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "The whole approved plan is implemented at this head."
                        " No in-scope rework remains."
                    ),
                },
            ),
            "2026-11-08T12:05:00Z",
        ),
        comment(
            9993,
            "pandalump",
            proof_request("271-ab-combined-stale-verdict-proof", "9999dddd", "rev-7"),
            "2026-11-08T12:10:00Z",
        ),
        # The proof reply is clear for a head that is not this candidate. The
        # service accepted a verdict; it simply does not apply here. A run that
        # treats any clear proof verdict as clearing would mark ready.
        comment(
            9994,
            "coderabbitai[bot]",
            proof_reply(
                "271-ab-combined-stale-verdict-proof",
                "rev-7",
                "aaaa1111",
                prose=(
                    "`refinement_sound` is substantive and non-vacuous at the"
                    " head I was given, its preconditions are satisfiable, and"
                    " no unresolved proof concern remains."
                ),
            ),
            "2026-11-08T12:15:00Z",
        ),
    ],
    paths=[PLAN_PATH, PROOF_PATH],
    cs_mode="clean",
))

scenario(Case(
    name="combined-proof-stale-revision",
    head="4444eeee",
    draft=True,
    comments=[
        # The head does not change in this case, and neither does the plan file
        # at it: the transition is the approval, rev-7 to rev-8, recorded out
        # of band. So both earlier requests were asked against the revision
        # approved at the time and cite the blob the file has at this head,
        # which is the rev-8 blob — the template asks for the file's blob at
        # the published head, not for the approved revision's. Quoting the
        # rev-7 blob here would describe a file this head never served, which
        # is a contradiction in the premise rather than the stale approval the
        # case exists to rehearse.
        comment(
            9961,
            "buzzybee-df12",
            request("271-ab-combined-stale", "rev-7", "4444eeee",
                blob=PLAN_BLOB_REV8,
                proof_inventory=COMBINED_INVENTORY
            ),
            "2026-11-08T09:20:00Z",
        ),
        comment(
            9962,
            "coderabbitai[bot]",
            reply(
                "271-ab-combined-stale",
                "rev-7",
                {
                    "label": "clear",
                    "head": "4444eeee",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "The whole approved plan is implemented at this head."
                        " No in-scope rework remains."
                    ),
                },
            ),
            "2026-11-08T09:25:00Z",
        ),
        comment(
            9963,
            "pandalump",
            proof_request(
                "271-ab-combined-stale-proof",
                "4444eeee",
                "rev-7",
                blob=PLAN_BLOB_REV8,
            ),
            "2026-11-08T09:30:00Z",
        ),
        comment(
            9964,
            "coderabbitai[bot]",
            proof_reply(
                "271-ab-combined-stale-proof",
                "rev-7",
                "4444eeee",
                prose=(
                    "`refinement_sound` is substantive and non-vacuous, and no"
                    " unresolved proof concern remains at the revision this"
                    " reply echoes."
                ),
            ),
            "2026-11-08T09:35:00Z",
        ),
    ],
    paths=[PLAN_PATH, PROOF_PATH],
    # Neither reply is wrong in itself: both are clear, both are bound to this
    # base/head, and both echo the revision they were given. What moved is the
    # plan file, which now carries `rev-8`. So the only reason to hold is that
    # the revision in force is no longer the one either verdict is recorded
    # against — and the plan file, not the replies, is what says so.
    plan_revision="rev-8",
    plan_blob=PLAN_BLOB_REV8,
))

scenario(Case(
    name="combined-proof-stale-plan-revision",
    head="7777dddd",
    draft=True,
    comments=[
        # Asked while `rev-7` was the approved revision, at the head that was
        # already published and already carried the rev-8 text. The template
        # asks for the file's blob at this head, so the request quotes the
        # rev-8 blob beside the rev-7 approval — the pairing an approval
        # transition at a fixed head produces. Quoting the rev-7 blob here
        # would name a file this head never served.
        comment(
            9995,
            "pandalump",
            proof_request(
                "271-ab-combined-stale-plan-proof",
                "7777dddd",
                "rev-7",
                blob=PLAN_BLOB_REV8,
            ),
            "2026-11-08T12:20:00Z",
        ),
        # The proof reply is clear, and its head is this candidate's. What it
        # echoes is `rev-7`, the revision in force when it was asked. Nothing
        # about the reply was wrong at the time it was written.
        comment(
            9996,
            "coderabbitai[bot]",
            proof_reply(
                "271-ab-combined-stale-plan-proof",
                "rev-7",
                "7777dddd",
                prose=(
                    "`refinement_sound` is substantive and non-vacuous at this"
                    " head, its preconditions are satisfiable, and no unresolved"
                    " proof concern remains at the plan revision this reply"
                    " echoes."
                ),
            ),
            "2026-11-08T12:25:00Z",
        ),
        # Then the plan moved to `rev-8`, and completeness was asked again
        # against the revision now in force. This reply is clear, bound to the
        # candidate, and echoes `rev-8`, so nothing on the completeness side can
        # hold the run. The proof verdict was never re-asked and still stands at
        # `rev-7`.
        comment(
            9997,
            "buzzybee-df12",
            request(
                "271-ab-combined-stale-plan",
                "rev-8",
                "7777dddd",
                blob=PLAN_BLOB_REV8,
                proof_inventory=COMBINED_INVENTORY,
            ),
            "2026-11-08T13:00:00Z",
        ),
        comment(
            9998,
            "coderabbitai[bot]",
            reply(
                "271-ab-combined-stale-plan",
                "rev-8",
                {
                    "label": "clear",
                    "head": "7777dddd",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "The whole approved plan is implemented at this head."
                        " No in-scope rework remains."
                    ),
                },
            ),
            "2026-11-08T13:05:00Z",
        ),
    ],
    paths=[PLAN_PATH, PROOF_PATH],
    # The plan file, and only it, says the revision in force moved. The
    # completeness reply already names the new one; the proof reply still names
    # the old.
    plan_revision="rev-8",
    plan_blob=PLAN_BLOB_REV8,
    cs_mode="clean",
))

scenario(Case(
    name="combined-proof-unbound-revision",
    head="5555ffff",
    draft=True,
    comments=[
        comment(
            9971,
            "buzzybee-df12",
            request("271-ab-combined-unbound", "rev-7", "5555ffff",
                proof_inventory=COMBINED_INVENTORY
            ),
            "2026-11-08T09:40:00Z",
        ),
        comment(
            9972,
            "coderabbitai[bot]",
            reply(
                "271-ab-combined-unbound",
                "rev-7",
                {
                    "label": "clear",
                    "head": "5555ffff",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "The whole approved plan is implemented at this head."
                        " No in-scope rework remains."
                    ),
                },
            ),
            "2026-11-08T09:45:00Z",
        ),
        comment(
            9973,
            "pandalump",
            proof_request("271-ab-combined-unbound-proof", "5555ffff", "rev-7"),
            "2026-11-08T09:50:00Z",
        ),
        # The proof question named `rev-7`, and this reply assesses the proofs
        # without echoing a revision at all. It is a clear verdict on the right
        # proofs for the right base/head, so nothing else about it is deficient;
        # what it fails to do is bind itself to an approved revision. A reply
        # that echoes only the base/head cannot establish which revision it
        # inspected, which is exactly the case the rule names.
        comment(
            9974,
            "coderabbitai[bot]",
            "\n".join(
                [
                    "**Verdict: clear**",
                    "",
                    "- **Assessment-ID:** `271-ab-combined-unbound-proof`",
                    f"- **Assessed base/head:** {BASE}...5555ffff",
                    "- **Assessed subject:** `refinement_sound`",
                    "",
                    "`refinement_sound` is substantive and non-vacuous, and no"
                    " unresolved proof concern remains.",
                ]
            ),
            "2026-11-08T09:55:00Z",
        ),
    ],
    paths=[PLAN_PATH, PROOF_PATH],
    cs_mode="clean",
))

scenario(Case(
    name="combined-proof-candidate-mismatch",
    head="6666aaaa",
    draft=True,
    comments=[
        comment(
            9981,
            "buzzybee-df12",
            request("271-ab-combined-mismatch", "rev-7", "6666aaaa",
                proof_inventory=COMBINED_INVENTORY
            ),
            "2026-11-08T10:00:00Z",
        ),
        comment(
            9982,
            "coderabbitai[bot]",
            reply(
                "271-ab-combined-mismatch",
                "rev-7",
                {
                    "label": "clear",
                    "head": "6666aaaa",
                    "subject": WHOLE_PLAN,
                    "prose": (
                        "The whole approved plan is implemented at this head."
                        " No in-scope rework remains."
                    ),
                },
            ),
            "2026-11-08T10:05:00Z",
        ),
        comment(
            9983,
            "pandalump",
            proof_request("271-ab-combined-mismatch-proof", "6666aaaa", "rev-7"),
            "2026-11-08T10:10:00Z",
        ),
        # A clear, revision-bound proof verdict — for a different candidate.
        # This is the wrong-base/head control: the reply was recorded against an
        # earlier head, so it describes proofs as they stood there. Accepting it
        # would clear a candidate nobody assessed, while every other field of
        # the reply still looks satisfactory.
        comment(
            9984,
            "coderabbitai[bot]",
            proof_reply(
                "271-ab-combined-mismatch-proof",
                "rev-7",
                "7777bbbb",
                prose=(
                    "`refinement_sound` is substantive and non-vacuous at the"
                    " head this reply assessed, and no unresolved proof"
                    " concern remains."
                ),
            ),
            "2026-11-08T10:15:00Z",
        ),
    ],
    paths=[PLAN_PATH, PROOF_PATH],
    cs_mode="clean",
))

# The two crossing cases. They exist because the readiness rules live in
# `pr-babysitting` while the packet that says which assessments apply lives in
# `sdlc-implementation`, and the handoff between them was only ever rehearsed
# in-memory: the boundary test drives the receiver from the shipped packet, but
# no run has started at the sender and crossed. Each case reuses one of the two
# decisions the readiness rule turns on, so the crossing is the only variable:
#
# * `crossing-whole-plan` is the permitting arm. Both skills have to agree that
#   the whole approved plan cleared at the revision in force, and the run then
#   transitions.
# * `crossing-subset-clear` is the holding arm. The verdict says `clear` and
#   the run still holds, because the hole is in the answer, not the crossing:
#   an agent that carried the packet faithfully still finds the declared subset
#   and must refuse readiness. A crossing that "fixed" the outcome by widening
#   the verdict would show the rehearsal was driving the decision rather than
#   observing it.
scenario(Case(
    name="crossing-whole-plan",
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
    cs_mode="clean",
    start_skill="sdlc-implementation",
))

scenario(Case(
    name="crossing-subset-clear",
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
    start_skill="sdlc-implementation",
))

print("wrote", sorted(path.name for path in OUT.iterdir()))
