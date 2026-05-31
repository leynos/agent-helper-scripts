# Craft in Action

<!-- markdownlint-disable MD013 -->

This shows how the subtle layering principle translates to real decisions.
Learn the thinking, not the code. The values will differ — the approach won't.

______________________________________________________________________

## The Subtle Layering Mindset

Before looking at any example, internalize this: **the system should be barely
noticeable.**

When looking at Vercel's dashboard, the viewer does not think "nice borders."
The structure is understood implicitly. When looking at Supabase, the viewer
does not think "good surface elevation." Layering is understood without
explanation. The craft is invisible — that is how craft is known to be working.

______________________________________________________________________

## Example: Dashboard with Sidebar and Dropdown

### The Surface Decisions

**Why so subtle?** Each elevation jump should be only a few percentage points
of lightness. The difference is barely visible in isolation. But when surfaces
stack, the hierarchy emerges. This is the Vercel/Supabase way — whisper-quiet
shifts that the viewer feels rather than sees.

**What NOT to do:** Don't make dramatic jumps between elevations. That's
jarring. Don't use different hues for different levels. Keep the same hue,
shift only lightness.

### The Border Decisions

**Why rgba, not solid colours?** Low opacity borders blend with their
background. A low-opacity white border on a dark surface is barely there — it
defines the edge without demanding attention. Solid hex borders look harsh in
comparison.

**The test:** Look at the interface from arm's length. If borders are the first
visible element, reduce opacity. If region boundaries cannot be found, increase
slightly.

### The Sidebar Decision

**Why same background as canvas, not different?**

Many dashboards make the sidebar a different colour. This fragments the visual
space into "sidebar world" and "content world."

Better: Same background, subtle border separation. The sidebar is part of the
app, not a separate region. Vercel does this. Supabase does this. The border is
enough.

### The Dropdown Decision

**Why surface-200, not surface-100?**

The dropdown floats above the card it emerged from. If both were surface-100,
the dropdown would blend into the card — the design would lose the sense of
layering. Surface-200 is just light enough to feel "above" without being
dramatically different.

**Why border-overlay instead of border-default?**

Overlays (dropdowns, popovers) often need slightly more definition because
they're floating in space. A touch more border opacity helps them feel
contained without being harsh.

______________________________________________________________________

## Example: Form Controls

### Input Background Decision

**Why darker, not lighter?**

Inputs are "inset" — they receive content, they don't project it. A slightly
darker background signals "type here" without needing heavy borders. This is
the alternative-background principle.

### Focus State Decision

**Why subtle focus states?**

Focus needs to be visible, but there is no need for a glowing ring or dramatic
colour. A noticeable increase in border opacity is enough for a clear state
change. Subtle-but-noticeable — the same principle as surfaces.

______________________________________________________________________

## Adapt to Context

The product might need:

- Warmer hues (slight yellow/orange tint)
- Cooler hues (blue-grey base)
- Different lightness progression
- Light mode (principles invert — higher elevation = shadow, not lightness)

**The principle is constant:** barely different, still distinguishable. The
values adapt to context.

______________________________________________________________________

## The Craft Check

Apply the squint test to the work:

1. Blur the view or step back from the work.
2. Is the hierarchical structure still apparent?
3. Is anything jumping out?
4. Can the reviewer tell where regions begin and end?

If hierarchy is visible and nothing is harsh — the subtle layering is working.
