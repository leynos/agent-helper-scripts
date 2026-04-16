# Roadmap conventions reference

This reference defines the formatting rules, structural model, and quality
criteria for roadmap documents. Follow these conventions exactly when
generating a roadmap.

## Document structure

A roadmap document has four parts:

1. A title and preamble.
2. A foundational phase (when needed).
3. Vertical-slice phases.
4. A deferred-extensions phase.

### Title and preamble

Open the document with a first-level heading naming the product:

```markdown
# <Product> roadmap
```

Follow with one to three paragraphs that:

- State the purpose of the roadmap and its relationship to the design
  documents.
- Explain the GIST alignment: phases carry ideas, steps work toward
  validating or falsifying those ideas, tasks are execution units.
- Note that the roadmap does not promise dates.
- Cite the primary design document and the location of RFCs or ADRs.

### Foundational phase

The first phase is permitted (and usually necessary) to cover architectural
decisions, build infrastructure, and test scaffolding. Even so, frame it as
an idea:

> Idea: if <product> settles its core contracts, packaging boundary, and
> build spine before feature work starts, later slices can converge on one
> coherent v1 architecture instead of repeatedly reworking interfaces and
> test scaffolding.

Foundational steps typically cover:

- Ratifying open decisions as ADRs (packaging boundary, scope policy, locale
  policy, transport policy).
- Establishing the repository layout and build system.
- Building the shared test corpus and contract-test scaffolding.

### Vertical-slice phases

Each subsequent phase delivers a usable vertical slice of functionality.
Order slices so that each one builds on the artefacts and contracts of the
previous slice. Prefer domain-oriented slices over tier-oriented ones.

Good slice names describe delivered value:

- "Markdown linting with real spans and safe fixes"
- "Docstrings and documentation comments in source trees"
- "Capability-planned language-aware rules"
- "Team adoption and extension ecosystem"

Bad slice names describe layers:

- "Parser implementation"
- "Backend work"
- "Frontend integration"
- "Testing phase"

### Deferred-extensions phase

Close the roadmap with a phase that collects work the design documents
mention but explicitly defer from the core release. Frame the phase idea as:

> Idea: if the core v1 promise is already trustworthy and boring to operate,
> the project can evaluate broader extensions on their product value instead
> of letting them destabilize the main release.

List deferred items as lightweight steps with one or two tasks each. Cite the
design document sections or RFCs that describe the deferred scope.

## Phase anatomy

A phase is a second-level heading with dotted numbering:

```markdown
## 2. Vertical slice 1: Markdown linting with real spans and safe fixes
```

Immediately below the heading, state the **idea** as a testable hypothesis:

> Idea: if the first vertical slice can lint Markdown with trustworthy spans,
> conservative fixes, and inspectable IR output, <product> will already solve
> a real repository problem before docstrings, plugins, or heavier NLP land.

Follow with one to two paragraphs of context explaining what the phase
delivers and why this ordering matters.

## Step anatomy

A step is a third-level heading with dotted numbering:

```markdown
### 2.1. Prove that Markdown can be flattened into a trustworthy IR
```

Immediately below the heading, state in one to two sentences:

- What question this step answers.
- What the outcome informs (subsequent steps, design choices, scope
  decisions).

Cite the relevant design document sections and RFCs.

A step groups only tasks that serve the same delivery objective. If the tasks
under a step do not share one operational purpose, split the step.

Steps are sequenced so each workstream either unlocks the next one or reduces
a specific class of delivery risk.

## Task anatomy

A task is a checkbox item with dotted numbering:

```markdown
- [ ] 2.1.1. Implement the Markdown IR envelope, `line_index`, region text,
  and `segments` mappings.
  - Requires steps 1.1-1.3.
  - Include source-backed positions, synthetic insertions, and content
    hashes.
  - Success: canonical IR JSON round-trips representative Markdown fixtures
    without span drift.
```

### Task rules

- **Dotted number.** Every headline task carries a dotted number matching its
  phase and step.
- **Checkbox.** Precede every task and sub-task with `[ ]`.
- **Concrete deliverable.** Phrase the task in terms of the capability
  delivered, not an aspiration or research topic.
- **Dependencies.** If the task depends on work outside its immediate
  sequence, cite the dependency using dotted notation on a sub-bullet:
  `Requires 2.3.1.` or `Requires steps 1.1-1.3.`
- **Design citations.** Cite the relevant design document section or RFC on a
  sub-bullet: `See design-doc.md §3.2.` or
  `See RFC 0001 §6.`
