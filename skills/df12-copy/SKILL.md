---
name: df12-copy
description: >
  Voice and copy style enforcement for df12 Productions. Use this skill
  whenever writing, editing, or reviewing marketing copy, landing pages,
  product descriptions, white papers, migration guides, release
  announcements, blog posts, README openers, or any other public-facing
  prose for df12 Productions or its products (Netsuke, Weaver, rstest-bdd,
  Zamburak, Wildside, Concordat, and others). Also trigger when the user
  asks to write "in the df12 voice", mentions the Logisphere crew or
  mascot characters, or requests copy that follows the "serious tools,
  playful worlds" ethos. This skill applies to all df12 product copy and
  should be used even for short-form content like taglines, feature
  bullets, changelogs, and social media posts.
---

# df12 Productions copy skill

This skill enforces the df12 voice and copy style guide when writing or
editing public-facing prose for df12 Productions.

## Before writing anything

Read the full style guide at `references/voice-and-copy-style-guide.md`.
It contains the complete rules, do/don't examples, and the Logisphere
crew deployment guidance. What follows here is a compressed operational
checklist — the reference is authoritative when in doubt.

## The voice in five words

Compressed. Precise. Dry. Grounded. Playful.

## Locale: en-GB-oxendict

Every piece of df12 copy uses British English with Oxford spelling:

- **-ize** not -ise: organize, realize, customize
- **-lyse** not -lyze: analyse, paralyse, catalyse
- **-our**: colour, behaviour, neighbour
- **-re**: centre, fibre, calibre
- **-ll-**: cancelled, counsellor, modelling
- **-e** retained: likeable, liveable, rateable
- **-ogue**: analogue, catalogue

US spelling only in code identifiers and API surfaces (`color` in CSS).

## Writing rules — apply to every sentence

### 1. Lead with the point

First sentence = the claim. No preamble, no throat-clearing, no "It's
worth noting that…". Enter at the verb. If the opening three words can be
deleted, delete them.

**Good:** "AI workflows fail in novel ways."
**Bad:** "At df12, we believe that AI workflows can sometimes fail in
novel ways."

### 2. Compress

Shortest version that preserves meaning. After drafting, delete every
adjective and adverb, then add back only those that change the meaning.

**Good:** "Predictable behaviour across environments."
**Bad:** "What we aim to achieve is a seamless experience that remains
reliably predictable across a wide variety of different environments."

### 3. Evidence before commentary

Assertions carry a source: a number, a version, a named technology, a
link. Commentary follows evidence, never precedes it. If a claim cannot
be substantiated, cut it or flag the gap.

**Good:** "Tested against PostgreSQL 16.2, SQLite 3.45, and DuckDB 1.0."
**Bad:** "This should work with most databases."

### 4. No hedging in product copy

Remove "I think", "perhaps", "it seems", "we believe" unless genuine
uncertainty exists and is worth communicating.

### 5. Dry wit only

Humour is deadpan, observational, or absurdist. It never explains itself.
No emoji in product copy. No exclamation marks for enthusiasm. If a joke
needs signalling, it is not good enough.

**Good:** "Long enough to know where the sharp edges hide."
**Bad:** "We've been around the block a few times! 😄"

### 6. Rhetorical questions must be devastating

The answer must be self-evident. If it is ambiguous, rephrase as a
statement.

**Good:** "If a system cannot be reasoned about, why would anyone trust
it?"
**Bad:** "Have you ever thought about what it would be like to have more
legible infrastructure?"

### 7. No startup vocabulary

Never use: revolutionary, game-changing, next-generation, cutting-edge,
best-in-class, we're thrilled to announce, we're excited to share,
leverage (as a verb), synergy, disrupt, empower, unlock.

## Personal pronouns

Avoid first- and second-person pronouns by default. Use impersonal and
third-person constructions: "developers can…", "the tool provides…",
"systems should be legible."

Pronouns are permitted in exactly four contexts:

1. **Calls to action:** "Start building." / "Try it today."
2. **Testimonial or personal narrative:** "I've spent years leading
   teams…"
3. **BDD-style steps or user stories:** "When I run the command…"
4. **README openers with direct address:** "You can install with…"

Everywhere else, rewrite.

## Punctuation

- **Oxford comma** always.
- **Collective nouns** take plural verbs: "df12 are releasing…"
- **Contractions** are natural: "it's", "won't", "doesn't".
- **Sentence fragments** permitted when intentional.
- **Spaced en dash** ( – ) not unspaced em dash.

## Naming

- **df12** — always lowercase. Never DF12, Df12, DF-12.
- **df12 Productions** — full name on first formal reference; "df12"
  thereafter.
