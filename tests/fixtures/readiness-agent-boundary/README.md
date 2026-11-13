# Agent-boundary rehearsal for `pr-babysitting` readiness

These are recordings from a headless agent run against the shipped
`pr-babysitting` skill. They show that an agent reading that skill gates the
draft-to-ready transition on the shape of the ExecPlan assessment evidence, and
they are reproducible from the files here.

They are **rehearsals against a controlled GitHub surface, not live GitHub
runs**. They exercise the shipped text, not the GitHub API, not a live
CodeRabbit reply, and not the real CodeRabbit service. Record the executable
checks actually run in a PR's validation evidence; do not cite these files as
proof of a live scenario. They also do not judge a proof's mathematics: the
sandbox has no Lean toolchain, so no recording here runs the verifier or builds
`proofs/refinement/Theorem.lean`. What a permitting proof case shows is that a
run clears the readiness gate on an assessment reply of the required shape; it
does not show that the reply's verdict is mathematically sound, and the
outcomes say so in their own words.

## What each scenario pins

Every scenario serves the same green checks, the same base and the same
trusted, in-repository candidate; the only variable is the assessment evidence,
the hosted check's own output, or the recorded local CodeScene result. `base` is
`73d32981c7b7e8f52590a074873e28a9f369f0f9` throughout, and the PR starts as a
draft in each case. The two `proof-only-*` scenarios differ from the rest in
one more respect that is part of their premise: their PR body says no ExecPlan
applies and their diff is the proof they introduce. The seven `combined-*`
scenarios differ in the opposite direction: their PR changes the plan file and
a proof, so both assessments apply, and the plan and proof `contents` routes
both serve the text a run reads at its own head.

| Scenario                             | Head       | Completeness evidence                                                        | Proof evidence                                     | `gh pr ready` |
| ------------------------------------ | ---------- | ---------------------------------------------------------------------------- | -------------------------------------------------- | ------------- |
| `subset-only`                        | `aaaa1111` | **not clear**; subject is the declared subset (EP-M1, EP-M2)                 | none                                               | no            |
| `subset-clear`                       | `ffff6666` | **clear**; subject is still the declared subset                              | none                                               | no            |
| `superseded-revision`                | `bbbb2222` | **clear** whole plan, but recorded against `rev-6` while `rev-7` is in force | none                                               | no            |
| `current-whole-plan`                 | `cccc3333` | **clear** whole plan, `rev-7`                                                | none affected                                      | yes           |
| `codescene-advisory`                 | `9999aaaa` | **clear** whole plan, `rev-7`; every check green                             | none affected                                      | no            |
| `local-codescene-finding`            | `1111bbbb` | **clear** whole plan, `rev-7`; every check green                             | none affected                                      | no            |
| `local-codescene-unavailable`        | `2222cccc` | **clear** whole plan, `rev-7`; every check green                             | none affected                                      | no            |
| `proof-only-pending`                 | `dddd4444` | no ExecPlan, so not applicable                                               | question posted, unanswered                        | no            |
| `proof-only-cleared`                 | `eeee5555` | no ExecPlan, so not applicable                                               | **clear**, subject `refinement_sound`              | yes           |
| `combined-plan-and-proof`            | `3333dddd` | **clear** whole plan, `rev-7`; the plan file is changed too                  | **clear**, `refinement_sound`, `rev-7`             | yes           |
| `combined-proof-pending`             | `8888cccc` | **clear** whole plan, `rev-7`                                                | **pending**; the scrutiny is unfinished            | no            |
| `combined-proof-stale-verdict`       | `9999dddd` | **clear** whole plan, `rev-7`                                                | **clear**, for `…aaaa1111`, which is not this head | no            |
| `combined-proof-stale-plan-revision` | `7777dddd` | **clear** whole plan, `rev-8`, the revision in force                         | **clear**, for this head, but records `rev-7`      | no            |
| `combined-proof-stale-revision`      | `4444eeee` | clear verdict, but records `rev-7` while the plan file reads `rev-8`         | clear verdict, same stale `rev-7`                  | no            |
| `combined-proof-unbound-revision`    | `5555ffff` | **clear** whole plan, `rev-7`                                                | **clear**, but the reply echoes no plan revision   | no            |
| `combined-proof-candidate-mismatch`  | `6666aaaa` | **clear** whole plan, `rev-7`                                                | **clear**, for `…7777bbbb`, which is not this head | no            |
| `posted-then-answered`               | `eeee6666` | none seeded; the run posts the question and a scripted reply answers it      | none                                               | yes           |
| `crossing-whole-plan`                | `cccc3333` | **clear** whole plan, `rev-7`; run starts at `sdlc-implementation`           | none affected                                      | yes           |
| `crossing-subset-clear`              | `ffff6666` | **clear**; subject is still the declared subset                              | none                                               | no            |

`codescene-advisory` isolates the CodeScene gate from every other reason to
hold: the whole approved plan has cleared at the revision in force, and all
three checks conclude `SUCCESS`. Its CodeScene check is nevertheless titled
"Issues found" and its output lists one advisory — a complexity finding against
a file the PR changes, so the finding is about this candidate. The run stays in
draft, which is the skill's rule that "a passing check with advisory findings
still has outstanding issues". That pairing is what distinguishes a gate bound
to CodeScene's output from one reading the green badge: if the agent had
treated the passing conclusion as clearance, this scenario would have marked
the PR ready. The run cannot clear the finding either — the sandbox has no
checkout, and its `cs` is a stand-in that reports the same finding — so it also
shows the gate blocking rather than silently waiving an issue it could not fix.

`subset-only` and `subset-clear` differ only in the verdict; both stay in
draft. That pair isolates the subject check from the verdict, which a single
`not clear` subset case cannot do: `subset-clear` is a clear verdict on the
current revision whose only defect is the subject, and it stays in draft anyway.
`subset-clear` reads the hosted CodeScene check output, the PR's diff and its
file list rather than reporting them missing, so its hold is the subject and
nothing else. `superseded-revision` isolates the revision check: the verdict is
clear and the whole plan, and only the revision is stale. It is also the first
scenario to exercise the manual-comment route: the agent posts a follow-up
asking for a `rev-7` verdict, reads it back, and waits for an answer that the
facts never supply. The scenario therefore shows both halves of the
stale-revision rule — the follow-up path works, and readiness still waits.

### The cross-skill handoff cases

The other sixteen scenarios start a run at `pr-babysitting`. The readiness
rules live there, but the packet that says which assessments apply is produced
by `sdlc-implementation`, and until these two cases existed the handoff between
them was only ever rehearsed in memory:
`tests/test_readiness_handoff_boundary.py` drives the receiver from the shipped
packet, which establishes what the receiver does with one, not that an agent
asked to start at the sender produces one and carries it. `crossing-whole-plan`
and `crossing-subset-clear` are the same two decisions as `current-whole-plan`
and `subset-clear` — same head, same discussion, same checks — with
`start_skill` set so the run begins at the sender. The crossing is the only
difference, so a divergence in outcome is attributable to it.

The receiver's applicability is not read from whether a proof question was
posted. The question is the assessment, not the condition: deriving the
condition from its presence made a missing required question look like an
inapplicable assessment, so a proof-changing candidate whose proof question was
never posted cleared on the completeness reply alone. Two independent reads
decide the condition instead, and they are not symmetric.

