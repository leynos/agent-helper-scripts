---
name: visual-design-web
description: >
  Visual strategy, art direction, and design critique for websites. Use this
  skill whenever the user asks for visual direction, page design strategy,
  design critique, hierarchy planning, concept exploration, or art direction
  for any web page or site — including landing pages, service/transactional
  pages, dashboards, editorial layouts, portfolios, campaign pages, and
  design-system foundations. Also trigger when the user asks to evaluate an
  existing web design, generate concept territories, plan visual hierarchy,
  choose type/colour/image strategy, or review a design for accessibility
  and communication clarity. This skill produces design rationale, concept
  directions, hierarchy maps, system strategies, and review notes — not
  HTML/CSS code. If the user needs implementation, hand off to the
  frontend-design skill after the design direction is set.
---

# Visual design for the web

A skill for visual communication strategy, art direction, and design critique
on the web.

This skill treats graphic design as a communication discipline, not a
decorative layer. Its job: help people do something, not merely make screens
look expensive.

## Governing rule

Every page needs a thesis. Within five seconds, the visitor should grasp what
this is, whether it concerns them, what matters most, and what to do next. That
principle — grounded in first-impression research, visual hierarchy, scan
behaviour, and information scent — overrides aesthetic preference at every turn.

## What this skill produces

- Design rationale and creative direction (one paragraph to full brief)
- Concept territories (3–5 distinct art directions with communicative
  stance, design-school lens, and risk assessment)
- Annotated hierarchy maps and scan-path plans
- Type / colour / image / motion system strategies
- Page-type-specific guidance
- Accessibility and inclusion risk registers
- Testing plans
- Critique notes on existing designs

This skill does not produce HTML, CSS, or component code. If the user needs
implementation after direction-setting, suggest the frontend-design skill.

## Reference files — read before producing output

The skill uses progressive disclosure. The SKILL.md you are reading now is the
operational spine. Deeper material lives in reference files. Read the relevant
references before generating output.

| Reference                 | When to read                                                                                         | Path                                  |
| ------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------- |
| **Design-school lenses**  | Generating concept territories or choosing a communicative stance                                    | `references/design-schools.md`        |
| **Accessibility facts**   | Any output that touches colour, type, targets, motion, images, or structure                          | `references/accessibility-facts.md`   |
| **Page-type branches**    | Working on a specific page archetype (marketing, editorial, service, dashboard, portfolio)           | `references/page-type-branches.md`    |
| **Exercises and devices** | Running a specific exercise (page thesis card, 5-second prompt, hierarchy ladder, stress pass, etc.) | `references/exercises-and-devices.md` |
| **Maxims and heresies**   | Critiquing an existing design or reviewing a proposed direction                                      | `references/maxims-and-heresies.md`   |

______________________________________________________________________

## Workflow

Follow these phases in order. Skip phases only when the user explicitly narrows
the request (e.g. "just critique this screenshot" skips to phase 6).

### Phase 1 — Gather inputs

Before designing anything, establish:

1. **User need** — who is this for, what do they need, why? Use the
   GOV.UK framing: "As a _**, I need to**_, so that ___."
2. **Business or mission need** — what does the organisation need this
   page to accomplish?
3. **Page job** — one sentence: what is this page's job?
4. **Page archetype** — landing, article, product, service task,
   dashboard, gallery, campaign, archive, support, or other.
5. **Audience types** — likely exclusions, context of use, emotional
   temperature (rushed, anxious, browsing, comparing, learning, deciding,
   recovering from error).
6. **Content reality** — what text, proof, data, states, forms, and
   assets exist now? What is still vapour?
7. **Brand direction** — adjectives, anti-adjectives, cultural
   references, visual taboos.
8. **Constraints** — accessibility requirements, legal, performance
   budget, CMS limitations, multilingual needs, device skew. Large visual
   assets and sparse first screens are design decisions with user costs, not
   free glamour.

If the user provides incomplete inputs, ask for the gaps. Prioritise user need
and page job — without these, everything downstream is guesswork.

### Phase 2 — Build the page thesis

Distil the inputs into:

- **Page thesis card**: "This page helps _X_ do/understand _Y_ so that
  _Z_."
- **Five-second promise**: what must the user grasp within five seconds?
- **Trust cues**: what makes this page credible?
- **Primary action**: the single most important thing the user can do.
- **Secondary action**: the fallback or alternative.
- **Proof structure**: what evidence supports the thesis?

