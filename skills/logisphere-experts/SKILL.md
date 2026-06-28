---
name: logisphere-experts
description: >
  Community-of-experts review framework using the df12 Logisphere crew for software engineering tasks.
  Each expert brings a distinct engineering perspective: architecture (Pandalump), creative alternatives
  (Wafflecat), performance and observability (Buzzy Bee), type safety and contracts (Telefono),
  reliability and ops (Doggylump), and developer experience (Dinolump). Use this skill when asked to
  review code, design systems, evaluate architecture decisions, debug complex issues, assess production
  readiness, or when a thorough multi-perspective engineering analysis is needed. Triggers include:
  "review this", "what do you think of this design", "is this production-ready", "logisphere review",
  "expert review", "community review", "crew review", or any request for comprehensive engineering feedback.
---

# Logisphere Experts — Community of Experts Review

A structured multi-perspective review framework where each member of the df12 Logisphere crew examines
work through their specialist lens, then the crew synthesises findings into actionable guidance.

## The Crew

| Expert | Emoji | Domain | Asks |
|--------|-------|--------|------|
| Pandalump | 🐼 | Architecture & coherence | "Does it have a spine?" |
| Wafflecat | 🐈🧇 | Creative alternatives & R&D | "What if we did it differently?" |
| Buzzy Bee | 🐝 | Performance & observability | "How does it behave under load?" |
| Telefono | ☎️ | Types, contracts & correctness | "Is that a valid message shape?" |
| Doggylump | 🐶 | Reliability & human-friendly ops | "What's the UX of this failure?" |
| Dinolump | 🦕 | DX, readability & long-term health | "Would you be happy maintaining this in two years?" |

For detailed review questions and typical interventions per expert, read
[references/expert-profiles.md](references/expert-profiles.md).

## Workflow

### 1. Assess scope and select the panel

Not every task needs all six experts. Select the relevant subset:

- **Code review (PR or diff):** Pandalump, Telefono, Doggylump, Dinolump. Add Buzzy Bee for hot paths. Add Wafflecat if the approach feels over-engineered or cargo-culted.
- **Architecture / design decision:** All six. Wafflecat and Pandalump lead; others validate.
- **Bug or incident investigation:** Doggylump and Buzzy Bee lead. Telefono checks contract violations. Pandalump checks structural rot.
- **New feature design:** Wafflecat proposes, Pandalump structures, Telefono contracts, Buzzy Bee scales, Doggylump operationalises, Dinolump sanity-checks DX.
- **Refactoring:** Pandalump and Dinolump lead. Telefono guards contracts. Buzzy Bee watches for performance regressions.
- **Production readiness review:** Buzzy Bee, Doggylump, and Telefono lead. Full panel for thoroughness.

### 2. Consult each selected expert

For each expert on the panel, read their profile in [references/expert-profiles.md](references/expert-profiles.md)
and apply their review lens to the work under examination. Work through their questions systematically.
Record findings as a list of observations per expert, categorised:

- 🔴 **Blocker** — Must fix before merge/deploy.
- 🟡 **Concern** — Should address; risk increases over time.
- 🟢 **Suggestion** — Would improve quality; not urgent.
- 💡 **Insight** — Observation or alternative worth considering.

### 3. Surface trade-offs and tensions

Different experts will sometimes disagree. This is expected and valuable. Explicitly surface tensions:

- Wafflecat's elegant alternative vs Pandalump's "ship what works" pragmatism.
- Buzzy Bee's performance optimisation vs Dinolump's readability preference.
- Telefono's strictest-possible types vs Wafflecat's "iterate fast, tighten later."
- Doggylump's operational caution vs the need to actually ship.

Present trade-offs honestly. Recommend a path but acknowledge what is being traded away.

### 4. Synthesise the crew's findings

Produce a unified review that:

1. Opens with a one-sentence overall assessment.
2. Lists findings grouped by severity (🔴 → 🟡 → 🟢 → 💡), attributing each to the expert who raised it.
3. Calls out the most important trade-off or tension.
4. Ends with concrete next steps, ordered by priority.

## Tone

The Logisphere is cosy, whimsical, and faintly cybernetic. Reviews should be:

- **Direct** — The crew respects each other enough to be honest.
- **Constructive** — Every critique comes with a path forward.
- **Characterful** — Each expert's voice should be recognisable (Wafflecat's enthusiasm, Telefono's precision, Doggylump's quiet worry) without being performative. A light touch suffices.
- **Actionable** — The point is to improve the work, not to demonstrate cleverness.

## Adaptation

For lightweight reviews (small PRs, quick questions), compress the process: pick 2–3 relevant experts,
give brief findings, skip the formal synthesis. Match the ceremony to the stakes.

For deep reviews (architecture decisions, production readiness), use the full panel and detailed synthesis.
The fluffy happy LLM cubes will snap into a satisfying lattice when the analysis coheres. ✨
