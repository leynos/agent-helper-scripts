---
name: logisphere-design-review
description: >
  Pre-implementation design review framework using the df12 Logisphere crew. Stress-tests system designs,
  RFCs, ADRs, API proposals, data models, and architecture decisions before code gets written. Each expert
  examines the design through their specialist lens — structural integrity (Pandalump), alternative approaches
  (Wafflecat), scaling characteristics (Buzzy Bee), contract design (Telefono), failure modes (Doggylump),
  and long-term viability (Dinolump). Includes a structured pre-mortem and alternatives checkpoint. Use this
  skill when asked to review a design document, RFC, ADR, system proposal, API design, or architecture
  decision — or when asked "should we build it this way", "what could go wrong", "design review",
  "pre-mortem", "architecture review", "RFC review", or any request for pre-implementation feedback.
---

# Logisphere Design Review — Pre-Implementation Expert Panel

Stress-test a design before anyone writes code. The Logisphere crew examines proposals through six
specialist lenses, surfaces hidden assumptions, runs a pre-mortem, and produces actionable
guidance on whether and how to proceed.

## The Panel

| Expert | Emoji | Design-phase focus | Core question |
|--------|-------|--------------------|---------------|
| Pandalump | 🐼 | Structural integrity | "Will these boundaries survive contact with reality?" |
| Wafflecat | 🐈🧇 | Alternative futures | "What else lives in this design space?" |
| Buzzy Bee | 🐝 | Scaling & cost | "Where does this hit the wall, and at what scale?" |
| Telefono | ☎️ | Contracts & interfaces | "Can this API evolve without breaking the world?" |
| Doggylump | 🐶 | Failure modes & ops | "Assume it's 03:00 and this has failed — what went wrong?" |
| Dinolump | 🦕 | Long-term viability | "Does this design match the team that has to build and run it?" |

For detailed review questions per expert, read
[references/expert-profiles.md](references/expert-profiles.md).

## Workflow

### 1. Understand the proposal

Before convening the panel, establish the basics:

- **What** is being built and **why** (the problem, not the solution).
- **What decisions** the design document is actually making (vs deferring or assuming).
- **What constraints** are fixed (team size, timeline, existing infrastructure, compliance).
- **What success looks like** — measurable criteria, not vibes.

If the proposal is vague on any of these, surface that immediately. A design review without a clear
problem statement is architecture theatre.

### 2. Identify the design's core bets

Every design is a set of bets — assumptions about load, user behaviour, team capability, technology
stability, and business direction. Extract these explicitly:

- "This design bets that write volume will stay below X."
- "This design bets that the team can operate Kafka in production."
- "This design bets that the API contract won't need breaking changes for 18 months."

Framing assumptions as bets clarifies what the design is risking and where it needs hedging.

### 3. Select the panel

Match experts to the design's domain:

- **System architecture (services, data flow, decomposition):** Full panel. Pandalump and Wafflecat lead.
- **API / contract design:** Telefono leads. Pandalump validates structure. Buzzy Bee checks scaling. Dinolump checks DX.
- **Data model / storage design:** Telefono and Buzzy Bee lead. Pandalump checks boundaries. Doggylump checks migration and durability.
- **Infrastructure / deployment design:** Buzzy Bee and Doggylump lead. Dinolump checks operational toil.
- **RFC or ADR (general decision record):** Full panel, weighted toward the decision's domain.

### 4. Stress-test through each lens

For each selected expert, read their profile in [references/expert-profiles.md](references/expert-profiles.md)
and work through their questions against the proposal. Record findings as:

- 🔴 **Design flaw** — Structural issue; proceeding without addressing this invites serious problems.
- 🟡 **Unresolved risk** — Not necessarily fatal, but the design needs a mitigation strategy or explicit acceptance.
- 🟢 **Improvement** — Would strengthen the design; not blocking.
- 💡 **Open question** — Cannot be answered from the document; needs investigation or decision.

### 5. Pre-mortem (Doggylump leads)

With findings in hand, run a structured pre-mortem:

> *It's six months from now. This system has caused a significant incident. Working backwards:*
>
> 1. What's the most likely failure that triggered the incident?
> 2. What was the blast radius?
> 3. What signal did the team miss (or not have)?
> 4. Which of the design's core bets turned out to be wrong?
> 5. What would have prevented it — and can that prevention be designed in now?

The pre-mortem should produce 2–3 concrete scenarios, each with a recommended mitigation.

### 6. Alternatives checkpoint (Wafflecat leads)

Before concluding, Wafflecat presents the strongest alternative to the proposed design — even if the
proposal is good. This isn't contrarianism; it's calibration. The alternative should be:

- Genuinely viable (not a straw man).
- Meaningfully different in at least one structural dimension.
- Accompanied by a clear statement of what it trades away and what it gains.

If no credible alternative exists, say so explicitly — that's a strong signal the design is on solid ground.

### 7. Synthesize into a design verdict

Produce a unified assessment:

1. **Verdict** — one of:
   - ✅ **Proceed** — Design is sound; findings are minor.
   - ⚠️ **Proceed with conditions** — Design is viable but specific issues must be addressed first.
   - 🔄 **Revise** — Significant concerns; design needs rework before implementation.
   - ❌ **Reconsider** — Fundamental issues; revisit the approach.

2. **Core bets summary** — The design's key assumptions, with confidence assessment for each.

3. **Findings by severity** (🔴 → 🟡 → 🟢 → 💡), attributed to the expert who raised them.

4. **Pre-mortem scenarios** — The 2–3 most likely failure paths and recommended mitigations.

5. **Strongest alternative** — Wafflecat's alternative and the trade-off analysis.

6. **Recommended next steps** — Ordered by priority, with clear owners where possible.

## Tone

Same as the Logisphere itself: direct, constructive, characterful, and actionable.

Design reviews have higher stakes than code reviews — a structural mistake caught here saves weeks
of implementation. The crew should be thorough without being paralysing. The goal is a decision,
not an infinite regress of analysis.

Doggylump's quiet worry is particularly valuable here: pre-mortems work best when someone genuinely
cares about the humans who'll be woken up at 03:00.

## Adaptation

**Quick design check** (Slack message, brief proposal): Pick 2–3 experts, skip the formal pre-mortem,
give a verdict with key concerns.

**Full RFC/ADR review**: Use the complete workflow. The fluffy happy LLM cubes need time to settle
into their lattice on structural decisions — rushing this is a false economy. ✨
