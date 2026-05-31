---
name: interface-design
description: "This skill is for interface design — dashboards, admin panels, apps, tools, and interactive products. NOT for marketing design (landing pages, marketing sites, campaigns)."
---

# Interface Design

<!-- markdownlint-disable MD013 MD025 -->

Build interface design with craft and consistency.

## Scope

**Use for:** Dashboards, admin panels, Software as a Service (SaaS) apps,
tools, settings pages, data interfaces.

**Not for:** Landing pages, marketing sites, campaigns. Redirect those to
`/frontend-design`.

______________________________________________________________________

# The Problem

The model will generate generic output. Model training has seen thousands of
dashboards. The patterns are strong.

The entire process below can be followed: explore the domain, name a signature,
state the intent, and still produce a template. Warm colours on cold
structures. Friendly fonts on generic layouts. A kitchen feel can still look
like every other app.

This happens because intent lives in prose, but code generation pulls from
patterns. The gap between them is where defaults win.

The process below helps. But process alone doesn't guarantee craft. Defaults
must be caught early.

______________________________________________________________________

# Where Defaults Hide

Defaults don't announce themselves. They disguise themselves as infrastructure
— the parts that feel like they just need to work, not be designed.

**Typography feels like a container.** Pick something readable, move on. But
typography isn't holding the design — it IS the design. The weight of a
headline, the personality of a label, the texture of a paragraph. These shape
how the product feels before anyone reads a word. A bakery management tool and
a trading terminal might both need "clean, readable type" — but the type that's
warm and handmade is not the type that's cold and precise. If the default
choice reaches for the usual font, design has defaulted.

**Navigation feels like scaffolding.** Build the sidebar, add the links, get to
the real work. But navigation isn't around the product — it IS the product.
Current location, possible destinations, what matters most. A page floating in
space is a component demo, not software. The navigation teaches people how to
think about the space they're in.

**Data feels like presentation.** Raw numbers are available, so numbers are
displayed. But a number on screen is not design. The question is: what does
this number mean to the person looking at it? What will they do with it? A
progress ring and a stacked label both show "3 of 10" — one tells a story, one
fills space. If the default choice reaches for number-on-label, design has
defaulted.

**Token names feel like implementation detail.** But the Cascading Style Sheets
(CSS) variables are design decisions. `--ink` and `--parchment` evoke a world.
`--grey-700` and `--surface-2` evoke a template. Someone reading only the
tokens should be able to guess what product this is.

The trap is thinking some decisions are creative and others are structural.
There are no structural decisions. Everything is design. The moment "why this?"
stops being asked is the moment defaults take over.

______________________________________________________________________

# Intent First

Before touching code, answer these explicitly for the requester.

**Who is this human?** Not "users." The actual person. Where are they when the
interface opens? What is on their mind? What happened 5 minutes ago, and what
action follows 5 minutes after? A teacher at 7am with coffee is not a developer
debugging at midnight is not a founder between investor meetings. Their world
shapes the interface.

**What must they accomplish?** Not "use the dashboard." The verb. Grade these
submissions. Find the broken deployment. Approve the payment. The answer
determines what leads, what follows, what hides.

**What should this feel like?** Say it in words that mean something. "Clean and
modern" means nothing — every artificial intelligence (AI) system says that.
Warm like a notebook? Cold like a terminal? Dense like a trading floor? Calm
like a reading app? The answer shapes colour, type, spacing, density —
everything.

If the answers cannot be specific, stop. Ask the requester. Do not guess. Do
not default.

## Every Choice Must Be A Choice

For every decision, the designer must be able to explain WHY.

- Why this layout and not another?
- Why this colour temperature?
- Why this typeface?
- Why this spacing scale?
- Why this information hierarchy?

If the answer is "it's common" or "it's clean" or "it works" — no choice has
been made. Defaulting has happened. Defaults are invisible. Invisible choices
compound into generic output.

**The test:** If the chosen details were swapped for the most common
alternatives and the design didn't feel meaningfully different, real choices
were never made.

## Sameness Is Failure

If another AI, given a similar prompt, would produce substantially the same
output — the result has failed.

This is not about being different for its own sake. It's about the interface
emerging from the specific problem, the specific user, the specific context.
When design proceeds from intent, sameness becomes impossible because no two
intents are identical.

When design proceeds from defaults, everything looks the same because defaults
are shared.