The candidate's diff is the primary evidence. A change to the proof the
recording names affects it whatever any request says, so
`test_the_receiver_reads_applicability_from_the_diff_the_inventory_cannot_undo`
rewrites `combined-plan-and-proof`'s inventory to `none affected` and removes
its proof question, and requires the candidate to stay in draft. A sender's
sentence cannot unmake the file its own diff carries.

The completeness request's `Proof inventory:` line is the secondary read, and
it speaks only in the other direction: it can *add* applicability, by naming a
proof the diff does not carry. That is
`test_an_inventory_naming_a_proof_the_diff_omits_still_applies`, which gives
`current-whole-plan` — a candidate that changes only the plan — the combined
scenario's inventory and requires it to stop clearing, because the sender has
claimed an affected proof whose assessment is missing. The two holds are
therefore controlled separately, one by a diff the inventory denies and one by
an inventory the diff does not support.

`test_the_receiver_reads_applicability_from_the_inventory_not_the_question`
covers the missing question alone: it removes the proof question from
`combined-plan-and-proof` while leaving its inventory naming the proof, so the
case shows a missing question is pending rather than inapplicable. Reading
applicability without ever reconciling coverage was still wrong, which is
`test_a_non_empty_inventory_naming_another_proof_cannot_cover_the_change`: a
clean verdict on a differently-named proof cannot discharge the assessment of
the proof the candidate changed.

Every case takes the `current-whole-plan` control in the form its own rewrite
needs: the unchanged scenario changes no proof and says `none affected`, and it
must clear without a proof question. So no hold above is attributable to
deleting a comment, to the inventory sentence alone, or to a rename.

The runner enforces five things about such a run, because reaching the right
readiness decision is exactly what a receiver-only run already does:

- It opened `sdlc-implementation/SKILL.md` and `pr-babysitting/SKILL.md`. A
  `cd <skill>; cat SKILL.md` counts as an open, which is the form a real run
  used; matching only the joined path missed it and failed a run that had in
  fact crossed. A path that is merely named does not: a note written with
  `cat > notes.md` that mentions both skills is a write, and is refused. The
  read has to be a `Read` of the file or a shell reader — `cat`, `sed`, `head`
  and the like — with the file as its argument.

  The argument has to be the one the reader opens. A reader's leading operands
  are the pattern, program or script it consumes, not files:
  `grep -rn sdlc-implementation/SKILL.md notes/` searches `notes/` for that
  string, and `sed sdlc-implementation/SKILL.md/x/ notes.txt` rewrites
  `notes.txt` with the path as its script. An earlier version credited any word
  whose basename was `SKILL.md`, so a run that only quoted the path into a
  search was recorded as having followed the skill. Options are not files
  either, and `tr` is not a reader at all — every operand it takes is a
  character set — so it is absent from the table. The table records how many
  leading operands each reader consumes before its first file, and `sed` is the
  one whose table entry the command can override: `-e` or `-f` supplies the
  script, which makes the first operand a file.
  `test_the_handoff_probe_refuses_a_mention_that_read_something_else` covers
  the pattern and script shapes, and
  `test_the_handoff_probe_keeps_an_open_by_a_reader_with_options` covers the
  real opens with options, one parametrized case per shape so that no shape is
  carried by a call the probe credits for another reason.

  The file that was read has to be the skill's own manifest. Matching the
  skill's name anywhere in the call was not enough:
  `echo sdlc-implementation; cat pr-babysitting/SKILL.md` put the sender's name
  in the input and opened the receiver's file, and one call then satisfied both
  halves of the crossing's coverage. The check is now on the path component
  before `SKILL.md`, with a bare `SKILL.md` resolved against a `cd` in the same
  call. `test_the_handoff_probe_binds_a_read_to_the_skill_it_opened` covers it.

  The read also has to have succeeded on its own. A compound call's exit status
  belongs to its last command, so `cat <manifest> || true` and
  `cat <manifest>; true` exit zero whether or not the file was read; so does
  `cat <manifest> && a; b`, where the `;` ends the chain before the call's
  status is taken. A read is credited only when nothing follows it or every
  separator after it is `&&`. The read is still credited when it is last in its
  call, `ls -R; cat <manifest>` being the form a recorded run used, and a
  trailing `;` starts no command and so does not change that.
  `test_the_handoff_probe_binds_a_read_to_its_own_success`,
  `test_the_handoff_probe_binds_a_read_to_every_separator_after_it` and
  `test_the_handoff_probe_keeps_a_read_that_ends_its_call` cover the masking
  refusals and the reads they must not refuse.
- It did not decide before opening either skill. The two opens are not ordered
  against each other, because an agent may explore either file first without
  that meaning anything was carried. The decision is what orders them, and it
  is found through the stand-in's trace: a call is a `gh pr ready` only when
  the trace recorded that invocation, and only a Bash argument list is
  searched, so a scratch file named `gh pr ready 272.txt` is not a transition.
  A ledger entry that describes the command it declined to run is not the
  command either — the first version of this check searched the event stream
  for the text, and the subset run's own "do not run gh pr ready" line would
  have been read as its transition.
- The packet was recorded **before** the transition it informs. The packet is
  a message of its own, and its position in the agent's event stream is
  compared with the `gh pr ready` call's. A run that printed the packet only
  after marking the PR ready is describing the handoff retrospectively, so the
  receiver cannot have applied it. The probe's negative control is a run that
  opens both skills, prints a valid packet and takes the right decision, and is
  nevertheless refused because the packet came after the transition.
- It printed a `HANDOFF PACKET` block whose fields are the ones the
  candidate's own skill states, in that order. The labels are read from the
  staged `sdlc-implementation`, so a packet that dropped or reordered a line is
  refused; Markdown decoration on the title or the lines is tolerated.
- The completeness line still says the assessment is required against the
  whole approved plan. That line is what the subset case turns on: if the
  packet stopped stating it, the subset run would hold for a reason its own
  handoff no longer gave.

Every condition is mutation-checked: a test withdraws the behaviour the probe
relies on, and the probe has to fail for the named reason.

That last condition is why the packet is checked for content and not merely for
presence. It is also why the two cases reuse recorded evidence rather than
inventing new evidence:
`test_a_crossing_scenario_reuses_a_recorded_readiness_decision` asserts that
each crossing `facts.json` is its sibling's facts plus the start skill.

Both runs were made on 2026-11-11 against this branch's skills. The permitting
one marked the PR ready after reading the plan at `cccc3333` and reconciling
`rev-7`; the holding one left it in draft and said so in terms of the subject
alone. Neither posted a comment, so neither has a `submitted/` entry. Both
outcomes quote the deciding reply and the local `cs` result, and both quote the
`cs` stand-in's own disclosure that it is simulated — the rehearsal's local
CodeScene half is a stand-in, and neither outcome presents it as a real
analysis.

