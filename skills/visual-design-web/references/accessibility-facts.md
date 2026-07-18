# Accessibility facts

Hard numbers and concrete requirements. No vibes. These are design
constraints that function as compositional tools.

---

## Contents

1. Text contrast
2. Non-text contrast
3. Focus visibility
4. Target size
5. Text spacing resilience
6. Motion
7. Images and alt strategy
8. Headings and structure
9. Link text and labels
10. Colour independence
11. Language and literalness
12. Scan behaviour and attention

---

## 1. Text contrast

**WCAG 2.2 minimum (AA):**
- Normal text (under 18pt / 24px, or under 14pt / 18.5px bold):
  **4.5:1** contrast ratio against background.
- Large text (18pt+ / 24px+, or 14pt+ / 18.5px+ bold): **3:1**
  contrast ratio.

**WCAG 2.2 enhanced (AAA):**
- Normal text: **7:1**.
- Large text: **4.5:1**.

**Design implication:** Light grey text on white backgrounds routinely
fails. Pastel palettes need dark enough foregrounds. Test every
text/background combination, including text over images and gradients —
if the image shifts, the contrast may break.

**Placeholder text** in form fields is not exempt. If a placeholder
carries meaningful information, it needs 4.5:1 contrast. Better: use
visible labels and reserve placeholders for example formatting only.

---

## 2. Non-text contrast

**WCAG 2.2 (AA):** Visual information needed to identify UI components
and their states, and graphical objects needed to understand the content,
require **3:1** contrast against adjacent colours.

**What counts:**
- Button borders and fill against the page background.
- Form field borders against the page background.
- Focus indicators against the background (see §3).
- Icon foreground against icon background.
- Chart segments against adjacent segments and background.
- Custom checkboxes, radio buttons, toggles, sliders.

**What doesn't count:** Inactive controls, purely decorative graphics,
and elements where appearance is determined by the user agent and not
modified by the author.

**Design implication:** Ghost buttons (text-only, no border) can fail if
the text contrast relies on being recognised as a button through shape
alone. Ensure at least the border or fill meets 3:1.

---

## 3. Focus visibility

**WCAG 2.2 (AA) — Focus Appearance (2.4.11):**
- The focus indicator must have an area of at least **2 CSS pixels**
  of thickness around the component's perimeter.
- The focus indicator must have **3:1** contrast between its focused and
  unfocused states.
- The indicator must not be entirely hidden by author-created content.

**WCAG 2.2 (AAA) — Enhanced Focus Appearance (2.4.12):**
- At least **2 CSS pixels** thick.
- **3:1** contrast against the unfocused state AND against adjacent
  colours.

**Design implication:** `outline: none` without a visible replacement is
not acceptable. The focus ring is a navigation tool — style it
deliberately, make it part of the visual language, do not suppress it.
Custom focus styles (offset outlines, box shadows, colour shifts) are
welcome as long as they meet the numbers.

**Material Design note:** Material recommends generous, high-contrast
focus indicators that integrate with the component's visual rhythm.
This is compatible with WCAG and tends to produce better visual results
than default browser outlines.

---

## 4. Target size

**WCAG 2.2 (AA) — Target Size Minimum (2.5.8):**
- Interactive targets must be at least **24 × 24 CSS pixels**, OR have
  sufficient spacing so that the target plus spacing reaches 24px.

**WCAG 2.2 (AAA) — Target Size Enhanced (2.5.5):**
- At least **44 × 44 CSS pixels**.

**Material Design 3 recommendation:**
- **48 × 48 dp** minimum touch target, regardless of visual size.
  The touch area may extend beyond the visible element.

**Exceptions:** Inline links within body text, targets whose size is
determined by the user agent, and targets where a specific presentation
is essential.

**Design implication:** Small icon buttons (close, favourite, share) are
frequent offenders. Even if the visible icon is 16px, the clickable
area must reach 24px minimum. Plan spacing accordingly. In dense
interfaces (dashboards, data tables), the 24px minimum demands careful
density management.

---

## 5. Text spacing resilience

**WCAG 2.2 (AA) — Text Spacing (1.4.12):**
Content must remain readable and functional when the user overrides:
- Line height to 1.5× the font size.
- Paragraph spacing to 2× the font size.
- Letter spacing to 0.12× the font size.
- Word spacing to 0.16× the font size.

**Design implication:** Fixed-height containers that clip text when
spacing increases are failures. Design containers to grow with content.
Avoid setting `overflow: hidden` on text containers. Test the design
with these overrides applied — tools like the WCAG Text Spacing
Bookmarklet make this easy.

---

## 6. Motion

**WCAG 2.2 (AA) — Motion Actuation (2.5.4):**
Any functionality triggered by device motion (shaking, tilting) must
have a UI alternative and the ability to disable motion response.

**WCAG 2.2 (AAA) — Animation from Interactions (2.3.3):**
Motion animation triggered by interaction can be disabled, unless
the animation is essential to the functionality or information.

**`prefers-reduced-motion` media query:**
- When `reduce` is set, all non-essential animation should stop or be
  replaced with an instantaneous state change.
- "Non-essential" = animation that does not convey information necessary
  to understand the content.
- Loading spinners, progress bars, and state-change indicators may
  persist in reduced form (e.g., a pulsing dot instead of a sweeping
  animation).

**Design implication:** Motion is a design tool, not a toggle. Plan two
design paths: the motion-rich path and the reduced-motion path. The
reduced-motion path must still be a complete, dignified experience — not
the "boring version". If the only way to understand the page is through
animation, the page has a content problem.