## Intent Must Be Systemic

Saying "warm" and using cold colours is not following through. Intent is not a
label — it's a constraint that shapes every decision.

If the intent is warm: surfaces, text, borders, accents, semantic colours,
typography — all warm. If the intent is dense: spacing, type size, information
architecture — all dense. If the intent is calm: motion, contrast, colour
saturation — all calm.

Check the output against the stated intent. Does every token reinforce it? Or
was an intent stated before defaulting anyway?

______________________________________________________________________

# Product Domain Exploration

This is where defaults get caught — or don't.

Generic output: Task type → Visual template → Theme Crafted output: Task type →
Product domain → Signature → Structure + Expression

The difference: time in the product's world before any visual or structural
thinking.

## Required Outputs

**Do not propose any direction until the process produces all four:**

**Domain:** Concepts, metaphors, vocabulary from this product's world. Not
features — territory. Minimum 5.

**Colour world:** What colours exist naturally in this product's domain? Not
"warm" or "cool" — go to the actual world. If this product were a physical
space, what would be visible? What colours belong there that don't belong
elsewhere? List 5+.

**Signature:** One element — visual, structural, or interaction — that could
only exist for THIS product. If one cannot be named, keep exploring.

**Defaults:** 3 obvious choices for this interface type — visual AND
structural. Patterns cannot be avoided until they have been named.

## Proposal Requirements

The direction must explicitly reference:

- Explored domain concepts
- Colours from the colour world exploration
- The signature element
- What replaces each default

**The test:** Read the proposal. Remove the product name. Could a reviewer
identify what this is for? If not, it's generic. Explore deeper.

______________________________________________________________________

# The Mandate

**Before showing the requester, review the output.**

Ask: "If the requester said this lacks craft, what would that mean?"

That critique — fix it first.

The first output is probably generic. That's normal. The work is catching it
before the requester has to.

## The Checks

Run these against the output before presenting:

- **The swap test:** If the typeface were swapped for the usual one, would
  anyone notice? If the layout were swapped for a standard dashboard template,
  would it feel different? The places where swapping would not matter are the
  places where defaulting occurred.

- **The squint test:** Blur the view. Can the structure and hierarchy still be
  perceived? Is anything jumping out harshly? Craft whispers.

- **The signature test:** Can the reviewer point to five specific elements
  where the signature appears? Not "the overall feel" — actual components. A
  signature that cannot be located doesn't exist.

- **The token test:** Read the CSS variables out loud. Do those variables sound
  like they belong to this product's world, or could they belong to any project?

If any check fails, iterate before showing.

______________________________________________________________________

# Craft Foundations

## Subtle Layering

This is the backbone of craft. Regardless of direction, product type, or visual
style, this principle applies to everything. The system should be barely
noticeable when it is working. When looking at Vercel's dashboard, the viewer
does not think "nice borders." The structure is understood. The craft is
invisible; that is how craft signals that it is working.

### Surface Elevation

Surfaces stack. A dropdown sits above a card which sits above the page. Build a
numbered system — base, then increasing elevation levels. In dark mode, higher
elevation = slightly lighter. In light mode, higher elevation is slightly
lighter or uses shadow.

Each jump should be only a few percentage points of lightness. The difference
is barely visible in isolation. But when surfaces stack, the hierarchy emerges.
Whisper-quiet shifts are felt rather than seen.

**Key decisions:**

- **Sidebars:** Same background as canvas, not different. Different colours
  fragment the visual space into "sidebar world" and "content world." A subtle
  border is enough separation.
- **Dropdowns:** One level above their parent surface. If both share the same
  level, the dropdown blends into the card and layering is lost.
- **Inputs:** Slightly darker than their surroundings, not lighter. Inputs are
  "inset" — they receive content. A darker background signals "type here"
  without heavy borders.

### Borders

Borders should disappear when attention is elsewhere, but be findable when
structure is needed. Low opacity rgba blends with the background — it defines
edges without demanding attention. Solid hex borders look harsh in comparison.

Build a progression — not all borders are equal. Standard borders, softer
separation, emphasis borders, maximum emphasis for focus rings. Match intensity
to the importance of the boundary.

**The squint test:** Blur the view at the interface. Hierarchy should remain
perceptible — what's above what, where sections divide. But nothing should jump
out. No harsh lines. No jarring colour shifts. Just quiet structure.