Each run also commits `traces/<name>-transcript.jsonl`: every assistant
message's text and tool calls, together with each call's success or failure,
and nothing else. The full event stream is several hundred kilobytes per run
and carries nothing else about the handoff, while the ordering evidence — which
message held the packet, which call read each manifest and whether it
succeeded, and which command ran the transition — is in the transcript alone.
The result *contents* are dropped, because the probe reads the outcome and
committing a skill's text would add bulk rather than evidence. Both facts
matter: the permitting run contains a `cat pr-babysitting/SKILL.md` that failed
before the same file was successfully opened, and a recording that kept only
the calls could not tell the two apart.
`test_the_committed_crossing_recordings_retain_the_handoff_evidence` runs the
probe over those committed files, so the evidence a reviewer reads is checked
by the same code the run itself ran.

### The two-assessment cases

The seven `combined-*` scenarios are the cases where an ExecPlan implementation
also introduces a proof, so both the completeness and the proof assessment are
applicable and both must clear. A verdict on one of them says nothing about the
other, and the pair of requests means a run cannot infer the revision binding
from a single reply's echo: `combined-plan-and-proof` is the only permitting
run in which two assessments have to clear, so a run that accepted one and
treated the other as covered would transition on evidence it never read.

`combined-plan-and-proof` is the permitting case: two clear replies, each
echoing `rev-7` for the same base/head, which matches the plan file read at the
head being judged. The PR changes the plan file and a Lean proof, and the run
reads both `contents` routes before deciding.

That run records an explicit limit on what it establishes. It had no Lean
toolchain, so it did not build the proof, and it reports that it could not
inspect the lemma `sound_of_refine` the proof applies or confirm that the
theorem's starting condition can hold. It cleared on the proof assessment's
verdict and the passing repository gates, not on a verifier run. The recording
is therefore evidence that the readiness rule accepts an assessment reply of
the right shape; it is not evidence that the reply's verdict is mathematically
sound, and the outcome states the gap rather than leaving it implicit.

The other six hold for one distinct reason each, so that a hold in one cannot
be explained by the defect in another. Three of them break the proof assessment
while the completeness assessment is clear, current, and bound to this
candidate; the remaining three break the evidence a verdict is reconciled
against:

- `combined-proof-pending` leaves the proof assessment unfinished. The
  completeness reply is clear for the whole plan at `rev-7` and for this
  candidate, so nothing on that side can hold the run. The proof reply records
  `Verdict: pending` and says why: the lemma the proof applies is not among the
  declarations in the file, and the answer is still being decided. A pending
  verdict is neither clear nor a finding, and cannot clear. The run polls, gets
  no further reply, and stays draft without posting anything — there is nothing
  yet to answer.
- `combined-proof-stale-verdict` gives the proof a clear verdict for a head
  that is not this candidate. The completeness reply is clear and current, and
  the proof reply is clear and echoes `rev-7`, but its assessed head is
  `aaaa1111` where the PR's head is `9999dddd`. The run treats the verdict as
  inapplicable, posts a follow-up pinned to the real head, and stays draft.
  This is the first of the three that isolate the proof assessment: the older
  `combined-proof-stale-revision` has both verdicts stale, so its hold does not
  show which assessment held it.
- `combined-proof-stale-plan-revision` leaves the proof verdict recorded
  against a superseded revision and nothing else. The plan file at head
  `7777dddd` reads `rev-8`, and the completeness reply is clear, bound to this
  candidate and echoes `rev-8`, so that side cannot hold the run. The proof
  reply is clear, its assessed head is this candidate's, and it echoes
  `rev-7` — the revision in force when it was asked. It was not wrong when
  written; it is stale now. The run holds, and rather than post a premature
  clearance it files a renewal request for `rev-8` that names the superseded
  verdict's comment ID. This is the case neither of the other two isolates: a
  proof verdict whose only defect is the plan revision it was recorded against,
  with completeness clear and current.
- `combined-proof-stale-revision` moves the approval under the replies. Both
  replies are clear and echo `rev-7`, and both are for the right base/head — but
  `rev-8` has since been approved, and the plan file at this unchanged head is
  the file that states it. The run reconciles the echoes against the file and
  renews both requests for `rev-8`; no reply follows, and the PR stays draft.
  This is the case the earlier recordings could not reach, where base/head is
  unchanged and only the revision in force has moved on.

  Because the head does not move, the file at it does not either: both earlier
  requests quote the blob the file has at this head, which is the `rev-8` blob,
  while naming `rev-7` as the revision approved when they were asked. The
  template asks for the file's blob at the published head, not for the approved
  revision's blob, so that pairing is what an approval transition at a fixed
  head looks like. Quoting the `rev-7` blob at this head — as the fixture did
  before — described a file this head never served, which is a contradiction in
  the premise rather than the stale approval the case rehearses. The same
  pairing holds in `combined-proof-stale-plan-revision`, whose earlier proof
  request preceded the `rev-8` request in the same thread.
- `combined-proof-unbound-revision` leaves the proof reply without a revision
  line at all. The completeness reply is clear and names `rev-7`, the proof
  reply is clear and names only the Assessment-ID, base/head and subject. A
  reply that does not echo the revision cannot be bound to it, so the run posts
  a follow-up asking for the revision to be restated and stays in draft. The
  bound reply in the same thread is what makes this a test of the binding: a
  run that inferred the proof revision from the completeness reply would take
  the pair as clear.
- `combined-proof-candidate-mismatch` changes the head the proof reply
  assessed. The reply echoes `rev-7` and is otherwise substantive, but its
  assessed head is `7777bbbb` where the PR's head is `6666aaaa`; asking the
  service for that commit returns 404. A verdict recorded against another
  revision does not carry over, so the run asks again against the real head and
  stays in draft.

Only the four whose hold is a fact about the plan file are held to a plan read
by the runner. The pending and stale-verdict cases are decided by the state of
the proof verdict alone — a pending verdict cannot clear at any revision, and a
clear verdict for another head needs no plan read to disqualify — so requiring
that read would demand evidence their decisions do not rest on.

## Layout

- `scenarios/<name>/facts.json` — the recorded GitHub surface for that run.
- `traces/<name>.jsonl` — every `gh` argv the agent issued, one JSON array per
  line, in order, written before the stand-in answered.
- `outcomes/<name>.txt` — the agent's final message for that run, verbatim.
  These are `.txt`, not `.md`, so the repository's Markdown gates cannot reflow
  a verbatim recording.
- `submitted/<name>.txt` — the comment body that run posted, verbatim. A trace
  shows that a POST happened; this shows what it asked for. Like the outcomes
  it is `.txt`, so the Markdown gates cannot reflow a verbatim recording, and
  it is committed only from a run whose authorization proof passed.
- `cs-shim.py` — the **simulated** `cs`. It answers `delta` and `check` from
  the scenario's recorded `cs_mode` (`clean`, `finding` or `unavailable`),
  reproduces the real CLI's exit status for each — including the non-zero exit
  when the licence check fails — and discloses itself on every answer. An
  unrecognized mode answers `unavailable`, so a broken fixture cannot
  manufacture the clean result the rehearsal is checking for. A `finding` mode
  must also record `cs_finding`: the stand-in carries no built-in text and
  refuses rather than invent one, since a default would name a path and line
  count this scenario may not serve.
- **Fixture faults are not local results.** Facts that were never served —
  missing, unreadable, not JSON, or not an object — exit `3` with a
  `fixture fault` diagnostic on standard error, and nothing is written to
  `cs-trace.jsonl`. They are deliberately *not* answered as `unavailable`,
  because that answer states a fact about the real binary (present, licence
  check failed) that a missing `facts.json` cannot establish. A served file
  whose `cs_mode` is unknown stays `unavailable`: the facts exist and record
  something this scenario cannot evaluate, which is the situation the licence
  failure describes.
