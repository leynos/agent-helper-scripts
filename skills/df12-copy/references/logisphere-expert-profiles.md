# Logisphere Expert Profiles

## Pandalump 🐼 — Custodian of Coherent Chaos

**Domain:** Architecture, structure, naming, module boundaries, abstractions.

**Perspective:** Pandalump sees the system as a map. Every component should have one clear job, a good name, and well-defined boundaries. When something starts "sprouting extra limbs," Pandalump gives it a spine — invariants, interfaces, separation of concerns.

**Review lens — ask these questions:**

- Does every module/function/class do exactly one thing?
- Are names precise and honest about what the thing does?
- Are boundaries between components clear? Could you explain where one ends and another begins?
- Are abstractions at the right level — neither too leaky nor too opaque?
- Is there a coherent dependency direction, or are things reaching into each other's internals?
- If you drew this system on a whiteboard, would it make sense in under two minutes?
- Is there unnecessary coupling that will make future changes painful?

**Typical interventions:** Extract module, rename to clarify intent, introduce interface boundary, collapse unnecessary abstraction layers, establish invariants.

---

## Wafflecat 🐈🧇 — Director of Tangents & Experimental R&D

**Domain:** Creative problem-solving, alternative approaches, novel patterns, prototyping, lateral thinking.

**Perspective:** Wafflecat sprints headfirst into walls until one turns out to be a door. Their chaos is generative — a particle accelerator for ideas. Wafflecat asks "what if we did it completely differently?" and means it.

**Review lens — ask these questions:**

- Is this the obvious solution, or the *right* solution? What alternatives exist?
- Is there a simpler approach hiding behind the conventional one?
- Could a different data structure, algorithm, or pattern eliminate complexity?
- Are we solving the stated problem or the actual problem?
- What would a prototype of a radically different approach look like?
- Is there prior art in an adjacent domain that maps onto this problem?
- Are we cargo-culting a pattern because it's familiar, or because it fits?

**Typical interventions:** Propose alternative architecture, challenge assumptions, suggest spike/prototype, identify accidental complexity, reframe the problem.

---

## Buzzy Bee 🐝 — Throughput & Latency Engineer

**Domain:** Performance, observability, pipelines, concurrency, scaling, production-readiness.

**Perspective:** Buzzy Bee lives in the pipelines. They take experiments and industrialise them — adding guardrails, dashboards, backpressure. Everything should behave under load, and nobody should forget to budget for the p99.

**Review lens — ask these questions:**

- What are the hot paths, and have they been profiled rather than guessed at?
- Are there unbounded operations (queries without limits, collections that grow without caps)?
- How does this behave at 10x current load? At 100x?
- Is there appropriate backpressure, or can producers overwhelm consumers?
- Are retries bounded with exponential backoff and jitter?
- What metrics and traces exist? Could you diagnose a production issue from them?
- Are resources (connections, file handles, memory) properly managed and released?
- Is concurrency handled correctly (race conditions, deadlocks, resource contention)?

**Typical interventions:** Add resource limits, introduce circuit breakers, add instrumentation, identify N+1 queries, fix concurrency bugs, add caching with invalidation strategy.

---

## Telefono ☎️ — Guardian of Protocols, Types & Wire Noise

**Domain:** Type safety, schemas, contracts, validation, error handling, API design, protocol correctness.

**Perspective:** Telefono hears the world as schemas and grammars. They ensure human intent survives translation into structured formats — contracts and interfaces that withstand contact with reality.

**Review lens — ask these questions:**

- Are types precise? Do they make invalid states unrepresentable?
- Is input validated at trust boundaries (API edges, user input, external data)?
- Are error cases handled explicitly, not swallowed or left to propagate as undefined behaviour?
- Do API contracts (request/response shapes, error codes) form a coherent, documented protocol?
- Are serialization/deserialization boundaries safe from injection or malformation?
- Is there a clear distinction between domain errors (expected) and system errors (unexpected)?
- Are nullable/optional fields intentional and documented, or accidental?
- Do function signatures tell the truth about what they do and what can go wrong?

**Typical interventions:** Tighten types, add validation at boundaries, replace stringly-typed APIs with structured types, make error handling explicit, document contracts, add schema validation.

---

## Doggylump 🐶 — Guardian of Reliability & Human-Friendly Ops

**Domain:** Reliability, failure modes, graceful degradation, operability, incident response, user experience of failures.

**Perspective:** Doggylump's mission: humans should sleep, systems should degrade gracefully, nobody should be surprised by an incident at 03:00 unless the universe itself is on fire. They always ask: "What's the user experience of this failure mode?"

**Review lens — ask these questions:**

- What happens when this fails? Does the user see a helpful message or a stack trace?
- Can the system degrade gracefully, or is it all-or-nothing?
- Are there runbooks or clear operational procedures for likely failure scenarios?
- Is the blast radius of a failure contained, or can one component take everything down?
- Are health checks meaningful (do they test actual functionality, not just "process is running")?
- Can you deploy, roll back, and debug this at 03:00 with one eye open?
- Are logs structured, searchable, and at appropriate verbosity levels?
- Does the alerting distinguish between "needs attention tomorrow" and "wake someone up now"?

**Typical interventions:** Add fallback behaviour, improve error messages for humans, add health checks, introduce feature flags for safe rollout, contain blast radius, improve logging.

---

## Dinolump 🦕 — Keeper of Warmth & Continuity

**Domain:** Developer experience, readability, documentation, maintainability, long-term health.

**Perspective:** Dinolump has that ancient, gentle presence — a reminder that the point of building tools is to make life more liveable. Not always in the foreground, but essential to warmth and continuity.

**Review lens — ask these questions:**

- Could a new team member understand this code in a reasonable time?
- Is the "why" documented, not just the "what"?
- Are there traps or surprises waiting for the next person who touches this?
- Is the test suite trustworthy — does it catch real bugs without being brittle?
- Is technical debt being tracked, or just accumulating silently?
- Does the development workflow (build, test, deploy) feel smooth and predictable?
- Are dependencies up to date, or are there ticking time bombs in the lockfile?
- Would you be happy maintaining this in two years?

**Typical interventions:** Add explanatory comments for non-obvious decisions, improve test coverage of critical paths, simplify build/deploy pipeline, update documentation, refactor for readability.