This separates professional interfaces from amateur ones. Get this wrong and
nothing else matters.

## Infinite Expression

Every pattern has infinite expressions. **No interface should look the same.**

A metric display could be a hero number, inline stat, sparkline, gauge,
progress bar, comparison delta, trend badge, or something new. A dashboard
could emphasize density, whitespace, hierarchy, or flow in completely different
ways. Even sidebar + cards has infinite variations in proportion, spacing, and
emphasis.

**Before building, answer:**

- What is the ONE thing the primary person does most here?
- What products solve similar problems brilliantly? Study them.
- Why would this interface feel designed for its purpose, not templated?

**NEVER produce identical output.** Same sidebar width, same card grid, same
metric boxes with icon-left-number-big-label-small every time — this signals
AI-generated immediately. It's forgettable.

The architecture and components should emerge from the task and data, executed
in a way that feels fresh. Linear's cards don't look like Notion's. Vercel's
metrics don't look like Stripe's. Same concepts, infinite expressions.

## Colour Lives Somewhere

Every product exists in a world. That world has colours.

Before reaching for a palette, spend time in the product's world. What would be
visible in the physical version of this space? What materials? What light? What
objects?

The palette should feel like it came FROM somewhere — not like it was applied
TO something.

**Beyond Warm and Cold:** Temperature is one axis. Is this quiet or loud? Dense
or spacious? Serious or playful? Geometric or organic? A trading terminal and a
meditation app are both "focused" — completely different kinds of focus. Find
the specific quality, not the generic label.

**Colour Carries Meaning:** Grey builds structure. Colour communicates —
status, action, emphasis, identity. Unmotivated colour is noise. One accent
colour, used with intention, beats five colours used without thought.

______________________________________________________________________

# Before Writing Each Component

**Every time** user interface (UI) code is written — even small additions —
state:

```text
Intent: [who is this human, what must they do, how should it feel]
Palette: [colours from the exploration — and WHY they fit this product's world]
Depth: [borders / shadows / layered — and WHY this fits the intent]
Surfaces: [the elevation scale — and WHY this colour temperature]
Typography: [the typeface — and WHY it fits the intent]
Spacing: [the base unit]
```

This checkpoint is mandatory. It forces the designer to connect every technical
choice back to intent.

If the rationale cannot explain WHY for each choice, defaulting has happened.
Stop and think.

______________________________________________________________________

# Design Principles

## Token Architecture

Every colour in the interface should trace back to a small set of primitives:
foreground (text hierarchy), background (surface elevation), border (separation
hierarchy), brand, and semantic (destructive, warning, success). No random hex
values — everything maps to primitives.

### Text Hierarchy

Don't just have "text" and "grey text." Build four levels — primary, secondary,
tertiary, muted. Each serves a different role: default text, supporting text,
metadata, and disabled/placeholder. Use all four consistently. If only two are
used, the hierarchy is too flat.

### Border Progression

Borders aren't binary. Build a scale that matches intensity to importance —
standard separation, softer separation, emphasis, maximum emphasis. Not every
boundary deserves the same weight.

### Control Tokens

Form controls have specific needs. Don't reuse surface tokens — create
dedicated ones for control backgrounds, control borders, and focus states. This
lets designers tune interactive elements independently of layout surfaces.

## Spacing

Pick a base unit and stick to multiples. Build a scale for different contexts —
micro spacing for icon gaps, component spacing within buttons and cards,
section spacing between groups, major separation between distinct areas. Random
values signal no system.

## Padding

Keep it symmetrical. If one side has a value, others should match unless
content naturally requires asymmetry.

## Depth

Choose ONE approach and commit:

- **Borders-only** — Clean, technical. For dense tools.
- **Subtle shadows** — Soft lift. For approachable products.
- **Layered shadows** — Premium, dimensional. For cards that need presence.
- **Surface colour shifts** — Background tints establish hierarchy without
  shadows.

Don't mix approaches.

## Border Radius

Sharper feels technical. Rounder feels friendly. Build a scale — small for
inputs and buttons, medium for cards, large for modals. Don't mix sharp and
soft randomly.

## Typography

Build distinct levels distinguishable at a glance. Headlines need weight and
tight tracking for presence. Body needs comfortable weight for readability.
Labels need medium weight that works at smaller sizes. Data needs monospace
with tabular number spacing for alignment. Don't rely on size alone — combine
size, weight, and letter-spacing.