- `cs-trace.jsonl` (per run, in the run directory) — every simulated `cs`
  invocation with the mode it answered from. A run that never invoked it cannot
  have cleared the local half, whatever its outcome says. The stand-in appends a
  `{"event": "pr-ready", "head": …}` line to this same file at the moment the
  transition happens, so one ordered timeline holds both the local check and
  the decision it informed; two files written by two processes could only show
  that both occurred, not which came first.
- `traces/<name>-cs.jsonl` — the committed copy of that run's simulated `cs`
  trace. It sits beside the `gh` trace because the two together are the
  recording: one shows what the agent was told about the PR, the other whether
  it consulted the local result before deciding. A run that transitions without
  a non-empty trace of this kind, or without the boundary line the runner
  requires before the decision, did not clear the local half of the gate.
- `gh-answers.jsonl` (per run, in the run directory) — every `gh` invocation
  with the exit status it was answered with and the text it printed. The argv
  trace records that a read was attempted; this records that it succeeded and
  what the agent received, which is what separates a read the agent could act
  on from one that failed or returned nothing usable. The text is captured from
  the stand-in's own standard output, so it includes whatever a `--jq` filter
  made of the payload. The runner requires an `isDraft` read after the last
  `pr ready` that both succeeded and reads as a non-draft, and a
  candidate-bound plan read before it that both succeeded and returned text.
