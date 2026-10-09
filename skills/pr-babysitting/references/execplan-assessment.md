# ExecPlan implementation and proof assessments

## Applicability and ownership

This is the hosted assessment contract for an assignment implementing an
approved ExecPlan, including a handoff from `sdlc-implementation`. A PR that
only authors a plan does not become an implementation assignment because it
contains an ExecPlan file. Establish applicability from accepted scope. Apply
the proof assessment whenever implementation introduces or materially changes a
proof, including outside an ExecPlan assignment.

Accept a red or draft PR. Use the parent skill's CI repair, findings,
publication, and review-response loop; do not send it back merely to obtain
green CI or readiness. Keep the implementation owner's plan, verification
inventory, acceptance mapping, and associated roadmap status synchronized with
repairs. Missing milestones remain implementation work, not a waived acceptance
criterion. Request bounded repairs within the existing authority.

Before requesting either assessment, require passing applicable deterministic
correctness and quality gates, including verification obligations, for the
published candidate. Verify remote parity and record its base/head, plan
revision, proof inventory, and inspection scope in the shared delivery ledger.
The milestone CLI result does not substitute for these hosted assessments.

## Comment routing

Read [comment routes and templates](comments.md). Assessments are conversations
through tagged issue comments, not formal CodeRabbit reviews. Post each
applicable question below as a separate top-level issue comment through the
assigned token procedure, selecting an authorized token with `shuf` from
`~/.local/share/github-tokens`. Reuse that procedure; never source, print,
copy, or expose tokens, or substitute a connector's implicit identity.

Record and read back the comment body, ID, URL, and candidate. On ambiguous
posting failure, inspect the discussion before retrying. Token rotation is not
permission to evade a cooldown. Missing authority or credentials leaves a
prepared comment and a blocker, not a fallback account.

Assessment conversations never go through `comenq`. Use the same manual-comment
route for necessary follow-ups after repairs or changed assessment scope,
linking the original request and response and identifying the new base/head. Do
not add formal `review`, `full review`, or `resume` commands. Fresh formal
reviews and their rate-limit recovery use `comenq-coderabbit` only after the
parent skill verifies readiness.

Before posting, capture the observation baseline described in
[awaiting CodeRabbit](awaiting-coderabbit.md). After posting, read back the
server-assigned request ID and timestamps and immediately begin that bounded
foreground wait. Read the complete substantive reply and reconcile every valid
finding before declaring the assessment clear. An acknowledgement or unrelated
new bot comment is not the answer. Do not return merely because the question
was posted or a few polls found nothing; preserve the pending request until a
response, an explicit service blocker, or the observation deadline.

Do not repeat an unanswered request or enqueue it because a draft-skip notice
exists. That notice concerns automatic reviews. A genuine chat failure or chat
rate limit remains an assessment blocker: honour its retry advice and record it
separately. Any authorized retry retains this assessment route and first checks
for a late reply; token rotation cannot bypass the limit.

## ExecPlan completeness and correctness

Preserve this opening, substituting the actual approved plan path. Do not post
unresolved placeholders. Supplement it with the published candidate, acceptance
evidence, and honest limitations:

```text
@coderabbitai please assess the implementation in this PR for completeness and correctness against the execplan:

> `docs/execplans/<slug>.md`

Published head: <full head SHA>; comparison base: <full base SHA>.
Acceptance evidence: <commands, results, and evidence links>.
Known limitations: <established limitations or none established>.
Assessment-ID: <unique request marker>.

Please echo the Assessment-ID and assessed base/head in your substantive reply.
This is an assessment conversation, not a request to start a formal PR review.

Identify remaining in-scope omissions or correctness defects and any access
or inspection limitations. Assess the implementation, not just the plan text.
```

CodeRabbit must address the actual plan and implementation with no remaining
in-scope rework. An acknowledgement, silence, generic approval, missing
inspection, or plan progress checkbox does not establish that result.

## Proof inventory and specific scrutiny

Cover introduced CrossHair, Kani, Verus, LemmaScript, and comparable proofs,
and substantive changes to existing propositions, assumptions, harnesses, or
verified production code. Inspect symbols, contracts, generated obligations,
and verifier configuration, not just filenames containing `proof`.

For each proof, identify the repository-relative source path and qualified
proof, lemma, harness, or contracted function with its named clause. Include
source and generated paths when both actually exist and are relevant. Name the
proposition, acceptance requirement, production function or transition,
preconditions, axioms, stubs, trusted boundaries, domain and bounds, tool and
backend versions, flags, exact command, and per-obligation outcome.

Include a non-vacuity argument: satisfiable preconditions, reachable cases, and
a negative control or justified independent witness/counterexample. Explain the
link from any model to the shipped implementation. Reject circular reasoning,
assuming the conclusion, or excluding every interesting input. Do not present
finite examples or a timeout without a counterexample as an unbounded proof.
Read the relevant verifier's version-matched documentation; record bounded,
conditional, unsupported, and inconclusive results honestly. Required
undischarged obligations remain blockers even if a process exits zero.

Post this separate question before ready-for-review, retaining its wording and
replacing the parenthetical with actual paths and named references:

<!-- markdownlint-disable MD013 -->

```text
@coderabbitai are you satisfied that the introduced proof(s) (<proof file paths with named proof references>) is substantive, rigorous, and well-founded?

Published head: <full head SHA>; comparison base: <full base SHA>.
Proof inventory and claims: <paths, qualified names, and propositions>.
Production correspondence: <implementation paths and relevant requirements>.
Assumptions, trusted boundaries, domain, and bounds: <specific evidence>.
Verifier evidence: <versions, commands, configuration, and per-proof outcomes>.
Non-vacuity and limitations: <witnesses, negative controls, and residual gaps>.
Assessment-ID: <unique request marker>.

Please echo the Assessment-ID and assessed base/head in your substantive reply.
This is an assessment conversation, not a request to start a formal PR review.

Check substance, rigour, foundations, and correspondence to production code.
Identify each unresolved concern or missing inspection explicitly.
```

<!-- markdownlint-enable MD013 -->

Require an explicit satisfactory assessment of the listed proofs with no
unresolved substantive proof concern. Verifier success and CodeRabbit's
judgement complement each other; neither replaces the other. When no proof is
affected, record a justified `not applicable` instead of posting an empty
inventory or creating a ceremonial proof.

## Readiness and later changes

The parent skill owns readiness. Both applicable assessments must clear for the
accepted candidate before its draft-to-ready transition. Reconcile the actual
substantive issue-comment responses, including edited-in-place replies. A
response that says the implementation is substantially complete but names
remaining in-scope defects has not cleared the gate. Fix, validate, push, and
await confirmation of the affected assessment. Never interpret a posted
request, green formal-review check, or queue receipt as completion.

Once those responses, green CI, and clear CodeScene findings cover the current
candidate, mark it ready and verify the transition. Only then inspect formal
review progress and rate limiting: await an active or automatic review, or use
`comenq-coderabbit` for an explicitly rate-limited review. The formal review is
a later stage, not the mechanism for obtaining the pre-ready assessment.

An already-ready PR stays ready; obtain missing assessments before merge.
Subsequent repairs, proof changes, rebases, or retargeting require renewed
candidate-bound evidence and affected assessment coverage. Preserve earlier
evidence for its actual scope without relabelling it as a new review. Do not
set the PR back to draft. If the assessment service explicitly cannot process
the question, retain its response and report the specific blocker rather than
inferring failure from automatic draft-review policy. Do not bypass the gate.
Generic approval cannot discharge missing proof scrutiny.
