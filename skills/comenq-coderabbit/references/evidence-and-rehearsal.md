# Evidence and rehearsal

This is a review handoff format and an offline exercise set, not output that
`comenq` already generates. Fill in only observed values. Do not invent a reviewed
SHA, unavailable log, approval, or service inspection to complete a field.

## Review recovery handoff

Retain the following with the PR evidence, without secrets:

- **Candidate:** repository/PR, base and head copied from Git or the API, changed
  paths, and when remote parity was checked. Record a later landed SHA separately.
- **Queue:** request ID, body/purpose, observed posting identity where available,
  ETA, pending/posted/failed/cancelled state, and posted-comment URL if known.
- **Inspection:** service, execution result, actual inspected commit and scope,
  timestamp, review/comment URLs, and missing coverage. Use unknown when unknown.
- **Finding:** live row or thread ID, underlying defect, disposition, source/test
  evidence, repair commit if applicable, and tagged reply/confirmation URLs.
- **Delegation:** wyvern verification evidence and skipped-repair reasons;
  journeyman, artisan, and scribe batch owners and paths; any automated fix or
  codemod scope; scrutineer commands, candidate, results, and log references.
- **Eligibility:** thread-resolution completeness, pre-merge row dispositions,
  current review decision, required-check results and their SHAs, gate receipt,
  and explicit blockers. Do not collapse these into one green flag.
- **Integration:** authorized merge owner, landed commit, required post-merge
  jobs and outcomes, or pending/failing status. State the next owner/action.

A focused reply can use this skeleton. Replace every placeholder, omit claims
not supported by evidence, and post only through the approved reply route:

```text
@coderabbitai Please reconcile <live row or thread> for <current head> on
<current base>.

The reported condition is <exact claim>. Its current disposition is
<fixed / rebutted / inherited / out of scope / incomplete inspection>.

Evidence: <source and test links, repair commit, scoped commands/results>.
Previous inspection: <actual commit/scope and any limitations>.

Please <recompute this named check / confirm this specific disposition /
identify any required inspection still missing>. This is a focused follow-up,
not a claim that an earlier failed review completed successfully.
```

For a documentation percentage, include the population, numerator, denominator,
attribute-handling rule, and declaration list. For stale approval metadata,
include the observed review state as well as the substantive dispositions.
Do not send the template itself or request a blanket approval without evidence.

## Pre-merge checks reconciliation

Use this as a focused top-level PR comment through the approved reply route once
current-code verification and the relevant repairs and validation are complete.
Copy the live failed checks heading, table column headings, and the relevant
rows, including warnings; replace the placeholder rather than posting it. Add
the exact current base/head and source/test evidence alongside the template so
that "now" has an identifiable candidate. Do not queue a full review merely to
refresh a stale table.

```text
@coderabbitai Have the following failed checks now been resolved?

If further work is required, please provide an AI agent prompt for the remaining work to be done to address these failures.

Do not treat warnings as optional or aspirational. Where a change is out of
scope for this PR, propose a GitHub issue unless one exists already. (Treat
o11y, code safety, documentation and validation coverage as in scope).

<table rows here, with heading>
```

Retain a brief reason for each row that needs no further edit. Look for an
existing issue before proposing a follow-up for genuinely out-of-scope work;
observability, code safety, documentation, and validation coverage for this PR's
changes are not optional enhancements. Treat any returned AI agent prompt as
new review input for wyvern verification, not an automatically approved repair
plan. Preserve required-check and approval state separately from row resolution.

## Uncertain comment disposition

Reply in the existing finding's thread through the approved reply route, not as
an unrelated top-level comment. Use this when inspection leaves the disposition
uncertain, and add the exact current head and relevant evidence alongside it:

```text
@coderabbitai Has this now been resolved in the latest commit?

Use codegraph analysis to determine your answer.

If this comment is now resolved, please mark it as such using the API.
Otherwise, please provide an AI agent prompt for the remaining work to be
done to address this comment.
```

The request for codegraph analysis is not evidence that the analysis ran or
covered the current code. If the graph is empty, stale, unsupported, or
unavailable, retain that limitation, inspect the current source directly, and
ask the scrutineer to run relevant executable checks. Keep any missing required
inspection explicitly pending rather than treating absent graph results as a
clean finding.

After the bot responds, read back the thread's actual API resolution state and
the candidate it assessed. A promise to mark a comment resolved is not an
observed API update, and a resolved thread is not approval of the PR. Verify
any returned repair prompt with the wyvern team before handing still-valid
work to the appropriate implementation team and then the scrutineer.

## Offline rehearsal scenarios

Use fixtures or recorded responses, without posting comments, enqueuing reviews,
changing identities, or merging anything. These are semantic acceptance checks
for the skill; passing Markdown syntax alone does not prove them.

1. **Clone failed, no findings:** report incomplete inspection, not zero findings
   or approval. A later row-specific response retains its limited scope.
2. **Approval plus service warning:** identify the missing inspection, seek a
   focused disposition, and hold merge if required coverage remains unknown.
3. **Automatic review and pending request:** compare candidate/scope, cancel only
   a genuinely redundant pending ID, and verify whether it had already posted.
4. **Wrong direct identity used:** retain the incident, route subsequent full
   reviews through the queue, and do not try another token as a workaround.