- **Success criteria.** State explicit success criteria on a sub-bullet
  prefixed with `Success:` when the criteria are not immediately obvious
  from the task description. Success criteria must be measurable or
  observable.
- **Sub-tasks.** Break complex tasks into sub-bullets describing the concrete
  build activities. Sub-tasks are indented under the headline task. They do
  not carry dotted numbers unless the roadmap is very large.
- **Scope.** Keep tasks small enough that each represents a coherent unit of
  delivery. If a task description runs to more than five sub-bullets, it is
  probably two tasks.

### Dependency notation

Use dotted notation for all dependency citations:

| Pattern                 | Meaning                                      |
| ----------------------- | -------------------------------------------- |
| `Requires 1.1.1.`      | Depends on one specific task.                |
| `Requires 1.1.1 and 1.1.2.` | Depends on two specific tasks.          |
| `Requires steps 1.1-1.3.` | Depends on all tasks in steps 1.1 through 1.3. |
| `Requires phase 2.`    | Depends on the completion of an entire phase. |

_Table 1: Dependency notation patterns._

### Design citation notation

Cite design document sections using `§` notation:

```markdown
See design-doc.md §3.2.
See RFC 0001 §6.
See design-doc.md §§5-13.
```

When a task relates to an RFC in its entirety, cite the RFC filename:

```markdown
See RFC 0002.
```

When a task relates to an ADR, cite the ADR filename:

```markdown
See adr-001-packaging-boundary.md.
```

## GIST alignment

The roadmap hierarchy maps directly to the GIST framework:

| Roadmap layer | GIST element | Purpose                                          |
| ------------- | ------------ | ------------------------------------------------ |
| Phase         | Idea         | A testable hypothesis about the product.         |
| Step          | Step         | A workstream that validates or falsifies the idea.|
| Task          | Task         | A concrete, measurable execution unit.           |

_Table 2: GIST alignment._

### What makes a good idea (phase)

An idea must be falsifiable. It should describe a bet the project is making:

- Good: "If the same extraction loop extends cleanly from Markdown into
  Python and Rust documentation surfaces, the architecture scales by domain
  rather than by piling on syntax-specific side paths."
- Bad: "Implement docstring support." (This is a wish, not a hypothesis.)

### What makes a good step

A step must have:

- A concrete objective: what will exist when the workstream is complete.
- A learning opportunity: what the step teaches that affects later sequencing
  or design.
- Coherence: all tasks under the step serve the same delivery objective.
- Sequencing value: the step either unlocks the next step or reduces a
  specific delivery risk.

### What makes a good task

A task must be:

- Concrete: it describes a build activity, not an aspiration or status label.
- Measurable: it has observable acceptance criteria.
- Atomic: it can be completed as a coherent unit.
- Traceable: it cites its design-document or RFC origin.

## Vertical-slice design

### Principle

Deliver useful functionality end-to-end in each phase rather than building
the system tier by tier. Each slice should exercise the full stack from input
to output for a specific domain.

### Sequencing heuristics

1. **Contracts and decisions before code.** Unresolved architectural
   decisions cause rework. Settle them in the foundational phase.
2. **Narrowest useful domain first.** Start with the domain that exercises
   the most architecture with the least scope. This is often the simplest
   input format with the most complete design coverage.
3. **Extend, do not rebuild.** Each subsequent slice should reuse and extend
   the loop established by the first slice, not build a parallel path.
4. **Defer what does not block adoption.** Features the design explicitly
   postpones belong in the deferred-extensions phase. Do not let them creep
   into earlier slices.
5. **Validation woven in, not bolted on.** Test scaffolding, performance
   probes, and debugging surfaces appear as tasks within each slice, not as a
   separate "testing phase" at the end.

### Cross-cutting concerns

Some work (caching, performance, debugging, documentation) touches every
slice. Handle these by including relevant tasks in each slice rather than
collecting them into a cross-cutting phase. The principle: each slice should
be independently useful and independently testable.

## Formatting rules

### Markdown conventions

- First-level heading for the document title only.
- Second-level headings for phases.
- Third-level headings for steps.
- Bullet items with checkboxes for tasks and sub-tasks.
- Blank lines before and after lists and fenced code blocks.
- Sentence-case headings throughout.
- 80-column paragraph wrapping.
- `-` as the bullet character.
- Oxford comma where it aids comprehension.

### Numbering

- Phases: `1.`, `2.`, `3.`, …
- Steps: `1.1.`, `1.2.`, `1.3.`, …
- Tasks: `1.1.1.`, `1.1.2.`, `1.1.3.`, …