## Card Layouts

A metric card doesn't have to look like a plan card, and a plan card doesn't
have to look like a settings card. Design each card's internal structure for
its specific content —
but keep the surface treatment consistent: same border weight, shadow depth,
corner radius, padding scale.

## Controls

Native `<select>` and `<input type="date">` render operating system (OS)-native
elements that cannot be styled. Build custom components — trigger buttons with
positioned dropdowns, calendar popovers, styled state management.

## Iconography

Icons clarify, not decorate — if removing an icon loses no meaning, remove it.
Choose one icon set and stick with it. Give standalone icons presence with
subtle background containers.

## Animation

Fast micro-interactions, smooth easing. Larger transitions can be slightly
longer. Use deceleration easing. Avoid spring/bounce in professional interfaces.

## States

Every interactive element needs states: default, hover, active, focus,
disabled. Data needs states too: loading, empty, error. Missing states feel
broken.

## Navigation Context

Screens need grounding. A data table floating in space feels like a component
demo, not a product. Include navigation showing current location in the app,
location indicators, and user context. When building sidebars, consider the same
background as main content with border separation rather than different colours.

## Dark Mode

Dark interfaces have different needs. Shadows are less visible on dark
backgrounds — lean on borders for definition. Semantic colours (success,
warning, error) often need slight desaturation. The hierarchy system still
applies, just with inverted values.

______________________________________________________________________

# Avoid

- **Harsh borders** — if borders are the first visible element, they're too
  strong
- **Dramatic surface jumps** — elevation changes should be whisper-quiet
- **Inconsistent spacing** — the clearest sign of no system
- **Mixed depth strategies** — pick one approach and commit
- **Missing interaction states** — hover, focus, disabled, loading, error
- **Dramatic drop shadows** — shadows should be subtle, not attention-grabbing
- **Large radius on small elements**
- **Pure white cards on coloured backgrounds**
- **Thick decorative borders**
- **Gradients and colour for decoration** — colour should mean something
- **Multiple accent colours** — dilutes focus
- **Different hues for different surfaces** — keep the same hue, shift only
  lightness

______________________________________________________________________

# Workflow

## Communication

Be invisible. Don't announce modes or narrate process.

**Never say:** "ESTABLISH MODE is active", "Checking system.md…"

**Instead:** Jump into work. State suggestions with reasoning.

## Suggest + Ask

Lead with the exploration and recommendation, then confirm:

```text
"Domain: [5+ concepts from the product's world]
Colour world: [5+ colours that exist in this domain]
Signature: [one element unique to this product]
Rejecting: [default 1] → [alternative], [default 2] → [alternative], [default 3] → [alternative]

Direction: [approach that connects to the above]"

[Ask: "Does that direction feel right?"]
```

## If Project Has system.md

Read `.interface-design/system.md` and apply. Decisions are made.

## If No system.md

1. Explore domain — Produce all four required outputs
2. Propose — Direction must reference all four
3. Confirm — Get requester buy-in
4. Build — Apply principles
5. **Evaluate** — Run the mandate checks before showing
6. Offer to save

______________________________________________________________________

# After Completing a Task

After building something, **always offer to save**:

```text
"Should these patterns be saved for future sessions?"
```

If yes, write to `.interface-design/system.md`:

- Direction and feel
- Depth strategy (borders/shadows/layered)
- Spacing base unit
- Key component patterns

## What to Save

Add patterns when a component is used 2+ times, is reusable across the project,
or has specific measurements worth remembering. Don't save one-off components,
temporary experiments, or variations better handled with props.

## Consistency Checks

If system.md defines values, check against them: spacing on the defined grid,
depth using the declared strategy throughout, colours from the defined palette,
documented patterns reused instead of reinvented.

This compounds — each save makes future work faster and more consistent.

______________________________________________________________________

# Deep Dives

For more detail on specific topics:

- `references/principles.md` — Code examples, specific values, dark mode
- `references/validation.md` — Memory management, when to update system.md
- `references/critique.md` — Post-build craft critique protocol

# Commands

- `/interface-design:status` — Current system state
- `/interface-design:audit` — Check code against system
- `/interface-design:extract` — Extract patterns from code
- `/interface-design:critique` — Critique the build for craft, then rebuild
  what defaulted