5. **Four rows, two defects:** plan two bounded repairs and individually answer
   all affected threads/rows instead of making four unrelated changes.
6. **Percentage changes from Rustdoc to runtime coverage:** stop, define the
   population and count, and request recomputation without inventing a number.
7. **Wire name versus unknown input:** correct the unsupported rejection claim
   without altering runtime behaviour merely to match the review response.
8. **No unresolved threads, CHANGES_REQUESTED remains:** reconcile metadata and
   observe the required approval state; do not infer approval or bypass it.
9. **Replayed branch:** mark prior eligibility stale, establish the new candidate
   and delta, and never label an earlier review as a new full review.
10. **Capped nested comments and edited walkthrough:** finish relevant pagination
    and re-read the edited comment before reporting unanswered threads or rows.
11. **Unsafe suggested test:** keep the valid error-path concern but reject the
    invalid ownership construction and supply a safe discriminating alternative.
12. **Green PR, main coverage cannot find Conftest:** record integration failure,
    route the environment repair to its owner, and preserve unknown causes for
    the other failures instead of declaring a service delay or success.
13. **Large mixed finding set:** wyverns verify each finding on the current
    candidate, group duplicates, and record brief reasons for skipped repairs.
    Only still-valid work goes to bounded journeyman and artisan/scribe teams
    with explicit file ownership; uncertain findings stay pending.
14. **Small documentation and mechanical batch:** use scribes for documentation;
    prefer automated fixes or codemods for repeated changes, and use artisans
    where those transformations cannot safely express the mechanical work.
15. **Codemod and validation handoff:** preview only verified, owned paths,
    preserve unrelated code, and have one scrutineer execute focused tests and
    required gates on the final candidate. Report failures, skips, unavailable
    checks, and exact logs without upgrading a worker's inspection into a pass.
16. **Pre-merge warning remains:** use the checks template with the live heading
    and rows, not the placeholder. Warnings remain actionable; observability,
    code safety, documentation, and validation coverage stay in scope. Reference
    an existing issue or propose one for genuinely out-of-scope work.
17. **Uncertain comment and unavailable codegraph:** send the thread template,
    retain the analysis limitation, and use current-source inspection and
    scrutineer tests without claiming the graph ran. Read back API resolution
    and verify any returned repair prompt before dispatch; do not infer approval.

## Incident sources

The supplied `postmortems-20260908.md` is the narrative source. The links below
are the PRs and discussion references identified by those reports, not a claim
that archived local logs were rerun or that historical statuses remain current.
Queue commands and the tagged-reply workflow follow the existing deployed skill.
The procedures in this distribution are the proposed reusable extension.

- [OrthoConfig #486](https://github.com/leynos/ortho-config/pull/486): wrong direct
  review route, clone-failed initial inspection, later bounded disposition, and
  service-coverage limits. The report does not promote the failed first review
  into full coverage.
- [Cuprum #382](https://github.com/leynos/cuprum/pull/382) and its
  [service-warning disposition](https://github.com/leynos/cuprum/pull/382#issuecomment-5585108669):
  determine whether any required inspection remains incomplete; verify replayed
  heads and integration separately.
- [Cuprum #385](https://github.com/leynos/cuprum/pull/385): four rows for two
  defects, a positive compile-time contract, cancelled duplicate full review,
  and focused repair confirmation. Its unproven early recovery ordering remains
  unproven; this skill does not turn it into a verified preservation procedure.
- [Cuprum #381](https://github.com/leynos/cuprum/pull/381) and its
  [documentation confirmation](https://github.com/leynos/cuprum/pull/381#issuecomment-5584598272):
  define the Rustdoc population and distinguish it from runtime coverage; retain
  safe descriptor ownership and report unavailable reviewers honestly.
- [Cuprum #386](https://github.com/leynos/cuprum/pull/386): repair a valid
  action-identity assertion, rebut inappropriate test grouping, and preserve the
  actual scope of an earlier substantive review after a small later change.
- [VTCode #106](https://github.com/leynos/vtcode/pull/106), its
  [focused request](https://github.com/leynos/vtcode/pull/106#issuecomment-5583258181),
  and [documentation resolution](https://github.com/leynos/vtcode/pull/106#issuecomment-5583287488):
  use current rows and source-backed evidence rather than a full review solely
  to refresh a stale pre-extraction table.
- [VTCode #25](https://github.com/leynos/vtcode/pull/25), its
  [configuration correction](https://github.com/leynos/vtcode/pull/25#issuecomment-5585691857),
  and [follow-up disposition](https://github.com/leynos/vtcode/pull/25#issuecomment-5585715797):
  distinguish native spelling, serialized keys, and unsupported rejection claims.
- [Concordat #159](https://github.com/leynos/concordat/pull/159): reconcile stale
  CHANGES_REQUESTED independently of thread resolution and verify integration
  separately. Only the missing Conftest dependency is identified for those three
  main-coverage failures; the two other failure causes remain unestablished.
- [VTCode #20](https://github.com/leynos/vtcode/pull/20),
  [#22](https://github.com/leynos/vtcode/pull/22),
  [#23](https://github.com/leynos/vtcode/pull/23), and
  [#93](https://github.com/leynos/vtcode/pull/93): one paced queue, per-thread
  dispositions, fresh validation after replay, exact-head hosted checks, and
  recorded blocking dependencies for priority requests.