Numbering appears in the heading or bullet text, not as Markdown ordered-list
syntax.

### Spelling

British English, Oxford spelling:

- -ize (organize, recognize), not -ise.
- -yse (analyse, paralyse), not -yze.
- -our (colour, behaviour), not -or.
- -re (centre, fibre), not -er.
- "outwith" and "caveat" are acceptable.
- US spelling for API identifiers (e.g. `color`).

## Structural example

The following skeleton illustrates the expected document structure. It is not
a complete roadmap; it shows the shape, not the substance.

```markdown
# Widgetron roadmap

This roadmap translates the current design and RFC set into an
outcome-oriented delivery sequence. It does not promise dates. Each phase
carries one testable idea at the GIST level. The steps underneath that phase
work toward validating or falsifying the idea, answering specific sequencing
questions, and leaving behind usable functionality rather than another
horizontal layer.

## 1. Foundational contracts and build spine

Idea: if Widgetron settles its core contracts and build spine before feature
work starts, later slices can converge on one coherent v1 architecture.

### 1.1. Ratify the v1 contracts that would otherwise force rework

This step answers what Widgetron v1 will and will not promise. Its outcome
informs the repository layout, public interfaces, and first release scope.
See widgetron-design.md §§3-5 and docs/rfcs/.

- [ ] 1.1.1. Record the transport-boundary decision as an ADR.
  - Decide between gRPC and HTTP/JSON.
  - Success: one accepted ADR defines the transport for all later work.
- [ ] 1.1.2. Record the v1 scope decisions.
  - Requires 1.1.1.
  - Confirm feature-flag policy, locale support, and API versioning.
  - Success: the v1 promises match widgetron-design.md §5.

### 1.2. Establish the repository skeleton and CI

This step answers whether the intended layout can support local development
and release builds. See widgetron-design.md §8.

- [ ] 1.2.1. Create the package structure.
  - Requires 1.1.2.
  - Success: the repository shape matches the intended architecture.
- [ ] 1.2.2. Wire CI to the build structure.
  - Requires 1.2.1.
  - Success: CI exercises the same boundary as local development.

## 2. Vertical slice 1: Core widget pipeline

Idea: if the first vertical slice can ingest, transform, and render a basic
widget with faithful source tracking, Widgetron already solves a real problem
before advanced features land.

### 2.1. Prove the transform pipeline produces faithful output

This step answers whether the core transform preserves source fidelity. See
widgetron-design.md §§6-7 and RFC 0001.

- [ ] 2.1.1. Implement the ingestion and transform pipeline.
  - Requires steps 1.1-1.2.
  - Cover standard widget types and malformed input.
  - Success: golden fixtures round-trip without data loss.
- [ ] 2.1.2. Add error recovery for malformed input.
  - Requires 2.1.1.
  - Success: malformed widgets produce diagnostics, not crashes.

### 2.2. Deliver the day-one CLI loop

This step answers whether the CLI contract supports normal usage. See
RFC 0002.

- [ ] 2.2.1. Implement the primary CLI command.
  - Requires 2.1.1.
  - Success: the command is useful on real repositories.
- [ ] 2.2.2. Add machine-readable output.
  - Requires 2.2.1.
  - Success: JSON output is stable and documented.

## 3. Deferred extensions after the core v1 promise

Idea: if the core v1 promise is already trustworthy and boring to operate,
the project can evaluate broader extensions on their product value instead of
letting them destabilize the main release.

### 3.1. Evaluate advanced widget types

- [ ] 3.1.1. Decide whether animated widgets graduate from preview.
  - Requires phase 2 completion.
  - See widgetron-design.md §12.
```

## Anti-patterns to avoid

### Layer cake

Phases named after technical tiers ("Parser", "Engine", "CLI", "Tests")
rather than delivered value. Restructure so each phase delivers a usable
slice.

### Passive headings

Steps that are just organizational labels ("Backend changes", "Other tasks")
rather than workstreams with delivery objectives. Every step must answer a
question.

### Aspirational tasks

Tasks phrased as intentions ("Improve error handling") rather than
deliverables ("Implement structured error recovery for malformed input with
golden-file regression tests"). Rewrite with concrete acceptance criteria.

### Orphaned scope

Design document sections or RFCs with no corresponding roadmap tasks. Either
add tasks or note the deferral explicitly.

### Hidden dependencies

Tasks that assume prior work without citing it. Every cross-step dependency
must use dotted notation.

### Date commitments

Roadmaps must not promise dates, durations, or timeframes. Development
effort should be roughly consistent from task to task, but the roadmap does
not predict calendar time.
