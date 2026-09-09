# Failure modes and recovery

These cases come from the supplied September 2026 implementation postmortems.
The procedures are reusable recommendations; the incident records do not prove
that a historical fix or review state applies to the PR currently being handled.
Source links and evidence limits are in
[Evidence and rehearsal](evidence-and-rehearsal.md#incident-sources).

## Wrong route or duplicate full review

**Recorded incidents:** OrthoConfig #486 used a direct request and an
unauthorized-for-review identity instead of the managed queue. Cuprum #385
cancelled a pending full review after an automatic review completed and used a
focused repair response. VTCode #93 recorded a train-blocking reason for queue
priority instead of duplicating the request.

**Recovery:** Stop issuing new requests. Inspect `comenq list`, `comenq hist`, and
PR comments to distinguish queued, posted, failed, and already reviewed work.
Preserve the wrongly routed request as part of the record; do not retrospectively
call it queued or delete evidence to conceal the mistake. Route subsequent new
full reviews and retries through the managed queue.

If an automatic or other review has completed the inspection needed for the
current candidate, cancel only the redundant pending request by its observed ID:

```bash
comenq del QUEUE_ID
```

Re-read the queue and PR activity after cancellation. The item may already have
posted; deleting a pending item is not cancellation of an in-flight review.
Do not cancel the only required inspection merely because some bot activity
exists. Do not claim that historical evidence already covers a changed head.

**Exit evidence:** Queue ID and observed disposition, posted-comment URL when
available, actual inspected commit/scope, and the outstanding need or accepted
review replacing the duplicate. On ambiguous delivery, reconcile history and
remote comments before retrying.

## Clone failure or service-health warning

**Recorded incidents:** OrthoConfig #486's first CodeRabbit review could not
clone the repository. A later response inspected the current diff and accepted
specific dispositions, but did not turn the earlier failure into full coverage.
Cuprum #382 had an approval with a service warning; a focused response explicitly
established that no required inspection remained incomplete.

**Recovery:** Read the failure message and review body, not only the check colour
or absence of inline comments. Classify a clone-failed review as incomplete.
Ask which inspection failed, whether it is required for this change, and what the
later response actually inspected. Keep completed partial findings, but mark
unknown coverage as unknown.

Supply source, tests, and current-head evidence for a focused follow-up where
that can resolve the warning through the existing policy. If required inspection
is still missing, diagnose the stated access, execution, or service problem and
queue one necessary retry after it is addressed. Do not speculate about a root
cause not established by the report. Do not retry on a loop, switch identities,
or grant broader repository access without authorization.

**Exit evidence:** Original failure, inspected candidate and scope, the explicit
service disposition or completed replacement inspection, and any remaining
limitation. A successful comment post is never this exit evidence.

## Stale pre-merge table after a real repair

**Recorded incidents:** VTCode #106 resolved a documentation warning after a
private-test extraction through a focused current-row response, without a new
full review solely to refresh the table. Cuprum #385's four rows represented two
defects, repaired as one bounded batch.

**Recovery:** Fetch the current walkthrough issue comment, including the live
failed row and explanation. It is edited in place. Compare the row with the
current code, the reviewed commit where known, and all related thread replies.
Map duplicate rows to the same underlying defect, not to separate repair tasks.

For a remaining defect, repair and validate it within the owning worker's scope.
For a stale row, send the exact row name, current base/head, changed declarations
or paths, repair commit, and validation evidence through the approved focused
reply route. Tag `@coderabbitai` and ask it to recompute or explicitly reconcile
the row. Do not assume the table can refresh only after another full review.

**Exit evidence:** The bot's explicit disposition or refreshed current row,
linked to the candidate it assessed. Keep any required approval/check state
separate. A worker saying "already fixed" does not resolve the hosted row.

## Documentation percentage without a reproducible denominator

**Recorded incidents:** Cuprum #381's original documentation percentage was
withdrawn, then confused with runtime coverage. The agreed Rustdoc population
was Rust functions whose bodies contained added or modified lines, with
contiguous Rustdoc preceding attributes and the declaration. The verified count
was 34 of 34. VTCode #106 required documentation evidence for declarations
actually introduced by its extraction, not an invented percentage.

**Recovery:** Ask what is being measured before editing. Name the language,
comparison base/head, included declarations, treatment of attributes, numerator,
and denominator. Enumerate the relevant declarations and inspect their actual
documentation. Do not trust a regular expression count without checking that it
handles the language and attribute layout.

Keep Rustdoc/docstring coverage separate from executed-line or branch coverage.
Use the repository's agreed scope and threshold, not the historical 34-function
example as a universal rule. Add purpose documentation where genuinely absent;
do not add filler or change runtime behaviour to improve a number. Send the
measured list/count and source links in a focused request to recompute the row.

**Exit evidence:** Reproducible scope and count, the real documentation repair if
needed, and explicit hosted reconciliation. A withdrawn number stays withdrawn.

## Unsupported behavioural claim in a review response

**Recorded incident:** VTCode #25 correctly used native `BehaviourConfig` with
the following fixed TOML wire table:

```toml
[behavior]
```

A review table incorrectly claimed that `[behaviour]` input was rejected. The
corrected response separated serialization/round-tripping from handling of
unknown input fields.

**Recovery:** Trace each behavioural assertion to the actual source and a test
that proves that assertion. Separate what a serializer emits, what a parser
recognizes and applies, and what it merely accepts without an error. Where the
source does not establish a claim, withdraw it rather than making the claim more
confidently or changing production behaviour to fit the review narrative.

Correct the affected PR text and send a tagged, row-specific explanation with
the authoritative source/test references. Distinguish resolved, inherited, and
out-of-scope conditions. Do not claim raw logs were reopened or a scenario was
reproduced when only preserved postmortem evidence was available.

**Exit evidence:** Corrected claim, source/test proving its bounded meaning, and
the explicit current review disposition. Retain uncertainty about untested
contracts rather than inferring them from a nearby green test.

## Valid defect, invalid remedy, or missing acceptance test

**Recorded incidents:** Cuprum #385 needed a positive compile-time use of the
actual exported function after removing a negative fixture; runtime tests could
not prove constness. Cuprum #381 needed error-path tests and helper documentation,
but a proposed invalid owning descriptor would violate the tested ownership
contract. Cuprum #386 fixed an action-identity assertion while rebutting class
grouping for two tests with distinct boundaries and no shared setup.

**Recovery:** Triage the observation separately from its suggested implementation.
Accept missing contract coverage when valid, but preserve ownership, safety,
public API, and repository conventions. Choose a bounded test of the real
boundary. When appropriate, use a controlled discriminating mutation, preserve
and restore the exact source, and have the gate owner validate the restoration.
Do not manufacture invalid ownership or weaken assertions to satisfy a bot.

Group equivalent comments and pre-merge rows into one implementation batch.
Reply individually to every affected thread with the actual repair or evidenced
rebuttal; resolving one representative thread does not disposition all others.
Treat applicable test and documentation gaps as acceptance work, even for a
one-line implementation change.

**Exit evidence:** Safe, focused regression evidence, exact repair/restoration
identity, required gate results, and explicit dispositions for every associated
thread and row. A semantic review alone is not compiler or runtime validation.

## Answered threads but stale CHANGES_REQUESTED

**Recorded incident:** Concordat #159 had specific dispositions for its original
threads while review metadata still requested changes. Tagged reconciliation,
a bot-requested approval command, and observed current-head `APPROVED` completed
the review-state repair before merge.

**Recovery:** Read thread resolution, the live pre-merge table, review submissions
and their commit IDs, the aggregate review decision, required checks, and the
remote head independently. Zero new comments or zero unresolved threads is not
an approval. Check for remaining substantive objections before calling metadata
stale.

When the substantive requirements are satisfied, submit a focused tagged
reconciliation with the current candidate and evidence. Follow an approval
command only when the bot explicitly requests it in the current exchange and
project policy authorizes it; do not invent a command or replay a historical
one. Observe the resulting state and reviewed commit before reporting success.

**Exit evidence:** An acceptable current review decision under the repository's
policy, all required dispositions, and exact-head checks. If it stays unresolved,
hold merge and escalate. Do not dismiss reviews, waive checks, use administrator
bypass, or equate a polite bot reply with an approval event.

## Rebase, server replay, or a later narrow commit

**Recorded incidents:** VTCode's stacked layers and Cuprum #382/#385 reran gates
on replayed candidates. Cuprum #386 retained an earlier Codex review at its
actual functional scope and did not claim a new full review for the later
three-line assertion addition. Those are distinct evidence statements.

**Recovery:** Let the designated stack owner handle preservation and replay using
the stack skill. Record both old and new base/head identities. Mark old merge
eligibility stale, run required fresh gates, and assess the actual delta needing
inspection. A preserved old review can remain useful without becoming a review
of the new candidate. Original comment anchors are clues, not proof that the
finding disappeared.

A focused follow-up may suffice for a narrow delta under the established review
policy. Missing required inspection needs a queued review. Do not universally
requeue every unchanged comment, or universally carry approval across a rebase.
Verify the remote head again before handing merge authority back to its owner.

**Exit evidence:** New base/head, fresh applicable gates, reviewed delta and
explicit limitations, current required approval/check state, and remote parity.
Do not reconstruct long SHAs from a remembered prefix; copy executable output.

## Other reviewers unavailable or analysis scope unmeasured

**Recorded incidents:** Sourcery budget limits were unavailable review, not
approval, in several Cuprum and OrthoConfig reports. CodeGraph's Rust view could
be empty or stale. OrthoConfig #486's green CodeScene result expressly had no
quality gates for that configuration scope. Cuprum #381 also distinguished valid
empty new-issues output from output lacking useful comparison identity.

**Recovery:** Record each service separately with execution result, inspected
scope, candidate, and limitation. Do not compensate for a failed reviewer by
counting another review twice. Use direct source or executable validation where
appropriate, but say exactly what it substitutes for and what remains unmeasured.
Apply the existing required/advisory policy; do not promote an optional reviewer
to a new blocker or demote a required one to make the train move.

**Exit evidence:** Required inspection satisfied or explicitly pending; advisory
unavailability and unmeasured surfaces retained honestly in the handoff.

## Green review but failing integration job

**Recorded incident:** Concordat #159 passed its PR checks and obtained approval,
then main coverage failed. Three real-driver tests lacked Conftest in that
isolated environment. A missing spelling-base file and a permissions-test failure
also occurred, but their causes were not established in the report.

**Recovery:** Keep review acceptance, PR checks, and integration state separate.
Verify the landed commit and exact failing job. Return missing provisioning to
the owning implementation/CI workflow; reproduce the actual coverage invocation
with its declared dependencies. Do not call an execution failure an upload delay,
mock away the real driver, skip required tests, or guess the other failure causes.

**Exit evidence:** A separately verified corrective candidate and the required
integration results, or an explicit unresolved integration failure. Earlier
approval is not evidence that main passed.
