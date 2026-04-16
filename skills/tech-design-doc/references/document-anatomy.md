# Document anatomy

Structural patterns and section catalogue for technical design
documents. Read this before producing an outline (Phase 2).

## Section catalogue

Not every document needs every section. The outline phase selects from
this catalogue based on the system being designed. Sections are listed
in a natural dependency order — earlier sections define concepts that
later sections reference.

### Front matter

- **Title.** The system name and document type.
- **Status.** Draft, living design, accepted, superseded.
- **Audience.** Who reads this and what they need from it.
- **Companion documents.** ADRs, roadmaps, engineering standards,
  repository layouts — anything normative that lives outside this
  document. Reference by path.
- **Date and version.** When this was last substantively updated.

### Problem and context

- **Design context and motivation.** Why does this system exist? What
  external observations, research results, or operational pain points
  drive the design? Cite sources.
- **Core business problem.** The problem in terms the reader's
  organisation cares about.
- **Prior art and ecosystem survey.** What exists already? What are its
  strengths and limitations? This section earns its length only if it
  informs design decisions. A survey that does not lead to a "therefore
  we chose X" is a literature review and should be cut.

### Scope and goals

- **Goals.** What the system does, framed as verifiable outcomes.
- **Non-goals.** What the system explicitly does not attempt. Non-goals
  prevent scope creep and set expectations.
- **Design intent summary.** A paragraph distilling the architectural
  philosophy. This is the thesis statement of the document.

### Terminology

- **Glossary.** Normative definitions for domain-specific terms. Every
  term used inconsistently in everyday language but precisely in this
  design gets an entry. Include naming conventions (casing, prefixes)
  if they matter.
- **Acronyms.** Expand every acronym on first use in the document body,
  and collect them in a table for reference.

### Personas and actors

- **User types.** Who interacts with the system? What are their goals,
  constraints, and technical fluency?
- **System actors.** Non-human participants: CI pipelines, cron jobs,
  external services, LLM agents.

### Architecture

- **Architectural summary.** A paragraph-level overview of the system's
  shape: what pattern it follows (hexagonal, event-driven, pipeline,
  etc.), what its major boundaries are, and how data flows.
- **Architecture diagram.** A Mermaid diagram showing major components
  and their relationships. Validate with nixie.
- **Trust boundaries.** Where does trusted code meet untrusted input?
  Where do privilege levels change? For security-critical systems, this
  is its own section with explicit attacker capabilities and protected
  assets (see the Zamburak pattern).
- **Component topology.** How components are deployed, scaled, and
  connected at runtime.

### Domain model

- **Core domain model.** The entities, their relationships, and their
  invariants. Produce as an external artefact (ER diagram, type
  definitions, or both) before writing prose.
- **Aggregate boundaries.** Which entities are modified together? Where
  are consistency boundaries?
- **State machines.** Lifecycle diagrams for entities with non-trivial
  state transitions. Validate with nixie.

### Component specifications

One subsection per major component. Each should cover:

- **Responsibility.** What does this component own? One sentence.
- **Ports.** What interfaces does it expose and consume? (For hexagonal
  architectures.)
- **Behaviour.** How does it process inputs and produce outputs?
  Sequence diagrams where interactions are non-obvious.
- **Failure modes.** What happens when this component fails, receives
  unexpected input, or cannot reach its dependencies?
- **Configuration.** What tunables does this component expose?

### Interfaces and contracts

- **CLI contract.** Command names, arguments, flags, exit codes, output
  formats. For CLI tools, this is often the most important section.
- **API contract.** HTTP endpoints, gRPC services, message formats.
  Produce as an external artefact (OpenAPI, `.proto`) and incorporate.
- **On-disk formats.** File formats the system reads or writes.
  Produce as external artefacts with examples.
- **Wire protocols.** Message formats for inter-component communication.

### Data model and storage

- **Schema.** Database tables, document structures, or key-value
  layouts. Produce as external artefacts.
- **Migration strategy.** How the schema evolves over time.
- **Data lifecycle.** Retention, archival, deletion policies.
- **Consistency model.** What guarantees does the storage layer provide?

### Operations

- **Deployment.** How the system is deployed, configured, and updated.
- **Observability.** Metrics, logs, traces. What does the operator need
  to see?
- **Scaling.** How the system handles increased load.
- **Disaster recovery.** Backup, restore, and failover procedures.

### Security

- **Threat model.** Attacker capabilities, protected assets, trust
  boundaries.
- **Authentication and authorization.** How identity is established and
  permissions are enforced.
- **Secrets management.** How credentials and keys are stored and
  rotated.

### Testing and verification

- **Testing strategy.** Unit, integration, end-to-end, and property-
  based testing approaches.
- **Verification targets.** What properties must hold? How are they
  verified?
- **Acceptance criteria.** What must be true for the design to be
  considered implemented?

### Roadmap and phasing

- **MVP scope.** What ships first? This section belongs in the design
  document only if it defines the boundary between "designed now" and
  "designed later". Otherwise, it belongs in a separate roadmap.
- **Implementation priorities.** High, medium, low — with rationale.
- **Deferred decisions.** Design choices explicitly left open, with
  criteria for when they must be resolved.

### Appendices

- **Glossary.** (If not placed earlier.)
- **Acronyms table.**
- **References.** All cited sources with URLs and access dates.

## Structural rules

1. **Sections have one job.** If a section serves two purposes, split
   it. If two sections serve the same purpose, merge them.

2. **Dependency order.** A section should not reference concepts that
   have not yet been defined. If forward references are unavoidable,
   flag them explicitly.

3. **Depth is earned.** Level-4 headings (####) are a signal that the
   document may be too granular. Prefer flatter structures. If a
   section genuinely needs sub-sub-sections, it may warrant its own
   companion document.

4. **Tables over prose for structured data.** Stakeholder mappings,
   configuration parameters, error codes, comparison matrices — these
   are tables, not paragraphs.

5. **Code blocks are artefacts.** A code block longer than ~20 lines
   should have been an external artefact that was validated before
   incorporation. Short inline examples are fine.

6. **Diagrams are numbered and captioned.** "Figure N: description."
   This enables cross-referencing.

## Length guidance

There is no target length. A design document is as long as the design
requires and no longer. The editing pass enforces this. That said:

- A CLI tool design (like Splitters): 2,000–5,000 words.
- A service or platform design (like Episodic): 5,000–15,000 words.
- A complex multi-component system (like Corbusier): 10,000–30,000
  words, likely with companion documents.
- A security-focused design (like Zamburak): varies, but the threat
  model and verification sections will be proportionally larger.
