# Exercises and devices

Reusable exercises, structured prompts, and evaluation tools. Use these during
concepting, hierarchy planning, review, and testing.

______________________________________________________________________

## Contents

1. Page thesis card
2. Five-second understanding prompt
3. Concept territory generator
4. Design-school remix exercise
5. Hierarchy ladder
6. First-scroll narrative
7. Image-purpose decision tree
8. Motion justification test
9. Convention-break justification
10. Stress pass (grayscale / zoom / keyboard / reduced motion)
11. First-click test prompt
12. Preference test prompt
13. Tree test prompt

______________________________________________________________________

## 1. Page thesis card

A forcing function for clarity. Complete this card before any visual work
begins.

```
PAGE THESIS CARD
────────────────────────────────────────────

Page URL or name:  ________________________________

This page helps:   ________________________________
                   (specific audience)

Do / understand:   ________________________________
                   (specific task or knowledge)

So that:           ________________________________
                   (outcome or benefit)

Five-second promise:
What must the user grasp within five seconds?
___________________________________________________

Primary action:
___________________________________________________

Secondary action:
___________________________________________________

Trust cues (what makes this credible?):
___________________________________________________

Proof structure (what evidence supports the thesis?):
___________________________________________________
```

**Usage:** Complete for every page or screen being designed. If the "this page
helps" sentence cannot be written concisely, the page is trying to do too many
things. Split or prioritize.

______________________________________________________________________

## 2. Five-second understanding prompt

Show the design (or a wireframe, or even a text description of the layout) for
five seconds, then remove it. Ask:

1. What is this page about?
2. Who is it for?
3. What is the most important thing on the page?
4. What would you do first?

**Evaluation criteria:**

- If the answers align with the page thesis card, the hierarchy is
  working.
- If users can name the topic but not the action, the CTA is too quiet.
- If users name a secondary element as "most important," the hierarchy
  needs rebalancing.
- If users cannot identify the topic at all, the thesis is buried.

______________________________________________________________________

## 3. Concept territory generator

For a given brief, generate three directions:

### Direction A — Dependable

The safest appropriate direction. Uses established patterns for this page type.
Minimizes risk. May lack distinctiveness.

- Communicative stance:
- Design-school lens:
- Colour hypothesis:
- Type hypothesis:
- Image hypothesis:
- Conventions preserved:
- Risk note:

### Direction B — Stretch

Pushes the visual language further. Takes a clear aesthetic position.
Introduces one or two unexpected elements while keeping core wayfinding
conventional.

- Communicative stance:
- Design-school lens:
- Colour hypothesis:
- Type hypothesis:
- Image hypothesis:
- Conventions preserved:
- Conventions broken (with justification):
- Risk note:

### Direction C — Feral

The provocative option. Borrows from a tradition the brief might not obviously
suggest. Maximizes memorability. May require user testing to validate.

- Communicative stance:
- Design-school lens:
- Colour hypothesis:
- Type hypothesis:
- Image hypothesis:
- Conventions preserved (bare minimum for usability):
- Conventions broken (with justification):
- Risk note:

**Usage:** Present all three. The final direction is often a hybrid, borrowing
the stance of one and the restraint of another. The purpose of the feral option
is to expand the solution space, not to be chosen intact.

______________________________________________________________________

## 4. Design-school remix exercise

Take the same page thesis. Apply three different design-school lenses (from
`references/design-schools.md`). For each, answer:

1. What visual language would this lens produce?
2. What message shifts compared to the other renderings?
3. What audience shifts?
4. What risks emerge?
5. Which web conventions feel natural to break under this lens?
6. Which conventions become even more essential to keep?

**Usage:** Prevents premature convergence. Useful when the team has locked onto
one direction too early, or when the "obvious" choice feels stale.

______________________________________________________________________

## 5. Hierarchy ladder

List every element on the page, then rank them from loudest to quietest.

```
HIERARCHY LADDER
────────────────────────────────────────────

Page: ________________________________

Rank  Element                 Visual volume   Should it be here?
──────────────────────────────────────────────────────────────────
1     ____________________    Loudest         Yes / No / Adjust
2     ____________________    ↑               Yes / No / Adjust
3     ____________________    |               Yes / No / Adjust
4     ____________________    |               Yes / No / Adjust
5     ____________________    |               Yes / No / Adjust
...   ____________________    ↓               Yes / No / Adjust
n     ____________________    Quietest        Yes / No / Adjust
```

**Evaluation criteria:**

- Does the loudest element match the page thesis?
- Is the primary action in the top three?
- Are any decorative elements louder than functional ones?
- Are there elements at equal volume that should be differentiated?

______________________________________________________________________

## 6. First-scroll narrative

Describe what happens as the user scrolls from the top of the page to the first
full viewport below the fold.

```
FIRST-SCROLL NARRATIVE
────────────────────────────────────────────

First screen (above fold):
What the user sees: ____________________________________
What the user understands: _____________________________
What the user can do: __________________________________

Transition zone:
What signals that there is more below? _________________

Second screen (first scroll):
What new information appears? __________________________
What changes in hierarchy or tone? _____________________
What action becomes available? _________________________

The question: Does the first screen give enough reason to scroll?
Answer: ________________________________________________
```

**Usage:** Catches the "cinematic hero slab" problem — a gorgeous first screen
that communicates nothing and gives no reason to continue. Also catches the
opposite problem: a first screen so dense that the user does not know where to
start.

