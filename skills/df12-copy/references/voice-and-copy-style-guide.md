# df12 Productions: voice and copy style guide

*Guidance for marketing copy, landing pages, product descriptions, and public-facing
technical writing. Not a documentation standard—see the documentation style guide for
repository prose.*

---

## Governing principle

**Serious tools, playful worlds.**

df12 copy earns trust through compression and precision. It entertains through
wit, not whimsy for its own sake. Every sentence carries its weight; any that
doesn't gets cut. The reader is a working developer who can smell filler at
forty paces.

The voice sits at the intersection of three qualities:

- **Authority through economy.** Short sentences land hardest when the reader
  knows the writer *could* elaborate and chose not to.
- **Warmth through craft.** Playfulness lives in word choice, rhythm, and
  surprise—never in exclamation marks, emoji, or hollow enthusiasm.
- **Respect through precision.** Technical users trust copy that uses exact
  terms. Hedging and hand-waving signal that the author does not understand the
  product.

---

## 1. Spelling and locale

Use British English based on the Oxford English Dictionary locale
`en-GB-oxendict`:

- suffix **-ize** in words like *realize*, *organize*, and *customize*
  (not -ise),
- suffix **-lyse** in words not traced to the Greek -izo/-izein suffixes:
  *analyse*, *paralyse*, *catalyse*,
- suffix **-our**: *colour*, *behaviour*, *neighbour*,
- suffix **-re**: *centre*, *fibre*, *calibre*,
- doubled **l**: *cancelled*, *counsellor*, *modelling*,
- retained **e**: *likeable*, *liveable*, *rateable*,
- suffix **-ogue**: *analogue*, *catalogue*.

Preserve United States spelling only in code identifiers, API surfaces, and
established product names (e.g. `color`, `gray` in CSS).

The word **"outwith"** is acceptable.

---

## 2. Punctuation and grammar

- **Oxford comma.** "Ships, planes, and hovercraft" where it aids
  comprehension.
- **Collective nouns.** Company names take plural verbs: "df12 are releasing…",
  "Concordat Industries are expanding."
- **Contractions.** Natural and encouraged. "It's", "won't", "doesn't" read
  as human; "it is", "will not", "does not" read as legal boilerplate. Use the
  expanded form only for emphasis or clarity.
- **Sentence fragments.** Permitted when intentional. "No bloat. No feature
  creep. Just focused utility."
- **Semicolons.** Use sparingly. Two short sentences usually read better than
  one long one split by a semicolon.
- **Em dashes.** Use the spaced en dash ( – ) per Oxford convention rather than
  an unspaced em dash.

---

## 3. Personal pronouns

Marketing copy for df12 avoids first- and second-person pronouns by default.
Third person and impersonal constructions keep the focus on the tool, not the
author or the reader.

Pronouns are permitted in these narrow contexts:

| Context | Example |
|---|---|
| Calls to action | "Start building." / "Try it today." |
| Testimonial or personal narrative | "I've spent years leading teams…" |
| BDD-style steps or user stories | "When I run the command…" |
| Direct address in README openers | "You can install with…" |

Outside these contexts, prefer constructions like "developers can…", "the tool
provides…", or "systems should be legible" over "you can…", "we provide…", or
"your systems."

---

## 4. Lead with the point

The first sentence states the claim, delivers the value, or names the thing.
Context follows only if needed. Preamble is dead weight.

### Do

> Good infra stays out of your way until you need it.

> Each tool does one thing exceptionally well.

> AI workflows fail in novel ways.

### Don't

> At df12, we believe that good infrastructure should stay out of your way
> until you need it.

> It's worth noting that each of our tools is designed to do one thing
> exceptionally well.

### Test

Read the first sentence of every paragraph in isolation. If any of them could
be deleted without losing information, the paragraph started too late.

---

## 5. Evidence first, commentary second

Assertions carry a source. A benchmark number, a link, a specific constraint,
a named technology. Personal commentary sits *after* the evidence—or not at
all.

### Do

> Response times under 200ms at the 95th percentile.

> Tested against PostgreSQL 16.2, SQLite 3.45, and DuckDB 1.0.

> "$120 per million output tokens. Ouch."

### Don't

> We think performance is really important, so we've optimized extensively.

> This should work with most databases.

### Guidance

If a claim cannot be substantiated, cut it or flag the gap honestly.
"Benchmarks pending" is stronger than an unanchored superlative. Intellectual
honesty is not a weakness; it is the entire game.

---

## 6. Compression

Every sentence should be the shortest version that preserves the meaning. If a
sentence can lose its first three words without changing its substance, cut
them.

### Do

> From installation to first successful run in under five minutes.

> Predictable behaviour across environments.

> Complexity exists in the implementation, not the interface.

### Don't

> What we aim to achieve is a seamless experience from the point of
> installation all the way through to the first successful run, and we target
> doing this in under five minutes.

### Test

After drafting, delete every adjective and adverb. Add back only those that
change the meaning.

---

## 7. Dry wit, not decoration

Humour arrives without announcement and trusts the reader to keep up. It never
explains itself. It earns a quick laugh and moves on.

### Do