- `gh-shim.py` — the executable stand-in. It derives the run directory from its
  own `__file__`, records each argv, and answers from `facts.json`. `pr ready`
  records `isDraft: false` in `state.json`, merging rather than replacing, so a
  later `pr view` can show the transition and a posted comment recorded earlier
  survives it. A POST to the issue-comment route is accepted only with the
  fixture token: without it the stand-in answers `401 Bad credentials`, because
  accepting the request would record a success the real service would refuse.
  `pr ready` also appends the transition marker to `cs-trace.jsonl`, because
  the two traces are written by different processes and only a shared file can
  order the local check against the decision. An accepted POST returns the
  fixture comment's URL, records the submitted body — in both the `-f body=…`
  and `--input -` forms — and serves it back on its own route, so a read-back
  and the discussion listing both see what was posted rather than a
  placeholder. Each accepted post is appended under an id of its own, because a
  run that renews two assessments posts twice and a stand-in holding one
  comment made the second look like it had replaced the first. Every post is
  also stamped with `created_at` and `updated_at`, one value taken from the
  latest the facts record plus a minute: the real service stamps every comment,
  and a run that polls for a fresh reply filters the discussion by time. A
  comment with no stamp reads back as `created_at: null`, which two recordings
  reported as the service failing to record when an accepted comment was made.
  The value is derived, not the instant of the POST, which a stand-in with no
  clock cannot know; what it reproduces is the property a poll needs, and
  because each earlier post is folded back into the facts, a second post in the
  same run is stamped later than the first rather than sharing its stamp. A
  single-comment route serves any comment the recorded listing carries, so a
  read-back finds a comment the run itself did not post. The `contents` route
  serves the plan file with its blob SHA, which is what lets a follow-up name
  the plan revision instead of stopping for a value the fixture never supplied.
  The `pulls/N`, `pulls/N/files`, `pulls/N/commits`, `pr list`, `pr diff` and
  `graphql` review-thread routes answer the reads a readiness run makes when it
  checks whether the delivered work matches the plan; without them a run
  reported those reads as 404 and could not see the diff at all. The `graphql`
  route takes POST only, and only for a document whose own text is a query: a
  mutation, a subscription, any other verb, or a read with no document is
  refused as unsupported rather than answered from the recorded reads. A stray
  `query` in another field does not make a mutation a query, and two documents
  are both read, so a mutation sent after a query is still refused. The check's
  own `annotations` route serves the entries its `annotations_count`
  advertises, and the `contents` route serves the file a finding names, so a
  run investigating an advisory reads the code rather than being told it is
  missing. `gh repo clone` is refused as unreachable —
  `Could not resolve host: github.com` — because that is what the dropped
  network really does; reporting it as an unsupported command would misdescribe
  the environment. The `check-runs` route carries the hosted check output,
  including CodeScene's own "no advisory findings" summary, which is one of the
  two CodeScene sources the skill reads; the recordings show only that half,
  for the reason under
  [what these recordings do not show](#what-these-recordings-do-not-show).
  `pr view --json statusCheckRollup` carries the same `output`, from the same
  helper, so a run that reads the rollup instead of the check-runs listing sees
  the same finding. The PR object itself carries the author, head repository,
  base and head refs and file list, because the skill's candidate-trust check
  reads them before it trusts any candidate-defined command, and a fixture
  without them made every run report that it could not decide. A `contents`
  route serves the proof the `proof-only-*` and `combined-*` scenarios
  introduce, so a run assessing it reads the subject rather than a 404.
- `make_scenarios.py` — regenerates every `facts.json`.
- `flagged_gate_stub.txt` — the file the advisory scenario serves and the local
  finding is measured against. It is data, so it stays out of the generator: a
  reader edits the text it is about, and the size the finding reports is
  computed from it.
- `sandboxed_run.sh` — the runner, including the isolation described below.

## Reproducing a run

`sandboxed_run.sh` takes a scenario name and needs `SKILL_SRC` set to the
`skills` directory of the candidate under test. It copies
`$SKILL_SRC/pr-babysitting` — and, for a scenario that sets `start_skill`, the
sender too — into a scratch working directory and runs a headless agent there,
so the prompt's `pr-babysitting/SKILL.md` resolves. Every completeness request
in `scenarios/` names the head it was posted for, and no scenario carries a
review decision the assessment is meant to be judged on.

```bash
SKILL_SRC=/path/to/checkout/skills \
  bash tests/fixtures/readiness-agent-boundary/sandboxed_run.sh current-whole-plan
SKILL_SRC=/path/to/checkout/skills \
  bash tests/fixtures/readiness-agent-boundary/sandboxed_run.sh crossing-whole-plan
```

The runner is not part of any Makefile gate: it needs a model API credential
and a `claude` CLI, which CI does not provide. It is a rehearsal tool, not a
deterministic check. It finds `claude` on the caller's PATH, or takes
`CLAUDE_BIN` naming the directory that holds it. The binary is then copied into
the run directory, because the host home it is normally installed under is
masked; the sandbox PATH holds the stand-in, that copy, `/usr/bin` and `/bin`,
so the agent inherits nothing else from the operator. It also needs `pasta`,
`nft` and `unshare`, and refuses to run without them, because the egress
allowlist is the boundary that stops a second HTTP client.

## Isolation

An earlier unmasked run proved that clearing ambient credentials alone is not a
boundary: the agent used the real client and posted a synthetic comment to the
live PR. Every recording here comes from a masked run in three layers.

**Network.** `pasta` gives the run a private network namespace and forwards the
host interface into it. The first thing the run does there is install an
`nftables` output policy of `drop`, admitting loopback, DNS to this host's own
resolvers, one TCP port to the model API host, and established flows. The
resolvers are read from `/etc/resolv.conf` on the host, and the model address
from `ANTHROPIC_BASE_URL`, both before the namespace drops the network; the run
aborts if either is empty. DNS is narrowed to those resolvers because admitting
port 53 generally would leave an arbitrary destination reachable.

After installing the rules, the run proves the boundary in both directions
before the agent starts, because a blocked-only check can pass on a broken
network and an allowed-only check can pass with no filter at all:

- at least one model API address must accept a connection on port 443;
- `1.1.1.1:443` and `140.82.121.4:443` must both fail, addressed literally so a
  DNS failure cannot be mistaken for a block.

The run aborts on either failure. This is the load-bearing boundary, because
the agent runs with Bash and a filesystem mask alone cannot stop a second HTTP
client. Verified against the live network: inside the sandbox `github.com`,
`api.github.com` and port 22 are all unreachable, while the model API and DNS
work.

**Mounts.** Inside the network namespace, `unshare -m` adds a private mount
namespace, made private with `mount --make-rprivate /` first:

- The stand-in is replace-bound over `/usr/bin/gh` and `/bin/gh`, so no
  absolute path reaches the real client.
- `comenq` lives under the operator's home, so the home mask below makes it
  unreachable; no separate stub is needed.
- The whole host home is replace-bound with an empty directory, not a list of
  named credential files inside it. Masking only `~/.config/gh`,
  `~/.claude/.credentials.json` and the token pool left every other file under
  the operator's home readable by absolute path, and a credential can live at a
  path the runner never thought to name. The agent has no legitimate reason to
  read any of it, so the whole directory goes. The `claude` binary is copied
  out of the host home into the run directory before the mask is applied, since
  the CLI itself is installed under `~/.bun` on this host.
- The comment-token pool is present but not real. The runner writes a fixture
  pool holding one token, `fixture-pool-token`, into the isolated home the run
  is given as `HOME`, at `~/.local/share/github-tokens` there. The stand-in
  alone honours that token, which authenticates as `fixture-commenter`; real
  GitHub would reject it, so nothing is lost if it escapes. This keeps the
  manual-comment route exercisable inside the sandbox while the host's real
  pool is unreachable behind the home mask.
- Masking fails closed. A missing target, a shape mismatch, a failed bind, or a
  mask that does not read back aborts the run before the agent starts.
- The masks are re-proved after they are applied: the host home must list no
  entries at all, `hosts.yml`, the token pool and the credential file must all
  be absent beneath it, the isolated home's token pool must hold exactly one
  line reading `fixture-pool-token`, and the staged CLI must be executable. A
  directory mask removes the paths beneath it, so any entry left under the host
  home means the mask did not take.

**Process.** The environment is replaced rather than filtered: `env -i` passes
only `PATH`, `HOME`, an empty `GH_TOKEN`, `GITHUB_TOKEN` and `GH_CONFIG_DIR`,
the two model API variables, `GIT_TERMINAL_PROMPT`, `TMPDIR` and `TERM`. No
ambient token, config override or path reaches the agent. `HOME` is the run's
own directory, not the operator's, and the operator's home is masked outright,
so the host home is reachable by neither a relative nor an absolute path. A
`.claude` directory is created there so the CLI has somewhere to write, and the
run aborts if the isolated home resolves to the host home or has no such
directory. It runs `--bare`, so operator instructions, hooks, MCP servers and
memory are absent, with `--permission-mode dontAsk` and
`--allowedTools Bash,Read,Glob,Grep`. The runner propagates the agent's own
exit status, so a run killed by its budget or by a timeout is a failure rather
than a clean rehearsal.

These layers are proved, not assumed. A diagnostic stand-in for the CLI once
recorded the agent's view from inside the sandbox: the credential file, token
pool and `hosts.yml` were empty or absent, `GH_TOKEN` and `GITHUB_TOKEN` were
unset, `/usr/bin/gh` and `/bin/gh` both held the stand-in, and `github.com`,
`api.github.com`, `140.82.121.4:22` and `1.1.1.1:443` were all blocked while
the model API was reachable. Under the whole-home mask those surfaces are
absent rather than empty, and the runner's read-backs establish that before the
agent starts on every run rather than in one diagnostic: listing the host home
must yield nothing at all. An earlier revision of this runner defined its
masking helper without calling it, so those surfaces were reachable; the proof
checks above exist so that the same omission fails the run instead of silently
weakening it.

The runner also asserts the outcome each scenario exists to pin, because a
trace shows what the agent read and only the decision shows what it concluded.
A scenario expected to transition must issue `gh pr ready` and read the draft
state back; a scenario expected to stay in draft must issue none. A scenario
that decides otherwise fails the run instead of being filed as a recording, so
these files cannot drift from the rule they are meant to demonstrate.

The gate assertions are specific rather than aggregate:

- The read-back is **ordered**. An initial `pr view` also carries `isDraft`, so
  a bare text search in the trace would pass even with the post-transition read
  removed. Only reads after the last `pr ready` count.
- The read-back is **successful and true**, not merely attempted. `state.json`
  is the value the stand-in served, so the runner fails a transition whose
  served state still reads `isDraft: true`, and `gh-answers.jsonl` makes a
  failed read-back distinguishable from one the agent could act on.
- The **value the agent actually read** must state the ready state. An exit
  status is not a value: `pr view --json isDraft --jq 'null'` exits zero and
  prints `null`. The stand-in records the text each invocation printed,
  including whatever a `--jq` filter made of it, and the runner accepts only an
  answer that reads as not-a-draft — the JSON object, a filtered `false`, a JSON
  `"false"`, or a `false <ref>` template. `null`, `true`, an empty body, a
  prose string and a failed call are each refused.
- A permitting run must have invoked the simulated `cs` at all. Marking ready
  without consulting the local result is the waiver the rule forbids, and an
  outcome that merely mentions the tool was missing is not evidence that it was
  consulted.
- The local check must be **candidate-bound and take place before the
  decision**. The runner requires a `cs delta` naming both the recorded base
  and head, in the shared trace, before the `pr-ready` boundary line. A bare
  `cs delta` reads a working tree this sandbox does not have, and a delta run
  after the transition would clear a candidate that had already been judged.
- `current-whole-plan` must read the plan file **before** the transition, at
  the candidate head. An earlier version selected the read with
  `grep '...ref='` and then re-tested that same line for `ref=`, which can
  never fail; it now resolves the `ref=` value and requires it to name the head
  commit or the PR's head branch. `?ref=main` serves the base branch's copy, so
  reading it says nothing about the revision in force. The read must also have
  succeeded and returned text: a 404, or an empty 200, is not a revision the
  decision could have reconciled. One read has to satisfy every condition —
  candidate-bound, before the transition, successful and non-empty — because
  two reads can satisfy them separately while the revision actually used was
  the base branch's copy.
- A scenario whose recorded local result is `finding` or `unavailable` may not
  be written as one that permits a transition; the two facts contradict each
  other, and the runner refuses the contradiction rather than recording it.
- The question a permitting run clears must be the one the skill posts. The
  seeded request is a premise, so a fixture could seed a shorthand the skill
  never sends and the run would then clear a question nobody asked. The request
  probe requires the completeness fields the template names — revision, the
  plan file's blob SHA at that head, acceptance evidence and filled limitations
  — and, for a proof request, its inventory, correspondence, assumptions,
  verifier evidence and non-vacuity fields, plus the blob beside any revision
  it names. The proof fields state the limits the fixture actually has — it
  records no Lean build log — rather than claiming evidence that was never
  served.
- The combined permitting run judges two subjects. It must read the proof as
  well as the plan at the head it judges, or its clear proof verdict would rest
  on the request's own inventory rather than on the file.

The stand-in's own authorization is proved the same way. Before the agent
starts, the runner posts a comment against a copy of the stand-in: with no
token, which must fail; with the fixture token, which must succeed; and then
with a wrong token, after which the accepted comment must still be the one the
fixture token recorded. The third call is what makes the refusal about the
credential rather than the starting state: the first refusal ran against an
empty record, so a stand-in that wrote the comment before checking the token
passed both and would have overwritten an accepted comment in the real run. An
earlier revision stamped the pool's login on every POST regardless of what the
token was, so a recording could show a follow-up that the real service would
have refused. After the run, the runner also prints the body that was posted
and fails if its author is not the pool account, so the trace's evidence is the
request itself and not only the fact that one was made.

The limits are deliberate. The model API stays reachable, because the agent
needs it. The host home is masked, so the operator's files — including this
repository's working tree, which lives beneath it — are out of reach; the run
gets a copy of the skill in its own working directory instead. The rest of the
system stays readable, because removing it would also remove the runtime the
agent needs. And the boundary is stronger against reaching GitHub than against
a locally privileged process: the harness assumes a cooperative agent, not an
adversarial one.

## What these recordings do not show

Each recording is evidence for what its trace and outcome contain, and no more.
Two limits apply to every run here.

**Revision confirmation.** `current-whole-plan` marks the PR ready only after
reading the plan file at the head it is judging, and the trace shows that read:
`contents/docs/execplans/issue-271-readiness-handoff.md?ref=cccc3333` returns a
file whose body says `Plan revision: rev-7`, which is the revision the verdict
echoes. The recording therefore shows the echo reconciled against the revision
in force, not accepted on its own. Its content is served as plain text rather
than in the API's base64 envelope, so a run that decoded `content` itself would
see a different shape; the fixture chooses the readable one so a reviewed file
carries the plan text. `proof-only-cleared` needs no revision read: its request
states that no ExecPlan applies, so there is no revision to confirm and the
proof verdict is the only applicable assessment. `superseded-revision` reads
`contents/docs/execplans` while naming the stale revision in a follow-up, which
is a different use of the route from the confirmation above.

The four holding `combined-*` cases whose ground is the plan file each
reconcile the same way, and their traces show it:
`combined-proof-stale-plan-revision`, `combined-proof-stale-revision`,
`combined-proof-unbound-revision` and `combined-proof-candidate-mismatch` all
read `contents/docs/execplans/issue-271-readiness-handoff.md` at their own head
before deciding, so none of them holds merely because it never looked. What
differs is what the read established. In both stale cases the file reads
`rev-8` against a reply that echoes `rev-7` — both replies in the older case,
the proof reply alone in the newer one; in the unbound case the completeness
reply names `rev-7` and the proof reply names nothing, so the revision check
cannot be satisfied for the proof from its own reply; in the mismatch case the
revision matches and the head does not. The permits case reads both `contents`
routes, the plan and the proof, at the head it judges, because a combined
assignment has two subjects to reconcile and one read would not cover both.
That second read is asserted rather than described: earlier recordings read the
plan alone while this paragraph claimed both, because nothing checked it. The
assertion is the same one the plan read gets, applied to the proof — a read of
the assessed file's `contents` route at the candidate head, ordered before the
transition, whose answer record shows status `0` and carries the theorem the
file states. A run that merely mentions the route, reads another ref, reads
another proof, reads nothing back, reads only the file's metadata — a
`--jq .sha` answer prints a hash and no theorem — or reads after it has already
transitioned is refused. The proof text is read from the scenario's own proof
route, so the assertion names the theorem this premise serves rather than any
text at all. The proof request states the template's inventory, correspondence,
assumptions, verifier evidence and non-vacuity fields, and the run reads the
proof to answer the question it was asked.

Both reads are also bound to the approved path. The plan route serves
`contents/docs/execplans/issue-271-readiness-handoff.md` exactly rather than
any file below `execplans/`, and the plan read names that path; a read of a
sibling ExecPlan is refused even when its answer would otherwise be usable, and
an answer whose own `path` names another file is refused too. The scenario's
`plan_path` is the value both the route and the assertion are built from, so a
premise that renames the plan moves the check with it rather than leaving an
unexamined prefix behind.

**CodeScene, local half.** The local result is a **simulated** `cs`
(`cs-shim.py`), not CodeScene. The real binary performs a licence check against
`api.codescene.io` on every invocation, and this sandbox drops all egress
except the model API, so genuine local analysis cannot run inside it. The
stand-in prints
`cs-stand-in: simulated output for rehearsal; not a CodeScene analysis` on
every answer, and records each call and the mode it answered from to
`cs-mode`-carrying `cs-trace.jsonl`. No recording here is evidence that a real
`cs delta` was executed, and none should be quoted as a CodeScene result.

What the stand-in *does* establish is what the agent does with each possible
local result, which is the part the skill's rule is about:

| Scenario                      | Local `cs delta` | Hosted CodeScene | `gh pr ready` |
| ----------------------------- | ---------------- | ---------------- | ------------- |
| `current-whole-plan`          | clean            | no findings      | yes           |
| `local-codescene-finding`     | one new issue    | no findings      | no            |
| `local-codescene-unavailable` | cannot evaluate  | no findings      | no            |
| `codescene-advisory`          | one new issue    | **one finding**  | no            |

The two `local-codescene-*` cases hold every hosted source constant and clean,
so each run's decision can only come from the local result.
`local-codescene-finding` is the case where the hosted badge says nothing is
wrong and the delta disagrees; `local-codescene-unavailable` is the case the
rule names directly — "I could not run the check" is not "the check found
nothing" — and the run must treat an unevaluable source as unverified rather
than clean. `codescene-advisory` is the opposite direction: every hosted check
concludes `SUCCESS`, yet the CodeScene check's own output lists a finding
against a file the PR touches, so the run must read the output rather than the
badge. Its local delta reports the same finding, because the two sources
describe one candidate and disagreeing them would test a contradiction the
scenario is not about.

The real local half is recorded outside this harness: a `cs delta` against the
candidate in a real worktree, reported in the PR's validation evidence. A live
run is the only place the genuine result exists, and a stand-in that fabricated
one would be recording an answer no service produced.

**A run that posts cannot then be answered, unless the scenario scripts it.**
The stand-in accepts a POST and serves it back on its own route and in the
comment listing. On its own it never replies to a comment the run itself
posted: its only assessment-bot comments are the ones the facts record, and
they answer the Assessment-IDs those facts name. A permitting run therefore
cannot both post and receive a clear reply, which is why most permitting
recordings have no `submitted/` entry from a post made in that run.

`posted-then-answered` is the one case that does. Its facts carry a
`scripted_replies` map keyed by question kind (`completeness` or `proof`). When
the run posts a tagged request naming an Assessment-ID, the stand-in answers by
that kind, echoes the marker the run minted, stamps the answer after its
request, adds it to the discussion, and serves it on its own comment route. The
answer's text opens with
`gh-stand-in: scripted reply for rehearsal; not a CodeRabbit answer`
(`SCRIPTED_PREFIX`), so the recording says in its own words what answered it
and no reader has to consult this file. The runner refuses a scripted reply
lacking that line, and refuses a scripted scenario whose run posted nothing or
was served nothing.

The scenario seeds no question of its own. Seeding one would answer a request
the run never made and make the case a duplicate of the recorded ones, so
`PROBE_REQUESTS` exempts a scenario only when its facts carry a script and no
question; the exemption is tied to the script rather than to the scenario name,
so it cannot be borrowed to excuse an ordinary case that forgot its premise.

Six further recordings post a comment, and `submitted/` is the complete list of
them: `combined-proof-candidate-mismatch`, `combined-proof-stale-plan-revision`,
`combined-proof-stale-revision`, `combined-proof-stale-verdict`,
`combined-proof-unbound-revision` and `superseded-revision`. Each renews or
challenges an assessment whose verdict does not bind, and each has a
`submitted/` body for the request it posted; the hold that follows is the
correct answer to an unanswered request, not a defect. None of the six shows
the agent clearing a gate on a reply to a post the run made — in those
permitting recordings the reply was already in the discussion when the run
started.

The deterministic suites cover the same sequencing against doubles, for the
shapes a single run does not exercise:
`test_a_reply_arriving_between_invocations_still_clears_the_question` runs the
sequence, takes its posted questions, appends replies echoing those markers,
and shows the second invocation transitioning without re-posting.

**What the scripted reply is not.** It is not a CodeRabbit verdict, and its
recording is not evidence that the service would answer a posted question
favourably, or at all. What `posted-then-answered` establishes is narrower and
is what the finding against this harness asked for: that the agent, when it
posts the question itself, finds the answer in the discussion it polls,
correlates it by the marker it minted, and clears the gate on that correlation
rather than on the act of posting.

**The stand-in does not apply `since`.** The recorded poll carries
`-f since=<the second before the request>`, and the stand-in answers it with
the whole thread rather than filtering to the comments updated after that
instant. A real service would return only the request and the answer, so the
recording shows the agent selecting the answer from a superset that also holds
the seeded premise comment. What the recording does establish is the part that
matters to the correlation: the answer's stamp sorts strictly after its
request's, so a real filter would include it. `posted_at(facts, after)` sets
that ordering deliberately, and
`test_a_scripted_answer_is_stamped_after_its_own_request` fails if a later
change stops it. Emulating the filter would make the recording more faithful
and is not claimed here.

**Freshness of each recording.** All seventeen recordings made before the
crossing cases passed their own outcome assertion when they were made. They
were replaced when the runner gained the shared `pr-ready` boundary line, the
successful read-back check, the candidate-bound plan read and the head-commit
route, and when the assignment began naming the stand-in as the local source;
both changes reached every scenario, so all nine originals were redone together.

The stand-in's handling of a posted comment changed next, and the recordings
that post were redone under it: the combined cases as they then stood and
`superseded-revision`. Before that change a posted comment read back with
`created_at: null` and a second post overwrote the first, and two outcomes
reported those as defects in the service. A stand-in that mismodelled the
record it exists to serve cannot be the evidence for how an agent reads that
record. The recordings that post nothing are unaffected, because the change is
confined to the comment the stand-in records and serves back; they were not
re-recorded, and their provenance is the earlier refresh above.

`combined-proof-pending` and `combined-proof-stale-verdict` were recorded next,
after the others. `combined-proof-stale-plan-revision` followed them, and it
was the only one made under every assertion current at that time: the premise
check, the plan-read check, the comment stamp and the answer record. The three
post differently, which is why each has a different artefact set: the pending
run posts nothing, the stale-verdict and stale-plan-revision runs both post and
so have `submitted/` entries. The answer records under `answers/` exist only
for runs whose scratch directory still held one when the record was committed;
a run whose scratch is gone has none, and none was reconstructed.

Both crossing runs were recorded last of all, and are the only recordings made
under the packet-ordering rule: the two earlier crossing runs printed their
packet in the final message, after the transition, and the rule now refuses
that shape. The first of the current pair was made after the runner began
requiring the packet before the decision, and its outcome says so — "I produced
the handoff packet above, then marked the PR ready". The holding one ends with
its packet, because a blocked handoff has no decision after it to record.

A recording made before an assertion was added is still valid evidence for what
it observed, but it has not been re-run against the assertion. The plan-read
check now extends to the three holding `combined-*` cases whose hold is a fact
about the plan file; the stale-plan-revision case was recorded under it, and
the rest were verified against their committed facts rather than assumed, which
is what `test_each_holding_combined_premise_holds_for_its_recorded_facts` does
for every one of the six.

`combined-proof-stale-revision` and `combined-proof-stale-plan-revision` were
recorded again once their premises were corrected to cite the blob the head
serves. Their earlier recordings were made against requests that quoted the
`rev-7` blob beside a head that served the `rev-8` file, which is the
contradiction described above; the clarifying remarks those runs made about the
mismatch were evidence of the premise defect, not of the stale approval the
cases exist to rehearse. Both re-runs passed every assertion, and each posted
its renewed requests citing `e3b7c04d…`, so those `submitted/` bodies and the
outcomes beside them now show the skill's own requests rather than the seed's.

The plan-read arm stops at those three. `combined-proof-pending`,
`combined-proof-stale-verdict` and `combined-proof-candidate-mismatch` are
decided by the state of the proof verdict alone — unfinished, or clear for a
head that is not this candidate's — and neither ground is a fact about the plan
file. Holding the last two to a read they have no use for made the check depend
on how a run chose to investigate rather than on what its hold rests on, and it
aborted a run that held for exactly the right reason: the mismatch case was
re-run and passed once the arm was corrected, and all seven recordings that
were affected by the request change were redone from actual runs against the
corrected runner.

The assessment requests are probed too. `PROBE_REQUESTS` reads a scenario's
`facts.json` and the run's own `state.json`, and refuses a question the skill
would not post: a completeness request must state the plan revision, a 40-hex
blob SHA for the plan file at that head, `Acceptance evidence:` and a filled
`Known limitations:`, and must not claim no proof is affected where that is
contradicted — by a proof question in the same discussion, or by a diff that
changes the proof file; a proof request must state the template's five fields —
inventory and claims, production correspondence, assumptions and bounds,
verifier evidence, and non-vacuity and limitations — must name the blob beside
any revision it names, and one that names no revision must carry the template's
`<omitted; no ExecPlan applies>` form. The blob is also held to the file the
scenario's head actually serves: the template asks for the blob at that head,
not for the named revision's own, so a request citing a blob no route answers
is refused. The two coincide until an approval moves under a fixed head, which
is why only the stale cases can tell them apart. The request text is a
generated premise rather than a recording, which is why the fixtures were
corrected and the recordings redone rather than the old request being preserved.

Both kinds of request are checked: the seeded question, and the comments the
run itself posted, read from the `posted` list the `gh` stand-in persists in
the run's `state.json`. `posted-then-answered` is why. It seeds no question at
all, so before the probe read the run's own posts there was nothing to check
there, and the one request the whole case turns on went unexamined. Its
recorded body is now checked like any other, and
`test_each_recorded_request_passes_the_checks_the_runner_applies` holds every
`submitted/` body to the template.

The blob is read as a value, not as one sentence. The template asks for "the
plan file's blob SHA at this head" and does not fix the wording, and the
agent's own request says
`Plan revision: rev-7 (plan file blob 5a1c9e4d… at this head).` A first version
of the posted-body check matched `blob SHA at this head: <sha>` and so refused
that recorded request — a request the skill does post. The probe now reads the
40-hex SHA from the `Plan revision:` line, which is where the template puts it.

A scenario whose facts carry a `scripted_replies` map is exempt from the "seeds
a question" rule, because its question is meant to be posted by the run. The
exemption is not silence: with no run behind it the probe refuses, naming the
scenario, and the runner separately refuses a scripted run that posted nothing.

Every scenario is held to that, not only the four the runner expects to
transition. The runner applies the probe to a permitting run because a bad
question changes its verdict; a holding run is evidence as well, and the six
holding `combined-*` cases failed the same check. Each asks a proof question
about `proofs/refinement/Theorem.lean` while its sibling completeness request
said `Proof inventory: none affected`, so a run reading both faced two
statements it could not both believe and held on that contradiction rather than
on the stale, pending, unbound or mismatched verdict the case exists to
demonstrate. The proof request was also a shorthand: it named the proof file
and a revision, but none of the five fields the template requires, so the
verdict it asked for covered a subject whose correspondence and limits were
never put to it. Both are premise defects, fixed in `make_scenarios.py`; all
six runs were then redone against the corrected premise and every recording
replaced with what those runs produced.

A premise and the recording made from it can now drift apart silently, which is
what happened here: the generator was shared across scenarios, so completing
one request rewrote nine premises while only the run being re-recorded was
updated. `test_each_scenario_seeds_the_question_the_skill_posts` covers every
scenario that seeds one, which is all of them but `posted-then-answered`; that
one's request is covered instead by
`test_each_recorded_request_passes_the_checks_the_runner_applies`, which reads
the body its run posted. The installed recordings were compared against the
bodies their `facts.json` now serves before this was committed.

Earlier still, the stand-in's own "not a CodeScene analysis" disclosure was an
unmodelled third variable, and that is why all nine original scenarios, not
only the permitting ones, were redone together. Two runs of one scenario then
diverged — one accepted the clean result and transitioned, the other read the
disclosure as "the local source is unverified" and held — so the recordings
were evidence about how each agent read the banner rather than about the rule.
The assignment now names the stand-in as this environment's local source
without revealing what it answered. Earlier revisions of these files were not
so: the stand-in once ignored `--jq`, so a filtered call returned the
unfiltered payload, it once answered a field-bearing `gh api` call as a read,
so a POST recorded nothing, and the permitting recordings were made before any
local CodeScene result existed, so they transitioned while their outcomes said
`cs` was unavailable. That last state is what the rule now forbids, and those
recordings were replaced rather than reworded.

The facts were also incomplete in a way the runs themselves reported: the
recorded PR carried no author or head-repository fields, so a run following the
skill's candidate-trust check could not reach a decision and said so. That is a
gap in the fixture, not a fact about the candidate, and it meant no earlier
recording isolated the variable it was made to test. The PR object now carries
the fields `gh pr view --json` returns, and `statusCheckRollup` carries each
check's own `output` rather than the generator's internal `advisories` field,
so the two routes a run can read a check through cannot disagree. The two
`proof-only-*` scenarios also record a PR whose body says no ExecPlan applies
and whose diff is the proof it introduces; the earlier shared body claimed an
approved plan, which contradicted their premise and made the run ask for a
completeness assessment instead of deciding the proof one.

## Recorded artefacts contain no live mutations

The traces show reads, `pr ready` in the four permitting scenarios, and POSTs
in the runs that renew an assessment or post the one question a scripted case
answers, all against the stand-in. No trace contains a merge or a review
request. Nothing here was captured from a live PR, no real CodeScene command
was run, and no credential appears in any file: the only token any run could
reach is the fixture token, which real GitHub rejects. Every posted body names
the plan revision and the base/head it was posted for, and carries no
credential.

## Refreshing

Regenerate with `python3 -I make_scenarios.py` after editing a scenario, or
after editing `flagged_gate_stub.txt`, whose text the advisory scenario serves
verbatim. Then rerun the affected scenarios and copy the following files per
run, where the run produced them:

| Run directory             | Committed path           | Present when             |
| ------------------------- | ------------------------ | ------------------------ |
| `gh-trace.jsonl`          | `traces/<name>.jsonl`    | always                   |
| `gh-answers.jsonl`        | `answers/<name>.jsonl`   | always                   |
| `cs-trace.jsonl`          | `traces/<name>-cs.jsonl` | the run invoked `cs`     |
| the agent's final message | `outcomes/<name>.txt`    | always                   |
| `submitted.md`            | `submitted/<name>.txt`   | the run posted a comment |

The `cs` trace is committed because it is half the evidence, not a scratch log:
it shows whether the local result was consulted before the decision, and the
boundary line the stand-in writes into it is what makes that ordering
checkable. Copy it whenever the run produced one, and delete a stale
`traces/<name>-cs.jsonl` when the new run produced no `cs` trace at all: a
committed trace left behind by an earlier run would claim a consultation this
run never made.

The answer record is committed for the same reason. The argv trace says a read
was attempted; only the answer says whether it succeeded and what the agent
actually received, which is what separates a usable read from one that failed
or filtered to nothing. The runner asserts on it during the run, but a
committed trace without it leaves a reader unable to check that assertion. A
record is the stand-in's own `{argv, status, stdout}`, so it carries fixture
data only: the stand-in answers from `facts.json` and never from the live
service, and it holds no credential because the sandbox passes none. Commit it
only when it was produced by the same run as the trace beside it — a record
copied from a different run would not describe that trace's answers. Runs whose
scratch directory is gone have no record committed, and none is reconstructed.

**Not every committed record carries `stdout`.** Five do not:
`codescene-advisory`, `local-codescene-finding`, `local-codescene-unavailable`,
`proof-only-pending` and `subset-clear`. Their records hold `{argv, status}`
only, because they were captured before the stand-in recorded the text it
printed. They show that each invocation ran and how it exited; they cannot show
what the agent received, so they do not on their own evidence the "usable read"
claim above for those runs. Read them as a status record, not as an answer.

The pairing test bounds the shortfall rather than ignoring it. It asserts the
record count and each entry's argv — the part those five do still carry — and
it also compares every file against `ANSWERS_WITHOUT_STDOUT`: a new recording
that loses `stdout` fails, and a listed file that gains it fails until its name
leaves the list. So the five are a stated, frozen limit on the older evidence,
not an unnoticed one that new recordings can extend. Re-recording those five
would close the gap; they have not been re-recorded here.

A scenario that posted no comment has no `submitted/` entry. Replace a trace,
its answer record, its `cs` trace, its outcome and its submitted body together:
any one without the others, or the reverse, is not evidence of anything. Review
a new recording before replacing an old one, and keep the previous recording's
scope if it covered different evidence. A run is only a recording if it passed
every assertion above; a run that aborted is a failed rehearsal and replaces
nothing.
