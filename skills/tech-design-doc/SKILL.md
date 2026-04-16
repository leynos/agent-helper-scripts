---
name: tech-design-doc
description: >
  Generate rigorous technical design documents from a problem statement or
  product brief. Use this skill whenever the user asks to produce a system
  design, technical specification, architecture document, design document,
  or product design — whether from scratch, from an existing brief, or by
  expanding a rough concept into a full specification. Also trigger when
  the user asks to "write a design doc", "spec this out", "produce an
  architecture document", "design this system", or provides a problem
  statement and expects a structured technical output. The skill drives a
  multi-phase workflow: research, outline, planning, drafting with
  external artefacts, Mermaid diagram validation, and a mandatory editing
  pass. It produces documents in the style of df12 Productions design
  documents — precise, evidence-grounded, and free of fluff.
---

# Technical design document generation

A skill for producing rigorous technical design documents from problem
statements, product briefs, or rough concepts.

## Before starting

Read the following reference files as needed during the workflow:

| Reference | When to read | Path |
|---|---|---|
| **Document anatomy** | Before outlining — structural patterns and section catalogue | `references/document-anatomy.md` |
| **Research protocol** | Before the research phase — methodology and source evaluation | `references/research-protocol.md` |
| **Editing checklist** | Before the final editing pass — the fluff-elimination protocol | `references/editing-checklist.md` |

## Governing principles

1. **Evidence before assertion.** Every architectural claim, technology
   choice, or design trade-off must cite a source, benchmark, or
   reasoned argument. Unsupported claims get cut in editing.

2. **Precision over comprehensiveness.** A shorter document that says
   exactly what it means beats a longer one that covers everything
   vaguely. The editing pass exists to enforce this.

3. **External artefacts first.** Schemata, domain models, interface
   contracts, and code snippets are drafted as separate files, validated
   independently, then incorporated into the document. This prevents
   drift between prose descriptions and actual definitions.

4. **Diagrams earn their place.** Every Mermaid diagram must be
   validated with nixie before incorporation. A diagram that does not
   parse is worse than no diagram.

5. **The document is the design.** Ambiguity in the document is
   ambiguity in the design. If a section cannot be written clearly, the
   design is not yet clear enough.

## Workflow

Execute these phases in order. Each phase produces concrete output
before the next begins. Do not collapse phases or draft prose before
the outline is agreed.

### Phase 0 — Intake and scoping

Establish the document's boundaries:

1. **Problem statement.** What is being designed, and why? If the user
   has provided a brief or prompt (as in the splitters example), extract
   the authoritative problem statement from it. If not, draft one and
   confirm.

2. **Audience.** Who will read this document? Developers implementing
   the system, reviewers evaluating the design, operators running it, or
   a combination? Pitch depth and vocabulary accordingly.

3. **Scope boundaries.** What is explicitly in scope? What is an
   explicit non-goal? Non-goals prevent scope creep during drafting.

4. **Decision authority.** Which design choices does this document make
   versus defer? Identify decisions that belong in separate ADRs,
   roadmaps, or engineering standards documents.

5. **Prior art.** Does the user have existing documents, codebases, or
   designs that inform this one? Identify them early — they set
   constraints.

If the user's prompt already answers these questions (as a detailed
brief would), extract and confirm rather than re-asking.

### Phase 1 — Research

Conduct targeted research using available tools. The goal is to ground
the design in current ecosystem reality, not to produce a literature
review.

**Use Firecrawl MCP when available.** A companion Firecrawl skill
provides tool surface details and query patterns — load it for the
research phase. → Read `references/research-protocol.md` for research
methodology and source evaluation criteria.

**When Firecrawl MCP is not connected,** fall back to `web_search` and
`web_fetch` for research. The research protocol still applies.

Research targets (select those relevant to the design):

- **Ecosystem survey.** What existing tools, libraries, frameworks, or
  protocols occupy this space? What are their strengths, limitations,
  and architectural choices? This prevents designing something that
  already exists or repeating known mistakes.