> Mediaeval skyline, liminal closes, and a surprisingly feral little tech
> scene.

> The software gremlin behind df12.

> Long enough to know where the sharp edges hide.

### Don't

> We're a fun, quirky little studio! 🎉

> Edinburgh – you might know it from the festival, but there's great tech here
> too!

### Guidance

If something needs a signal that it is funny (an emoji, "haha", "just
kidding"), it is not funny enough to include. The exception is the occasional
😂 or 😁 in informal developer contexts—never in product copy, landing pages,
or announcements.

---

## 8. Technical precision, conversational frame

Technical explanations maintain accuracy but resist jargon for its own sake.
Pitch to the room: in copy aimed at Rust developers, assume the reader knows
what serde is. In a landing page aimed at a broader engineering audience,
unpack concepts without condescension. The concrete example always beats the
abstract definition.

### Do

> Hexagonal architecture keeps the domain logic clean. Ports define the
> boundaries; adapters plug in the infrastructure. Swap a database, swap a
> message broker – the core never notices.

> Observability is not an add-on. It is the foundation everything else rests
> on.

### Don't

> For those who may not be familiar, hexagonal architecture is a pattern
> that separates concerns…

> Observability, which refers to the ability to understand the internal state of
> a system based on its external outputs, is something we prioritise.

---

## 9. Structure and rhythm

Copy alternates between short declarative sentences and slightly longer ones
that elaborate. The short sentence delivers the point; the longer one provides
the evidence or the context. This rhythm prevents monotony without sacrificing
compression.

### Pattern

> **Short.** Longer sentence that supports the short one with detail.

Applied:

> **Small, Sharp Tools.** Each tool does one thing exceptionally well. No
> bloat, no feature creep, just focused utility.

> **Respect Cognitive Load.** Systems should be legible and unsurprising.
> Complexity exists in the implementation, not the interface.

Reserve anaphora (deliberate parallel repetition) for moments of genuine
conviction. It works because it is rare. Deploying it on minor product features
dilutes its force.

---

## 10. Formatting

- Wrap paragraphs at 80 columns.
- Use Markdown headings (`#`, `##`, `###`) in order without skipping levels.
- Write headings in sentence case.
- Use `-` as the first-level bullet.
- Always provide a language identifier for fenced code blocks; use `plaintext`
  for non-code text.
- Ensure blank lines before and after lists and fenced blocks.
- Expand uncommon acronyms on first use: Continuous Integration (CI).
- Follow [markdownlint](https://github.com/DavidAnson/markdownlint)
  recommendations.

---

## 11. Naming and identity

| Term | Usage |
|---|---|
| **df12** | Always lowercase. Never "DF12", "Df12", or "DF-12". |
| **df12 Productions** | Full legal/formal name. Use on first reference in formal contexts; "df12" thereafter. |
| **Logisphere crew** | See section 12 for deployment guidance. Refer to characters by name; never explain the conceit. |
| **"Software gremlin"** | Acceptable self-descriptor in informal copy. Not a title. |
| **Edinburgh** | Always name the city. "Based in Edinburgh, Scotland" on first reference. |

---

## 12. The Logisphere crew in public-facing copy

The Logisphere is df12's community of experts — a cast of illustrated plushie
characters, each representing a specialist review lens. They appear in white
papers, migration guides, release announcements, and blog posts. Their purpose
is to make "serious tools, playful worlds" literal: rigorous technical content,
illustrated by a cast the reader remembers.

### The core crew

Six characters form the permanent roster. Each maps to a domain concern, not
a personality quirk:

| Character | Domain | One-line lens |
|---|---|---|
| **Pandalump** 🐼 | Architecture & structure | Does every component have one job and a good name? |
| **Wafflecat** 🐈🧇 | Creative R&D & alternatives | Is this the obvious solution or the right one? |
| **Buzzy Bee** 🐝 | Performance & observability | What happens at 10× load? Where are the metrics? |
| **Telefono** ☎️ | Types, contracts & protocols | Do the types make invalid states unrepresentable? |
| **Doggylump** 🐶 | Reliability & failure modes | What is the user experience of this failure? |
| **Dinolump** 🦕 | DX, readability & continuity | Would a new contributor understand this in a day? |

**Sharkylump** 🦈 is the chair and designated responsible individual (DRI) of
the Logisphere governance structure. Sharkylump does not appear in illustrated
content but may be referenced in governance contexts and internal process
documentation.

### When to deploy the crew

The crew appears in two distinct modes depending on the product and audience.

**Mode A — Core crew as scene illustrations.** Use the six Logisphere
characters directly when the content concerns df12's general tools, processes,
or methodology. Each character appears in sections that align with their
domain: Telefono illustrates a section on type changes; Doggylump illustrates
fixture isolation and failure handling; Pandalump unveils architectural
decisions. The crew collectively appears in opening and closing scenes (the
workshop gathering, the celebration).

**Mode B — Product-specific characters.** When a product has its own narrative
world, create bespoke characters that map to the product's architectural
concepts rather than reusing the core crew. Zamburak introduces Zamburak the
CaMeL, Monty Mole, Sly Scorpion, and the P-LLM/Q-LLM cubes — each a direct
analogue of a system component or threat actor. The core Logisphere crew does
not appear.

The choice between modes depends on whether the product's domain concepts are
better served by the existing lenses (Mode A) or by characters that *are* the
architecture (Mode B). Do not mix modes within a single document.

### Illustration conventions

- **Every illustration carries a caption.** The caption describes the scene and
  names the characters present. Screen readers depend on this.
- **Characters appear at narrative beats, not every section.** A white paper
  with ten sections might have five or six illustrations. Overcrowding dilutes
  the visual storytelling.
- **Characters perform domain-appropriate actions.** Telefono examines schema
  documents. Doggylump oversees a construction site. Wafflecat experiments.
  Pandalump draws on a whiteboard. The action reinforces the lens.
- **The plushie aesthetic is non-negotiable.** Characters are rendered as
  needle-felted or soft-toy style illustrations, consistent with the df12
  visual identity. Photorealism, corporate clip art, and generic mascot styles
  are all wrong.
- **Opening scene: the crew gathers.** Establish the cast at the start so the
  reader knows who they are following.
- **Closing scene: celebration or resolution.** The final illustration marks
  completion — a picnic, a campfire, a green CI run. This is the "playful
  worlds" payoff.

### Copy rules for character references

- **Name characters on first appearance.** "Telefono validates the new type
  signatures while Wafflecat demonstrates `async fn`." After first reference,
  the name alone suffices.
- **Never explain the conceit.** Do not write "these are our fun mascot
  characters who represent different aspects of software quality." The
  illustrations and captions do that work. The reader either gets it or does
  not need to.
- **Keep character voice out of the prose.** The crew illustrates; they do not
  narrate. The body text remains in the df12 voice described in this guide.
  Characters do not speak in dialogue or deliver opinions in the copy itself.
- **Attribution line.** White papers and illustrated guides carry the line
  "Illustrated by the Logisphere crew" or "Illustrated by the df12 Productions
  plushie gang" in a footer or colophon section. This is the only place where
  the conceit is made explicit.
- **Product-specific characters get an introduction.** When using Mode B,
  provide a brief key (illustration gallery or inline caption) mapping
  characters to concepts on first appearance. "Zamburak the CaMeL and Monty
  Mole arrive to defend the LLM cubes" is sufficient — the mapping is
  self-evident from context.

### What the crew is not

- **Not decoration.** If an illustration does not reinforce the section's
  technical content, cut it.
- **Not a substitute for explanation.** The prose must stand alone. A reader
  who ignores every illustration should still understand the document fully.
- **Not a brand mascot in the traditional sense.** The crew does not appear on
  merchandise, in advertising taglines, or as profile avatars for the company.
  They live in technical narratives. That constraint is what keeps them
  effective.

---

## 13. Tone boundaries

### What df12 copy is

- Compressed, precise, and grounded.
- Dry, deadpan, occasionally absurdist.
- Confident without being arrogant.
- Helpful without being asked—prescribe clearly, triage fast.

### What df12 copy is not

- Breathless, excitable, or startup-adjacent ("revolutionary", "game-changing",
  "we're thrilled to announce").
- Self-deprecating to the point of undermining the product.
- Cruel. Bluntness targets positions, bad defaults, and industry pathology—not
  individuals (public grifters excepted).
- Hedging. "Perhaps", "it seems", "we believe" have no place in product copy
  unless genuine uncertainty exists and is worth communicating.

---

## 14. Rhetorical questions

The rhetorical question is a precision instrument, not a softening device. It
forces the reader to confront the logical consequence of a position.

### Do

> If a system cannot be reasoned about, why would anyone trust it?

> What happens when an AI workflow fails in a way nobody anticipated?

### Don't

> Have you ever thought about what it would be like to have more legible
> infrastructure?

### Test

The answer to a rhetorical question must be self-evident. If the answer is
ambiguous, rephrase as a statement.

---

## 15. Calls to action

Direct. No ceremony.

### Do

> Install with `cargo install`. First run in under five minutes.

> Read the docs. File an issue. Ship something.

### Don't

> Why not give it a try today and see if it works for you?

> We'd love for you to check out the documentation and let us know what you
> think!

---

## 16. Copy checklist

When editing, ask:

1. **Can this sentence lose its first three words?** Cut them.
2. **Is there a source?** Factual claims need evidence. Link it or cite it.
3. **Am I explaining a joke?** Delete the explanation.
4. **Would a question land harder than a statement?** Especially when
   challenging assumptions.
5. **Am I hedging?** Remove "I think", "perhaps", "it seems" unless genuine
   uncertainty exists.
6. **Is this the shortest version that preserves the meaning?** Compress.
7. **Does the register match the audience?** Technical in technical spaces,
   human in human ones.
8. **Would I say this out loud?** If it sounds stilted read aloud, rewrite it.
9. **Is this "serious tools" or "playful worlds"—and does it need to be both?**
   Not every sentence carries both qualities. Some are precise. Some are fun.
   The mix across a page is what matters.
10. **Am I using a personal pronoun?** Check it against the permitted contexts
    in section 3. If it doesn't fit, rewrite in the impersonal.
