# ExecPlan implementation and proof assessments

## Applicability and ownership

This is the hosted assessment contract for an assignment implementing an
approved ExecPlan, including a handoff from `sdlc-implementation`. A PR that
only authors a plan does not become an implementation assignment because it
contains an ExecPlan file. Establish applicability from accepted scope.
Apply the proof assessment whenever implementation introduces or materially
changes a proof, including outside an ExecPlan assignment.

Accept a red or draft PR. Use the parent skill's CI repair, findings,
publication, and review-response loop; do not send it back merely to obtain
green CI or readiness. Keep the implementation owner's plan, verification
inventory, acceptance mapping, and associated roadmap status synchronized
with repairs. Missing milestones remain implementation work, not a waived
acceptance criterion. Request bounded repairs within the existing authority.

Before requesting either assessment, require passing applicable deterministic
correctness and quality gates, including verification obligations, for the
published candidate. Verify remote parity and record its base/head, plan
revision, proof inventory, and inspection scope in the shared delivery ledger.
The milestone CLI result does not substitute for these hosted assessments.

## Comment routing

Read [comment routes and templates](comments.md). The two initial assessment
comments below are explicit, narrow exceptions to the generic whole-review
queue rule. Post each as a separate top-level issue comment through the
assigned token procedure, selecting an authorized token with `shuf` from
`~/.local/share/github-tokens`. Reuse that procedure; never source, print,
copy, or expose tokens, or substitute a connector's implicit identity.

Record and read back the comment body, ID, URL, and candidate. On ambiguous
posting failure, inspect the discussion before retrying. Token rotation is
not permission to evade a cooldown. Missing authority or credentials leaves
a prepared comment and a blocker, not a fallback account.

All subsequent whole-assessment retries, fresh full or incremental reviews,
and review-resume requests use `comenq-coderabbit`, preserving the relevant
assessment question and current evidence. Inspect pending requests first.
Focused replies to a specific finding still use `comments.md`; they are not
a substitute route for a repeated full assessment.

## ExecPlan completeness and correctness

Preserve this opening, substituting the actual approved plan path. Do not
post unresolved placeholders. Supplement it with the published candidate,
acceptance evidence, and honest limitations:

```text
@coderabbitai please assess the implementation in this PR for completeness and correctness against the execplan:

> `docs/execplans/<slug>.md`

Published head: <full head SHA>; comparison base: <full base SHA>.
Acceptance evidence: <commands, results, and evidence links>.
Known limitations: <established limitations or none established>.

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
source and generated paths when both actually exist and are relevant. Name
the proposition, acceptance requirement, production function or transition,
preconditions, axioms, stubs, trusted boundaries, domain and bounds, tool and
backend versions, flags, exact command, and per-obligation outcome.

Include a non-vacuity argument: satisfiable preconditions, reachable cases,
and a negative control or justified independent witness/counterexample.
Explain the link from any model to the shipped implementation. Reject circular
reasoning, assuming the conclusion, or excluding every interesting input.
Do not present finite examples or a timeout without a counterexample as an
unbounded proof. Read the relevant verifier's version-matched documentation;
record bounded, conditional, unsupported, and inconclusive results honestly.
Required undischarged obligations remain blockers even if a process exits zero.

Post this separate question before ready-for-review, retaining its wording
and replacing the parenthetical with actual paths and named references:

<!-- markdownlint-disable MD013 -->

```text
@coderabbitai are you satisfied that the introduced proof(s) (<proof file paths with named proof references>) is substantive, rigorous, and well-founded?

Published head: <full head SHA>; comparison base: <full base SHA>.
Proof inventory and claims: <paths, qualified names, and propositions>.
Production correspondence: <implementation paths and relevant requirements>.
Assumptions, trusted boundaries, domain, and bounds: <specific evidence>.
Verifier evidence: <versions, commands, configuration, and per-proof outcomes>.
Non-vacuity and limitations: <witnesses, negative controls, and residual gaps>.

Check substance, rigour, foundations, and correspondence to production code.
Identify each unresolved concern or missing inspection explicitly.
```

<!-- markdownlint-enable MD013 -->

Require an explicit satisfactory assessment of the listed proofs with no
unresolved substantive proof concern. Verifier success and CodeRabbit's
judgement complement each other; neither replaces the other. When no proof
is affected, record a justified `not applicable` instead of posting an empty
inventory or creating a ceremonial proof.

## Readiness and later changes

The parent skill owns readiness. Both applicable assessments must clear for
the accepted candidate before its draft-to-ready transition. Reconcile
responses using its existing feedback loop, including edited-in-place issue
comments, and use `comenq-coderabbit` for rate-limit recovery. Never interpret
a posted request as completion.

An already-ready PR stays ready; obtain missing assessments before merge.
Subsequent repairs, proof changes, rebases, or retargeting require renewed
candidate-bound evidence and affected assessment coverage. Preserve earlier
evidence for its actual scope without relabelling it as a new review. Do not
set the PR back to draft. If the service cannot assess a draft, record the
workflow dependency and seek an explicit exception rather than silently
bypassing the gate. Generic approval cannot discharge missing proof scrutiny.