- **Edinburgh** — always name the city. "Based in Edinburgh, Scotland" on
  first reference.
- **"Software gremlin"** — acceptable in informal copy. Not a title.

## Structure and rhythm

Alternate between short declarative sentences and longer ones that
elaborate. The short sentence delivers the point; the longer one provides
evidence or context.

**Pattern:** Bold fragment. Supporting sentence with detail.

> **Small, Sharp Tools.** Each tool does one thing exceptionally well. No
> bloat, no feature creep, just focused utility.

Reserve anaphora (parallel repetition) for moments of genuine conviction.
It works because it is rare.

## Calls to action

Direct. No ceremony.

**Good:** "Install with `cargo install`. First run in under five minutes."
**Bad:** "Why not give it a try today and see if it works for you?"

## Formatting

- Paragraphs at 80 columns, code at 120.
- Headings in sentence case.
- `-` as first-level bullet.
- Language identifier on every fenced code block.
- Expand uncommon acronyms on first use.

## The Logisphere crew

The Logisphere is df12's community of experts — illustrated plushie
characters representing specialist review lenses. Read the full guidance
in `references/voice-and-copy-style-guide.md` section 12 before writing
any content that involves the crew. The critical rules:

### Core roster

| Character | Domain |
|---|---|
| Pandalump 🐼 | Architecture & structure |
| Wafflecat 🐈🧇 | Creative R&D & alternatives |
| Buzzy Bee 🐝 | Performance & observability |
| Telefono ☎️ | Types, contracts & protocols |
| Doggylump 🐶 | Reliability & failure modes |
| Dinolump 🦕 | DX, readability & continuity |

Sharkylump 🦈 chairs the governance structure but does not appear in
illustrated content.

### Two deployment modes — never mix within a document

**Mode A — Core crew as scene illustrations.** Use the six Logisphere
characters when the content concerns df12's general tools, processes, or
methodology. Each character appears in sections matching their domain.

**Mode B — Product-specific characters.** Create bespoke characters that
map to the product's architectural concepts. The core crew does not
appear.

Choose the mode that best serves the product's domain concepts. Do not
mix modes in a single document.

### Illustration rules

- Every illustration carries a caption naming the characters and
  describing the scene.
- Characters appear at narrative beats, not every section. Five or six
  illustrations in a ten-section paper is typical.
- Characters perform domain-appropriate actions (Telefono examines
  schemas; Pandalump draws on a whiteboard).
- Plushie/needle-felted aesthetic only. No photorealism, clip art, or
  generic mascots.
- Opening scene: the crew gathers. Closing scene: celebration or
  resolution.

### Copy rules

- Name characters on first appearance with a brief action phrase.
- **Never explain the conceit.** No "meet our fun mascots."
- Characters illustrate; they do not narrate. Body text stays in the
  df12 voice.
- Attribution line in footer: "Illustrated by the Logisphere crew" or
  "Illustrated by the df12 Productions plushie gang."
- Mode B characters get a brief key mapping characters to concepts on
  first appearance.

## Self-check before delivering copy

Run this checklist against every piece of output:

1. Can any sentence lose its first three words? Cut them.
2. Does every factual claim have evidence? Link or cite it.
3. Am I explaining a joke? Delete the explanation.
4. Would a question land harder than a statement?
5. Am I hedging? Remove it.
6. Is this the shortest version that preserves the meaning?
7. Does the register match the audience?
8. Would this sound stilted read aloud? Rewrite it.
9. Is this "serious tools" or "playful worlds" — and does it need to be
   both? Not every sentence carries both. The mix across a page is what
   matters.
10. Am I using a personal pronoun? Check the four permitted contexts.

## Examples of the voice in action

**Product description (landing page):**

> Netsuke compiles YAML to Ninja build files. One input format, one
> output format, no opinions about what gets built. Describe the graph;
> Netsuke writes the manifest.

**Feature bullet (product page):**

> **Repeatability Over Magic.** Predictable behaviour across
> environments. Green-path repeatability means fewer surprises in
> production.

**About page (informal):**

> Payton has spent years leading teams in large organisations — long
> enough to know where the sharp edges hide. df12 is their way of
> turning that scar tissue into a coherent boutique studio instead of a
> junkyard of side projects.

**Migration guide section heading + lead (technical):**

> ## Async steps, unit returns, and type precision
>
> v0.5.0 supports `async fn` step handlers directly. Async work no
> longer needs to be forced into fixtures or adapter traits.

**White paper abstract (formal):**

> Formal verification delivers stronger correctness guarantees than
> testing ever can. Most teams still won't touch it. The tooling is
> hostile, the artefacts are opaque, and the cognitive overhead is
> brutal.
