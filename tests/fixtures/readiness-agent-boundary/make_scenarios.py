#!/usr/bin/env python3
"""Generate the controlled GitHub facts for each readiness scenario.

The facts are what a real `gh` would return for this repository: the PR's
draft and check state, the CodeRabbit commit status, and the issue-comment
thread carrying the assessment request and its reply. The harness supplies
them through an executable `gh` shim, so the agent under test reads fixed
GitHub facts and the only variable is the assessment evidence.
"""

from __future__ import annotations

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
    return {
        "id": 7701 + index,
        "name": check["name"],
        "status": check["status"],
        "conclusion": check["conclusion"],
        # The hosted CodeScene check's own output. Without it the agent can see
        # the check passed but not that it listed no advisory findings, and the
        # skill makes an outstanding issue block readiness even on a passing
        # check.
        "output": {
            "title": "No issues found" if scene else "",
            "summary": (
                "No advisory findings, gate failures or code-health declines."
                if scene
                else ""
            ),
            "annotations_count": 0,
        },
    }


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


def api_map(comments: list[dict[str, object]]) -> dict[str, object]:
    """Return every recorded API route for one scenario."""
    return {
        r"/issues/\d+/comments": comments,
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
            "total_count": len(GREEN),
            "check_runs": [check_run(index, check) for index, check in enumerate(GREEN)],
        },
        r"/contents/docs/execplans(?:[?#]|$)": plan_contents(),
    }


def scenario(
    name: str,
    *,
    head: str,
    draft: bool,
    comments: list[dict[str, object]],
) -> None:
    """Write one scenario's facts and prompt."""
    facts = {
        "login": "experiment-owner",
        "pr_checks": "".join(
            f"{check['name']}\t{check['status']}\t{check['conclusion']}\n" for check in GREEN
        ),
        "pr": {
            "number": PR,
            "url": f"https://github.com/{REPO}/pull/{PR}",
            "baseRefOid": BASE,
            "headRefOid": head,
            "isDraft": draft,
            "mergeStateStatus": "BLOCKED" if draft else "CLEAN",
            "reviewDecision": "",
            "statusCheckRollup": GREEN,
        },
        "pr_ready_response": f"Pull request {REPO}#{PR} is marked as ready for review",
        "api": api_map(comments),
        "coords": {"repository": REPO, "pull_request": PR},
    }
    directory = OUT / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "facts.json").write_text(
        json.dumps(facts, indent=2) + "\n", encoding="utf-8"
    )


scenario(
    "subset-only",
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
)

scenario(
    "superseded-revision",
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
)

scenario(
    "current-whole-plan",
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
)

scenario(
    "subset-clear",
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
)

scenario(
    "proof-only-pending",
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
)

scenario(
    "proof-only-cleared",
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
)

print("wrote", sorted(path.name for path in OUT.iterdir()))