- **Standards and specifications.** Are there relevant RFCs, W3C specs,
  protocol definitions, or de facto standards?
- **Academic and industry literature.** Are there research results,
  benchmarks, or well-known architectural patterns that inform the
  design?
- **Technology baseline.** For implementation choices (languages,
  frameworks, infrastructure), gather current version numbers, API
  surfaces, and known constraints.

Produce a research summary as a working note. This is not part of the
final document, but it informs every subsequent phase. Include sources
with URLs.

### Phase 2 — Outline

Produce a section-level outline of the document. →
Read `references/document-anatomy.md` for the section catalogue and
structural patterns.

The outline must:

- map every requirement from the problem statement to at least one
  section,
- identify sections that need diagrams,
- identify sections that need external artefacts (schemata, models,
  code, interface definitions),
- flag sections where research gaps remain,
- establish the dependency order between sections (some sections
  reference concepts defined in earlier ones).

Present the outline to the user for agreement before proceeding. The
outline is a contract — deviations during drafting require
justification.

### Phase 3 — External artefacts

Before drafting prose, produce the structured artefacts that the
document will reference. Draft each as a separate file in the working
directory.

Artefact types and their file formats:

| Artefact | Format | Purpose |
|---|---|---|
| Domain model / glossary | Markdown or TOML | Normative terminology and entity definitions |
| Data schemata | SQL, Protobuf, JSON Schema, TOML, or language-native types | Canonical data structures |
| Interface contracts | OpenAPI, gRPC `.proto`, CLI help text, or type signatures | API and command surfaces |
| Configuration formats | TOML, YAML, or JSON with comments | On-disk or runtime configuration shapes |
| Code snippets | Language-native source files | Reference implementations, algorithm sketches |
| State machines | Mermaid `stateDiagram-v2` | Lifecycle and transition definitions |
| Sequence diagrams | Mermaid `sequenceDiagram` | Interaction protocols |
| Architecture diagrams | Mermaid `graph` or `C4Context` | System structure |
| Entity relationships | Mermaid `erDiagram` | Data model relationships |

**Why external files?** Three reasons:

1. **Validation.** Code compiles or it doesn't. Schemata parse or they
   don't. Catching errors before they enter prose prevents a class of
   document bugs.
2. **Reconciliation.** When a schema changes, updating one file and
   re-incorporating is less error-prone than hunting through prose.
3. **Reuse.** External artefacts can seed implementation directly.

For Mermaid diagrams, validate each one immediately after drafting:

```bash
# Clone nixie if not already present
git clone https://github.com/leynos/nixie.git /tmp/nixie 2>/dev/null || true

# Inspect nixie's README for current invocation instructions
cat /tmp/nixie/README.md

# nixie validates inline Mermaid blocks in Markdown files.
# Wrap standalone .mmd files in a Markdown fenced block before
# passing them to nixie:
validate_mermaid() {
  local src="$1"
  local tmp
  tmp=$(mktemp --suffix=.md)
  printf '```mermaid\n' > "$tmp"
  cat "$src" >> "$tmp"
  printf '\n```\n' >> "$tmp"
  # Run nixie against the wrapper file — consult the README output
  # above for the exact invocation command.
  cd /tmp/nixie && <nixie-command> "$tmp"
  local rc=$?
  rm -f "$tmp"
  return $rc
}
```

On first use in a session, read nixie's README to confirm the
invocation command — the tool may evolve. The wrapper function above
handles the common case of validating a standalone `.mmd` file by
embedding it in a Markdown document, which is nixie's expected input
format.

If a diagram does not validate, fix it before proceeding. Do not defer
diagram fixes to the editing pass.

### Phase 4 — Drafting

Draft the document section by section, following the agreed outline.

**Drafting rules:**

1. **One section at a time.** Complete each section before starting the
   next. This prevents half-finished sections from accumulating.

2. **Incorporate artefacts by reference or inline.** When a section
   references an external artefact, either include it as a fenced code
   block (for short artefacts) or reference the file path (for long
   ones that will be adjacent to the design doc in the repository).

3. **Diagrams are prose, not decoration.** Every diagram must be
   introduced by a sentence explaining what it shows and followed by
   prose that draws attention to the important relationships. A diagram
   without surrounding prose is a diagram the reader will skip.

4. **Cross-reference, don't repeat.** If a concept is defined in
   section 3, section 7 should reference it, not redefine it. Forward
   references are acceptable if flagged ("see §7.2 below").

5. **Decision records.** When the design makes a non-obvious choice,
   record the decision, the alternatives considered, and the reasoning.
   These can be inline or referenced as separate ADR files, depending
   on the document's conventions.

6. **Failure modes are not optional.** Every system has failure modes.
   If a section describes a mechanism, it should also describe what
   happens when that mechanism fails, degrades, or receives unexpected
   input.

7. **Write in active voice.** "The orchestrator dispatches tasks" not
   "Tasks are dispatched by the orchestrator." Passive voice obscures
   agency and responsibility — both of which matter in a design.

**Section-level checklist (apply to each section before moving on):**

- Does this section fulfil its obligation from the outline?
- Are all claims substantiated?
- Are all artefacts incorporated or referenced?
- Would removing any paragraph lose information? If not, remove it.
- Does the section introduce terms that should be in the glossary?

### Phase 5 — Diagram validation pass

After all sections are drafted, run every Mermaid diagram through nixie
as a batch. If the design document is a single Markdown file with
inline Mermaid blocks, pass the entire file to nixie directly — this is
its native input format.

```bash
cd /tmp/nixie && <nixie-command> /path/to/design-document.md
```

Fix any failures. This is a hard gate — a document with broken diagrams
is not complete.

### Phase 6 — Editing pass

The editing pass is mandatory, not optional. Its purpose is to remove
fluff, tighten prose, and enforce consistency.

→ Read `references/editing-checklist.md` for the complete protocol.

**The editing pass is destructive.** It removes content. It shortens
sentences. It eliminates hedging, throat-clearing, and unsupported
claims. This is intentional. A design document that says less but means
it is more useful than one that says more and hedges.

The editing pass addresses these categories in order:

1. **Structural coherence.** Do sections flow logically? Are there gaps
   or redundancies? Does the document fulfil the outline contract?

2. **Fluff elimination.** Delete every sentence that does not
   contribute information. Delete every word that does not contribute
   meaning. Specific targets:
   - Throat-clearing ("It is worth noting that…", "In order to…")
   - Hedge words ("perhaps", "it seems", "arguably", "it could be said")
   - Tautologies ("completely unique", "very essential")
   - Filler transitions ("Additionally", "Furthermore", "Moreover" when
     the connection is already obvious)
   - Meta-commentary about the document itself ("This section
     describes…", "As mentioned above…")

3. **Vocabulary precision.** Replace vague terms with precise ones.
   "The system handles errors" → "The dispatcher retries failed tasks
   three times with exponential backoff." Specificity is the difference
   between a design and a wish list.

4. **Consistency.** Terminology, capitalisation, hyphenation, and
   spelling must be consistent throughout. If the glossary says
   "merge base" (two words), every instance in the document must match.

5. **Source verification.** Every factual claim must still have a
   source. Any claim that lost its source during drafting either gets
   one or gets cut.

6. **Locale enforcement.** British English with Oxford spelling
   throughout (unless the user specifies otherwise): -ize, -yse, -our,
   -re, -ll-, spaced en dash, Oxford comma, sentence case headings.

### Phase 7 — Assembly and delivery

Assemble the final document:

1. Incorporate all validated external artefacts.
2. Add front matter (title, status, audience, date).
3. Add a table of contents if the document exceeds ~30 sections.
4. Add a glossary if domain-specific terms are used.
5. Add a references section with all cited sources.
6. Deliver as a Markdown file.

If the user requests a Word document (.docx), use the docx skill for
final formatting after the Markdown master is complete.

## Structural patterns across df12 design documents

These patterns are observed in the example corpus (Corbusier, Episodic,
Weaver, Zamburak, Splitters) and should inform — not rigidly
constrain — the outline:

- **Zamburak pattern.** Threat model → trust boundaries → architecture
  → component contracts → verification. Suited to security-critical
  systems. Normative glossary up front. Explicit non-goals. Companion
  documents referenced by path.

- **Episodic pattern.** Overview → goals/non-goals → personas →
  architectural summary → component responsibilities → agent graph
  architecture → data model → operations. Suited to data-pipeline and
  orchestration systems. ADRs referenced. Mermaid-heavy.

- **Weaver pattern.** Vision → comparative analysis → architecture →
  component deep-dive → security model → agent capabilities → roadmap.
  Suited to developer tools. Extensive ecosystem survey. Academic
  references.

- **Corbusier pattern.** Executive summary → system overview → detailed
  architecture → component specifications → data model → operations →
  appendices with glossary and acronyms. Suited to platform products.
  Tables for stakeholder mapping. Mermaid for component topology.

Choose the pattern that best fits the system being designed, or
hybridize where appropriate. The outline phase is when this decision is
made.

## Tool integration notes

### Firecrawl MCP

A companion Firecrawl skill provides the tool surface, query patterns,
and usage guidance for the Firecrawl MCP server. Load it alongside
this skill when conducting the research phase.

Firecrawl is the preferred research tool for crawling documentation
sites, extracting structured content from JavaScript-rendered pages,
and scraping specification documents. When Firecrawl MCP is not
connected, degrade to `web_search` and `web_fetch` and note the
degradation in the research summary.

### nixie (Mermaid validation)

nixie (`github.com/leynos/nixie`) validates inline Mermaid diagrams in
Markdown files. Its native input is a Markdown document containing
fenced Mermaid code blocks — it extracts and validates each one.

Use it at two points:

1. After drafting each diagram (Phase 3) — wrap standalone `.mmd`
   files in a Markdown code fence before passing to nixie.
2. As a batch validation of the complete document (Phase 5) — pass
   the assembled Markdown file directly.

Clone nixie into `/tmp/nixie` on first use. Read its README to
confirm the invocation command before calling it — the tool may have
changed since this skill was written.

### df12 copy skill

If producing a design document for a df12 Productions product, also
load the `df12-copy` skill for voice and style enforcement. The editing
pass (Phase 6) should then apply both the editing checklist from this
skill and the self-check from `df12-copy`.

## Failure modes

- **Research phase produces no useful results.** Acknowledge the gap
  explicitly in the document. Do not fabricate ecosystem context.
- **Diagram fails nixie validation.** Fix the diagram. Do not skip
  validation. If the diagram cannot be fixed, replace it with a
  structured prose description and note the limitation.
- **Outline disagreement.** If the user disputes the outline, resolve
  before drafting. Drafting against a contested outline wastes effort.
- **Scope creep during drafting.** If a section grows beyond its
  outline allocation, either the outline was wrong (update it) or the
  section contains fluff (edit it). Do not silently expand scope.
- **External artefact contradicts prose.** The artefact is
  authoritative. Update the prose to match, not the reverse.

## Anti-patterns to avoid

- **The literature review.** A design document is not a survey paper.
  Ecosystem context earns its place only if it informs a design
  decision. Cut everything else.
- **The feature catalogue.** Listing what the system does without
  explaining how, why, or what happens when it fails is a product
  brief, not a design document.
- **The aspirational roadmap.** "In future, the system could…" belongs
  in a roadmap document, not in a design specification. The design
  document describes what is being built, not what might be built
  later.
- **The diagram gallery.** Diagrams without surrounding prose are
  decoration. Every diagram needs introduction, explanation, and
  connection to the narrative.
- **The hedge forest.** "This could potentially perhaps be implemented
  using…" — if the design has not decided, say so explicitly rather
  than hedging. Indecision is information; hedging is noise.
