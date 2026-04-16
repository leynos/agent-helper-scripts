# Editing checklist

The mandatory editing pass for technical design documents. Read this
before Phase 6 (Editing).

## Philosophy

The editing pass is adversarial. Its job is to find and remove
everything that does not earn its place. A sentence survives editing
only if removing it would lose information that matters to the reader.

This is not proofreading. Proofreading fixes typos and grammar. Editing
restructures, cuts, and tightens. Both happen in this phase, but the
emphasis is on the destructive work.

## Pass order

Execute these passes in sequence. Each pass has a specific target.
Running them in order prevents earlier passes from undermining later
ones.

### Pass 1 — Structural coherence

Read the document against the agreed outline.

- Does every section from the outline appear?
- Does every section fulfil its stated purpose?
- Are there sections that appeared during drafting but were not in the
  outline? If so, do they earn their place? If not, cut or merge them.
- Do sections flow in a logical dependency order?
- Are there redundancies — the same information stated in two places?
  Consolidate to one location and cross-reference.
- Does the document answer the problem statement? Trace each
  requirement to a section.

### Pass 2 — Sentence-level fluff elimination

Read every sentence. For each, ask: "Does removing this sentence lose
information that matters?" If not, remove it.

Specific targets:

**Throat-clearing.** Sentences that announce what is about to be said
rather than saying it.

- "It is worth noting that X." → "X."
- "In order to achieve Y, the system…" → "The system… to achieve Y."
- "This section describes the architecture." → (delete; the heading
  already says this)
- "As mentioned in the previous section…" → (delete or replace with a
  specific cross-reference)
- "Before we dive into the details…" → (delete)

**Hedge words.** Words that weaken claims without adding genuine
uncertainty.

- "perhaps", "arguably", "it seems", "it could be said", "it is
  believed that", "in some cases it may be possible"
- If the uncertainty is genuine, express it precisely: "The performance
  impact is not yet benchmarked" not "The performance impact may
  perhaps be significant."
- If the uncertainty is not genuine, delete the hedge and state the
  claim directly.

**Tautologies and filler.**

- "completely unique" → "unique"
- "very essential" → "essential"
- "basic fundamentals" → "fundamentals"
- "future plans" → "plans"
- "end result" → "result"
- "each individual" → "each"

**Weak transitions.** Words that connect sentences that are already
obviously connected.

- "Additionally" — if the connection is obvious, delete
- "Furthermore" — same
- "Moreover" — same
- "It should also be noted that" — always delete
- "In addition to the above" — always delete

If a genuine transition is needed, write one that conveys the
relationship: "This constraint also affects X" is better than
"Additionally, X."

**Passive voice.** Rewrite in active voice unless the agent is
genuinely unknown or irrelevant.

- "Tasks are dispatched by the orchestrator" → "The orchestrator
  dispatches tasks"
- "Errors are handled gracefully" → (who handles them? how?)
- "The configuration is loaded at startup" → "The service loads
  configuration at startup"

**Nominalisations.** Verbs disguised as nouns, adding bulk without
meaning.

- "performs validation of" → "validates"
- "provides support for" → "supports"
- "makes use of" → "uses"
- "carries out execution of" → "executes"
- "enables the facilitation of" → (delete the entire phrase and start
  over)

### Pass 3 — Vocabulary precision

Replace vague terms with precise ones.

| Vague | Ask | Precise example |
|---|---|---|
| "handles" | How? | "retries with exponential backoff" |
| "manages" | What operations? | "creates, updates, and deletes" |
| "processes" | What transformation? | "parses and validates" |
| "supports" | What mechanism? | "exposes a gRPC port for" |
| "ensures" | How is it enforced? | "rejects requests that lack" |
| "integrates with" | Through what interface? | "calls the X API via" |
| "leverages" | (Never use this word) | (Use the actual verb) |
| "utilizes" | (Use "uses") | "uses" |
| "robust" | Against what? | "tolerates N concurrent failures" |
| "scalable" | To what? | "handles 10k requests/s per node" |
| "seamless" | (Marketing word; delete) | Describe the actual UX |
| "powerful" | (Marketing word; delete) | Describe the capability |

### Pass 4 — Consistency

Check for inconsistencies across the entire document:

- **Terminology.** Is the same concept always called the same thing?
  Check against the glossary.
- **Capitalisation.** Is "merge base" always "merge base", never
  "Merge Base" or "merge-base" (unless in code)?
- **Hyphenation.** Pick one form and use it throughout: "re-apply" or
  "reapply", not both.
- **Number formatting.** Digits or words? Pick a convention. (Common:
  words for one to nine, digits for 10+.)
- **Code formatting.** Are all CLI commands, file paths, function
  names, and configuration keys in `code spans`?
- **Heading style.** Sentence case throughout (unless the user
  specifies otherwise).
- **List style.** Consistent punctuation. If list items are sentences,
  they end with full stops. If fragments, they do not.

### Pass 5 — Source verification

For every factual claim in the document:

- Is there a source? If not, can one be found? If not, cut the claim
  or flag it as unverified.
- Is the source still valid? Check URLs.
- Is the source appropriately cited? (Footnote, inline link, or
  references section.)

### Pass 6 — Locale enforcement

Unless the user has specified otherwise, enforce British English with
Oxford spelling:

- **-ize** not -ise: organize, recognize, customize
- **-yse** not -yze: analyse, paralyse, catalyse
- **-our**: colour, behaviour, neighbour
- **-re**: centre, fibre, calibre
- **-ll-**: cancelled, counsellor, modelling
- **-ogue**: analogue, catalogue, dialogue
- **Spaced en dash** ( – ) not unspaced em dash (—)
- **Oxford comma** in lists
- **Collective nouns** take the form appropriate to the context
- **Quotation marks**: single for scare quotes, double for direct
  quotation (or vice versa — pick one and stick to it)

US spelling is acceptable only in code identifiers, API surfaces, and
direct quotations from US-English sources.

### Pass 7 — Final read

Read the entire document once more, start to finish, as if encountering
it for the first time. This pass catches:

- Jarring transitions
- Sections that assume context the reader does not yet have
- Lingering fluff that survived earlier passes
- Tone inconsistencies

## The one-third rule

A useful heuristic: if the editing pass does not remove at least a
third of the draft's word count, either the drafting was unusually
disciplined or the editing was too gentle. Most first drafts contain
30–50% fluff. This is normal and expected.

Do not pad the draft to make the editing pass look more impressive. Do
not skip the editing pass because "it's already pretty tight." Run the
passes regardless.