______________________________________________________________________

## 7. Image-purpose decision tree

For each image in the design, answer these questions in order:

```
1. Does this image carry information the user needs?
   → YES: Go to 2.
   → NO: It is decorative. Use alt="". Consider whether it earns its
     payload cost.

2. Does the image perform a function (button, link, control)?
   → YES: Alt text describes the function, not the image.
     Example: Search icon → alt="Search"
   → NO: Go to 3.

3. Can the image's information be described in a short phrase?
   → YES: Use concise alt text describing what the image conveys,
     not what it depicts.
     Example: Photo of a queue → alt="Long waiting times at the
     service centre" (not "Photo of people standing in a line").
   → NO: Go to 4.

4. The image is complex (chart, diagram, map, infographic).
   → Provide a short alt text summarising the key finding.
   → Provide a longer text description nearby or linked.
   → If it is a data chart, provide the data in a table.

5. Is the image text rendered as an image?
   → If the visual presentation is essential (logo, brand mark): OK,
     but alt must contain the full text.
   → If the visual presentation is not essential: use real text instead.
```

______________________________________________________________________

## 8. Motion justification test

For every animated element, answer:

```
MOTION JUSTIFICATION
────────────────────────────────────────────

Element: ____________________________________

What does this motion TEACH?
(e.g., where the element came from, what just changed)
Answer: ________________________________________

What does this motion CONFIRM?
(e.g., the action succeeded, the state changed)
Answer: ________________________________________

What does this motion ORIENT?
(e.g., spatial relationships, navigation context)
Answer: ________________________________________

If none of the above: this motion is decorative.
Is it worth the performance and accessibility cost?
Answer: ________________________________________

Reduced-motion alternative:
What happens when prefers-reduced-motion is set?
Answer: ________________________________________
Is the reduced-motion experience still complete and dignified?
Answer: ________________________________________
```

______________________________________________________________________

## 9. Convention-break justification

When the design breaks a web convention (non-standard navigation, novel scroll
behaviour, unusual form patterns, unfamiliar interaction models):

```
CONVENTION-BREAK JUSTIFICATION
────────────────────────────────────────────

Convention broken: ____________________________________

What benefit does breaking it provide?
Answer: ________________________________________________

What cost does breaking it impose?
(Disorientation, learning curve, accessibility risk, discoverability
loss, increased error rate)
Answer: ________________________________________________

Does the benefit outweigh the cost for all audience segments?
Answer: ________________________________________________

What mitigation reduces the cost?
(Onboarding hint, fallback pattern, progressive enhancement)
Answer: ________________________________________________

Decision: BREAK / KEEP / BREAK WITH MITIGATION
```

______________________________________________________________________

## 10. Stress pass

A structured review that tests the design under constrained conditions. Run all
four checks on every design before finalizing.

### 10a. Greyscale pass

View the design with all colour removed (desaturate to 0%).

- Can you still distinguish all interactive elements?
- Can you still read the hierarchy?
- Do form states (default, focus, error, success) remain distinguishable?
- Do chart segments remain distinguishable?
- If anything disappears or becomes ambiguous, it relies on colour alone.

### 10b. Zoom pass

View the design at 200% browser zoom.

- Does all text remain readable?
- Do containers grow with content without clipping or overflow?
- Is horizontal scrolling required? (It should not be for most
  content.)
- Do interactive targets remain reachable and large enough?
- Does the layout reflow sensibly?

### 10c. Keyboard pass

Navigate the entire page using only keyboard (Tab, Shift+Tab, Enter, Space,
Arrow keys, Escape).

- Is a focus indicator visible on every interactive element?
- Does the focus order follow a logical reading sequence?
- Can every interactive element be activated?
- Are there any focus traps (modal dialogs that do not return focus,
  infinite tab loops)?
- Can skip-navigation links bypass repeated blocks?

### 10d. Reduced-motion pass

Enable `prefers-reduced-motion: reduce` in the operating system or browser
settings.

- Do all non-essential animations stop or reduce?
- Does the page still communicate its thesis without animation?
- Are loading indicators still visible (they may persist in reduced
  form)?
- Is the reduced-motion experience complete and dignified, not a
  stripped-down afterthought?

______________________________________________________________________

## 11. First-click test prompt

For a specific task:

"You want to [task]. Looking at this page, where would you click first?"

**Evaluation criteria:**

- If the majority click on the correct element, the scent is strong.
- If clicks scatter, the hierarchy or labelling needs work.
- If users click on a wrong element that looks right, the visual
  affordance is misleading.

______________________________________________________________________

## 12. Preference test prompt

Show two or three concept territories side by side (or in sequence). Ask:

1. Which version feels more trustworthy?
2. Which version feels easier to use?
3. Which version would you be more likely to return to?
4. What do you notice first in each?

**Warning:** Preference tests measure attraction, not usability. A preferred
design may still be harder to use. Combine with first-click or 5-second tests
for a fuller picture. Beware the aesthetic-usability effect.

______________________________________________________________________

## 13. Tree test prompt

For information architecture and navigation validation:

"You want to [task]. Using only this menu structure (no page content visible),
which path would you follow?"

**What it tests:** Whether the navigation labels and structure match the user's
mental model. Does not test visual design — tests the underlying findability.

**When to use:** Before visual design begins (to validate IA) or when users
report difficulty finding content despite clear visual hierarchy (the problem
may be structural, not visual).