Treat headings, labels, link text, instructions, and error language as design
material — not copy that gets glued on after the moodboard.

### Phase 3 — Generate concept territories

Produce 3–5 distinct art directions. For each, specify:

1. **Communicative stance** — what message does the visual language send?
2. **Design-school lens** — which tradition does this borrow from, and
   why is it earned here? → Read `references/design-schools.md`
3. **Colour hypothesis** — dominant, accent, state, and brand roles.
4. **Type hypothesis** — display, body, hierarchy strategy.
5. **Image hypothesis** — photography, illustration, iconography, or
   none, and why.
6. **Motion hypothesis** — what motion teaches, confirms, or orients
   (not what jiggles).
7. **Conventions preserved** — which web conventions remain familiar, and
   which break deliberately (with justification).
8. **Risk note** — what could go wrong with this direction?

Aim for one dependable direction, one stretching, one slightly feral. Resist
the drift toward the safest corporate oatmeal.

### Phase 4 — Plan hierarchy and scan path

For the chosen (or shortlisted) direction:

- Map the first-screen reading order.
- Plan the first-scroll narrative: what changes after the hero region?
- Check that headings and layout support real scanning behaviour
  (F-pattern, layer-cake). → Read `references/accessibility-facts.md` for
  scan-behaviour notes.
- Confirm primary navigation remains discoverable. Hidden primary
  navigation is not welcome.
- Identify trust cues, scent trails, and the strongest-scent element
  (link, button, or heading).
- Build a hierarchy ladder: loudest to quietest element.

### Phase 5 — Define the system

Turn the chosen direction into rules for:

- **Type** — hierarchy, line height, readable density, line length,
  text-spacing resilience.
- **Colour** — roles (hierarchy, state, brand), minimum contrast (read
  the hard numbers in `references/accessibility-facts.md`).
- **Spacing and grid** — scale, grouping, density control.
- **Imagery** — purpose taxonomy (informative, decorative, functional,
  complex), alt strategy per category.
- **Illustration and iconography** — when each is appropriate.
- **Focus style** — visible, high-contrast, not dependent on colour
  alone.
- **Target size** — minimums for touch and pointer.
- **Motion** — what it teaches; reduced-motion fallback.

Then branch into the appropriate page-type flow. → Read
`references/page-type-branches.md`.

### Phase 6 — Critique and review

Whether reviewing a new direction or an existing design, apply:

1. The **page thesis test** — can a stranger state the thesis after five
   seconds?
2. The **hierarchy ladder** — does loudness match importance?
3. The **scan-path check** — do headings, layout, and scent support
   scanning?
4. The **stress pass** — grayscale, 200% zoom, keyboard-only, reduced
   motion. → Read `references/exercises-and-devices.md`.
5. The **accessibility risk register** — meaningful headings, alt text,
   focus visibility, non-text contrast, target size, motion, literal language
   in high-stakes areas. → Read `references/accessibility-facts.md`.
6. The **convention-break audit** — which conventions broke, and does
   the benefit outweigh the cost?
7. The **aesthetic-usability warning** — pretty can flatter a broken
   experience. The skill drags attention back to behaviour.
8. The **heresies check** — does the design commit any of the known
   antipatterns? → Read `references/maxims-and-heresies.md`.

### Phase 7 — Testing plan

Recommend specific evidence-gathering methods:

- **5-second test** — does the thesis land?
- **First-click test** — does the primary action attract the first
  click?
- **Preference test** — between concept territories.
- **Tree test** — for findability and navigation structure.
- **Explicit aesthetic-usability warning** — beauty may mask broken
  flows.

Then iterate. Revisit phases 3–6 as evidence arrives.

______________________________________________________________________

## Boundary with other skills

- **frontend-design** — this skill sets direction; frontend-design
  implements it. Suggest handoff when the user wants code.
- **df12-copy** — if writing copy for df12 Productions, use that skill
  for voice and style. This skill handles visual strategy only.

## Locale

Follow the user's language conventions. For df12 work, use British English with
Oxford spelling (organize, analyse, colour, centre).

## Source canon

These references anchor the skill's positions. Cite them when the user asks
"says who?":

- W3C WCAG 2.2, Quick Reference, and Understanding documents
- WAI practical guidance (writing, designing, images, layout)
- GOV.UK Design Principles and Design System
- Inclusive Design Principles (inclusivedesignprinciples.info)
- Material Design 3 (expressive systems, colour, typography)
- Nielsen Norman Group research (hierarchy, scanning, scent, testing)
