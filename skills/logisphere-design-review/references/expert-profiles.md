# Logisphere Design Review — Expert Profiles

## Pandalump 🐼 — Structural Integrity

**Focus:** Decomposition, boundaries, dependency direction, naming, conceptual coherence.

Before code exists, Pandalump examines whether the proposed structure will survive contact with
reality — and whether the names and boundaries will still make sense six months from now.

**Design review questions:**

- Does the decomposition reflect real domain boundaries, or arbitrary technical ones?
- Can you explain the dependency direction in one sentence? Does it flow "downward" consistently?
- Are the proposed module/service boundaries drawn where change is most likely to occur?
- Do the names form a consistent vocabulary? Would a new team member build the right mental model from them alone?
- Is the level of granularity appropriate — neither a monolith in disguise nor a distributed monolith?
- Are there circular dependencies, hidden coupling, or shared mutable state lurking in the design?
- Which invariants must hold across the system? Are they enforceable at the architectural level?
- If this design were a building, where are the load-bearing walls? What can be renovated later without structural risk?

**Red flags:** God objects, unclear ownership boundaries, names that describe implementation rather than intent, abstraction layers justified by "we might need it later."

---

## Wafflecat 🐈🧇 — Alternative Futures

**Focus:** Unexplored design space, hidden assumptions, radical simplification, adjacent solutions.

This is Wafflecat's natural habitat. Before anyone writes a line of code, Wafflecat's job is to
make sure the team has actually explored the possibility space rather than anchoring on the first
plausible idea.

**Design review questions:**

- What alternatives were considered and why were they rejected? (If none: that's the first problem.)
- What are the three strongest assumptions in this design? What happens if each is wrong?
- Is there a simpler version that solves 80% of the problem with 20% of the complexity?
- What would this look like if we used a completely different paradigm (event-driven vs request/response, push vs pull, stateless vs stateful)?
- Is the design solving the problem as stated, or the problem as it actually exists?
- Where is the design over-specified? Which decisions can be deferred without risk?
- What prior art exists? Has someone solved a structurally similar problem in another domain?
- If we fast-forward two years, what's most likely to need changing? Does the design accommodate that?

**Red flags:** No alternatives considered, designing for requirements that don't exist yet, premature optimisation disguised as architecture, complexity justified by hypothetical future needs.

---

## Buzzy Bee 🐝 — Scaling Characteristics & Operational Cost

**Focus:** Load profiles, resource consumption, bottlenecks, capacity planning, cost modelling.

At design time, Buzzy Bee shifts from profiling to *predicting*. The question isn't "what's slow"
but "what will become the bottleneck, and at what scale?"

**Design review questions:**

- What are the expected load profiles (requests/sec, data volume, concurrent users)? At launch? In 12 months?
- Where are the stateful components, and how do they scale horizontally?
- What's the write/read ratio, and does the data storage strategy match it?
- Are there fan-out patterns (one event triggers N downstream operations)? What bounds N?
- What's the expected p50/p95/p99 latency for the critical path? Is the design consistent with those targets?
- Where will the cost concentrate (compute, storage, egress, third-party API calls)? Does the design allow cost control?
- Are there operations that could become unbounded (queries without pagination, batch jobs without size limits)?
- How does the system behave during a traffic spike — does it shed load gracefully or fall over?
- What needs caching, and what's the invalidation strategy?

**Red flags:** No load estimates, "we'll optimise later" without identifying what to optimise, synchronous chains longer than three hops, unbounded fan-out, no cost model.

---

## Telefono ☎️ — Contracts & Interface Design

**Focus:** API surface, data models, schema evolution, protocol design, integration contracts.

At design time, Telefono examines the *seams* — the places where components, services, or systems
meet. A good interface contract outlives the implementation behind it.

**Design review questions:**

- Can the API be described as a small set of well-defined operations, or is it a grab-bag?
- Are request/response shapes minimal? Does each field earn its place?
- How will the API evolve? Can fields be added without breaking existing consumers (additive changes)?
- What's the versioning strategy? How do old and new clients coexist during migration?
- Are error responses structured and specific enough for clients to act on programmatically?
- Is the data model normalised appropriately? Are there denormalisations, and are they justified?
- What are the trust boundaries? Where does validation occur?
- Are there implicit contracts (ordering guarantees, delivery semantics, consistency levels) that should be explicit?
- If two teams implemented against this spec independently, would the results be interoperable?

**Red flags:** Overloaded endpoints, stringly-typed interfaces, no versioning plan, error responses that are just HTTP status codes, implicit ordering assumptions, schemas that can't evolve without breaking changes.

---

## Doggylump 🐶 — Failure Modes & Operational Readiness

**Focus:** Failure scenarios, degradation paths, deployment strategy, day-two operations.

Before code exists is the cheapest time to design for failure. Doggylump runs the pre-mortem:
*assuming this system has failed, what went wrong?*

**Design review questions:**

- For each external dependency, what happens when it's unavailable for 5 minutes? For an hour?
- What are the blast radius boundaries? Can a failure in component A take down component B?
- How is the system deployed? Can it be rolled back in under five minutes?
- What does a partial outage look like to the end user? Is there a meaningful degraded mode?
- What data can be lost, and what absolutely cannot? Are the durability guarantees clear?
- How will the team know something is wrong before users report it (monitoring, alerting, health checks)?
- What are the most likely incident scenarios? Do runbooks exist for them (or can they be written from the design)?
- Is there a data migration path? What happens to in-flight requests during deployment?
- Can the system be debugged in production without SSH access to individual machines?

**Red flags:** No failure mode analysis, single points of failure, "we'll add monitoring later," no rollback plan, data migration hand-waved, blast radius unbounded.

---

## Dinolump 🦕 — Long-term Viability & Team Impact

**Focus:** Cognitive load, team topology alignment, technology choices, maintenance burden, knowledge distribution.

Dinolump asks the questions that only matter if you plan to still be running this system in a year.
Which, unless it's a throwaway prototype, you do.

**Design review questions:**

- How many concepts does a developer need to hold in their head to work on this system?
- Does the team have production experience with the proposed technology choices, or is this a learning exercise disguised as architecture?
- Is knowledge about critical components distributed across the team, or concentrated in one person?
- Does the service/component boundary match team boundaries (Conway's Law alignment)?
- What's the testing strategy at each level (unit, integration, contract, end-to-end)? Is it realistic given the team's capacity?
- How much operational toil will this design generate? Is there a path to reducing it over time?
- Are the technology choices mainstream enough that hiring and onboarding won't be a bottleneck?
- Does the design document itself (through naming, structure, and convention), or does it require extensive external documentation to understand?

**Red flags:** Résumé-driven architecture, bus factor of one, no testing strategy, team structure misaligned with system structure, exotic technology choices without operational experience.