**Auto-playing content:** Moving, blinking, or scrolling content that
starts automatically, lasts more than 5 seconds, and is presented
alongside other content must have a mechanism to pause, stop, or hide
it (WCAG 2.2.2). Auto-playing carousels, background videos, and
marquees fall under this rule.

---

## 7. Images and alt strategy

**Image purpose taxonomy (W3C WAI):**

| Purpose | Alt strategy | Example |
|---|---|---|
| **Informative** | Short, accurate description of the information the image conveys. | A photograph of a building showing its architectural features. |
| **Decorative** | Empty alt (`alt=""`). The image adds atmosphere but carries no information. | A gradient wash behind a heading. |
| **Functional** | Alt describes the function, not the image. | A magnifying glass icon on a search button → `alt="Search"`. |
| **Complex** | Short alt plus a longer text description nearby or linked. | A chart → short alt summarising the finding, plus a data table. |
| **Images of text** | Avoid. If unavoidable, the alt must contain the full text. | A logo rendered as an image → `alt="Acme Corp"`. |

**GOV.UK distinction:**
- **Photography** for lifelike representation — when the user needs to
  see the real thing (a person, a place, a product).
- **Illustration** for simplification — when the image explains a
  concept, process, or relationship that is easier to grasp visually
  than verbally.

**Design implication:** Every image must earn its place. Ask: "Does this
image explain, orient, reassure, or intensify meaning?" If the answer is
"it fills space" or "it looks nice," it is decorative — mark it as such
and question whether it is worth the payload.

**Text in images:** Do not bake text into images unless the visual
presentation of the text is itself essential (e.g., a logo). Text in
images cannot be resized, reflowed, translated, or read by assistive
technology. Hero images with overlaid display text should use real HTML
text over a background image, not flattened composites.

---

## 8. Headings and structure

**WCAG requirement:** Headings describe the topic or purpose of the
content they introduce. Heading levels must reflect the structural
hierarchy of the content (h1 → h2 → h3, not skipping levels for visual
sizing).

**Design implication:** Visual heading hierarchy and semantic heading
hierarchy must align. If a design makes an h3 visually louder than an
h2, the semantic structure and the visual hierarchy contradict each
other, confusing both sighted and screen-reader users.

**Headings as navigation:** Screen-reader users navigate by headings.
Every major section should have one. Headings should be descriptive
enough to make sense out of context — "Our approach" is weaker than
"How we test every build."

**Landmarks:** Use HTML5 landmarks (`<header>`, `<nav>`, `<main>`,
`<aside>`, `<footer>`) to provide structural navigation. Visual design
should reinforce these boundaries.

---

## 9. Link text and labels

**WCAG requirement:** The purpose of each link can be determined from
the link text alone, or from the link text together with its
programmatically determined context.

**Design implication:** "Read more", "Click here", and "Learn more" are
weak scent. They force the user to read surrounding context to
understand the link's destination. Better: "Read the full accessibility
audit" or "Compare pricing plans."

**Instruction text and labels:** Form labels must be visible and
associated with their fields. Instructions for completing a form should
appear before the form or at the point of need, not only in a separate
help section.

---

## 10. Colour independence

**WCAG requirement:** Colour must not be the sole means of conveying
information, indicating action, prompting response, or distinguishing
visual elements.

**Common failures:**
- "Required fields are marked in red" (without a symbol).
- Chart segments distinguished only by hue.
- Link text distinguished from body text only by colour (without
  underline or other visual treatment).
- Error states indicated only by a colour change (without an icon or
  text message).

**Design implication:** Every colour-coded element needs a redundant
cue: shape, pattern, icon, text label, or position. Design in greyscale
first to verify the information structure holds without colour.

---

## 11. Language and literalness

**WCAG guidance:** Use the clearest, simplest language appropriate for
the content. Provide explanations for unusual words, phrases, jargon,
and abbreviations.

**Design implication for high-stakes content:** Where mistakes have real
consequences — forms, transactions, legal agreements, medical
information, error messages — use literal language. Clever wordplay,
metaphor, and brand voice should yield to clarity. "Your payment could
not be processed" is better than "Oops! Something went wrong."

Error messages should identify the error, explain what went wrong in
plain terms, and suggest how to fix it. Do not blame the user. Do not
use technical codes without explanation.

---

## 12. Scan behaviour and attention

These are research findings, not WCAG requirements, but they ground the
skill's hierarchy and scan-path guidance.

**F-pattern (Nielsen Norman Group):** Users scan web pages in an
F-shaped pattern — two horizontal stripes across the top, then a
vertical stripe down the left side. Content placed outside these zones
receives less attention.

**Layer-cake scanning:** Users scan headings and subheadings to build a
mental model of the page before committing to read any section. Strong
headings act as a table of contents for sighted users.

**Information scent (Pirolli & Card):** Users follow links and cues that
seem most likely to lead toward their goal. Strong scent = clear,
specific labels. Weak scent = vague labels, hidden navigation, generic
link text.

**First-impression formation:** Users form judgements about page
credibility and relevance within 50 milliseconds. Visual hierarchy,
apparent professionalism, and content relevance all contribute. This is
not vanity — it is the threshold that determines whether the user stays
to read.

**The aesthetic-usability effect (Kurosu & Kashimura, confirmed by
Tractinsky et al.):** Attractive interfaces are perceived as more usable
than they are. This cuts both ways: beauty can buy patience for minor
issues, but it can also mask serious usability problems. The skill uses
this finding as a warning: always test behaviour, not just preference.
