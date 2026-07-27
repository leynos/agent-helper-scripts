# Page-type branches

After establishing the design system (SKILL.md Phase 5), route into the
appropriate page-type branch. Each branch specifies the communication
structure, hierarchy priorities, specific risks, and design patterns particular
to that archetype.

______________________________________________________________________

## Contents

1. Marketing / campaign pages
2. Editorial / content pages
3. Transactional / service pages
4. Dashboard / data pages
5. Portfolio / cultural pages
6. Archive / index pages
7. Support / help pages

______________________________________________________________________

## 1. Marketing / campaign pages

### Communication structure

Promise → Proof → Emotional tone → Primary action → Reassurance.

### First-screen priorities

1. **Thesis headline** — what is this, and why does it matter to the
   visitor?
2. **Value proposition** — one to two sentences. Not a tagline; an
   answer.
3. **Primary call to action** — visible without scrolling.
4. **Trust cue** — a recognisable logo, a metric, a testimonial snippet,
   a press mention. Something that answers "why should I believe you?" early.

### Scroll narrative

Below the fold, the page builds the case: features or benefits (structured for
scanning, not reading), social proof (specifics, not vague praise), objection
handling, secondary actions, and closing reinforcement of the primary action.

### Hierarchy notes

- The headline carries the loudest voice. Everything else is quieter.
- Feature sections should scan as a layer-cake: heading → short
  description → supporting detail. Users will read headings first and decide
  whether to read body text.
- Avoid walls of undifferentiated benefit cards at equal visual weight.
  If six features are listed, signal which one matters most.

### Specific risks

- **Cinematic hero slab:** A full-viewport image or video that contains
  no thesis, no value proposition, and no action. The user must scroll past the
  postcard to learn what the page is about. This is attention-debt with no
  guarantee of payoff.
- **Stock-photo sludge:** Generic imagery of smiling people in open-plan
  offices. It communicates nothing and teaches nothing. If photography does not
  show the actual product, the actual team, or the actual outcome, consider
  illustration or no image at all.
- **Action-free first screen:** If the primary action requires scrolling
  to reach, some visitors will never reach it.

### Accessibility notes

- Hero images with text overlays: use real HTML text, ensure contrast
  against all areas of the background image, provide a fallback background
  colour.
- Auto-playing video: must have pause controls, must respect
  `prefers-reduced-motion`, must not auto-play audio.
- Testimonial carousels: must be pausable, keyboard-navigable, and not
  the sole way to access the content.

______________________________________________________________________

## 2. Editorial / content pages

### Communication structure

Title → Deck / standfirst → Subheads as scan layer → Body content → Related
links with strong scent.

### First-screen priorities

1. **Title** — descriptive, specific. "How we reduced build times by 60%"
   beats "Our journey."
2. **Deck / standfirst** — one to three sentences that tell the reader
   what they will learn and why it matters.
3. **Byline and date** — signals authority and currency.
4. **Estimated reading time** — optional but useful for longer pieces.

### Scroll narrative

Subheadings create a scannable outline. Each section should make sense when
read as a heading alone (layer-cake scanning). Pull quotes, callouts, and
inline images break the text rhythm and create visual entry points.

### Hierarchy notes

- Type hierarchy does most of the work. Display size for the title,
  clear step-down for subheads, comfortable body text (16–20px, line-height
  1.4–1.6, line-length 45–75 characters).
- Avoid burying the conclusion. Academic structures (context → method →
  results → discussion) do not suit web reading. Lead with the finding, then
  explain how you got there.

### Specific risks

- **Undifferentiated text walls:** Long body text with no subheadings,
  no visual breaks, and no scan layer. Users bail.
- **Weak related-link scent:** "Related articles" with no description.
  "You might also like" with thumbnails but no headline. Links need enough
  context to generate scent.
- **Image as interruption:** A large decorative image that breaks the
  reading flow without adding information. If the image does not illustrate,
  explain, or evidence the adjacent text, it is in the way.

### Accessibility notes

- Long-form content benefits from a visible table of contents with
  anchor links.
- Inline images need alt text that describes what the image contributes
  to the argument, not just what it depicts.
- Code blocks, tables, and embedded media need appropriate accessible
  treatments.

______________________________________________________________________

## 3. Transactional / service pages

### Communication structure

Question → Help → Input → Error recovery → Next step.

### Design philosophy

Service pages exist to help people complete a task. Clarity, predictability,
and reassurance matter more than expression. The GOV.UK Design System is the
benchmark here: years of user research have produced patterns that work under
pressure, at scale, across diverse audiences.

### Core patterns

**One-question-per-page:** For multi-step tasks, ask one question per screen.
This reduces cognitive load, simplifies validation, makes progress legible, and
reduces the cost of errors (the user loses one answer, not many).

**Step-by-step navigation:** For long journeys, show the user where they are in
the process. A step indicator, breadcrumb trail, or section list provides
orientation.

**Form design:**

- Visible labels above fields (not inside as placeholder-only).
- Help text appears before the field it relates to, or on demand via
  a details/disclosure component.
- Group related fields with fieldsets and legends.
- One column. Multi-column form layouts increase completion errors.

**Error treatment:**

- Inline validation at the point of the error.
- Error summary at the top of the page, linking to each error.
- Error messages: identify the field, describe the problem in plain
  language, suggest a fix. Do not blame the user.
- Error state: not colour alone — use icon, border, and text.

**Success / confirmation:**

- Clear confirmation message.
- What happened, what happens next, what to do if something is wrong.
- Reference number or receipt if applicable.

### Hierarchy notes

- The question or task is the loudest element.
- The action button is the second loudest.
- Help text, secondary actions, and navigation are quieter.
- Avoid competing calls to action on a single step.

### Specific risks

- **Over-designed forms:** Decorative form controls that obscure state
  or reduce accessibility. Custom selects, styled checkboxes, and animated
  inputs must preserve the semantics and keyboard behaviour of native controls.
- **Assumption of linear progress:** Not all users complete a journey in
  one session. Allow saving progress, returning to previous steps, and changing
  answers.
- **Jargon in error messages:** "Validation error: field format
  mismatch" helps no one.

### Accessibility notes

- Form inputs must be associated with visible labels via `for`/`id`.
- Error messages must be announced to screen readers (via `aria-live`
  or focus management).
- Autocomplete attributes should be set for personal-data fields
  (name, email, address, payment).
- Touch targets for buttons and inputs must meet target-size minimums.

______________________________________________________________________

## 4. Dashboard / data pages

### Communication structure

Question → Key finding → Chart / data → Annotation → Non-colour cues.

### First-screen priorities

1. **Key finding or status** — the single most important number or
   state, prominently displayed.
2. **Context** — comparison (vs. last period, vs. target, vs. benchmark)
   that makes the number meaningful.
3. **Navigation to deeper data** — clear paths to drill down.

### Design philosophy

Dashboards answer questions. Every element should earn its space by answering a
question the user actually has. Decorative charts — charts that exist because
"dashboards have charts" — waste attention.

### Hierarchy notes

- Key metrics at the top, loudest.
- Supporting charts at secondary volume.
- Filters and controls: accessible but not dominant.
- Tables: sortable, with clear header alignment, adequate row spacing
  for readability and target size.

### Specific risks

- **Rainbow charts:** Multiple bright hues with no semantic logic. Use
  a sequential or diverging palette appropriate to the data type, and always
  provide non-colour cues.
- **Chart-only communication:** If the chart is the only way to
  understand the data, screen-reader users are excluded. State the key finding
  in text. Provide a data table as an alternative or supplement.
- **Dense default:** If the dashboard loads showing everything at full
  density, nothing stands out. Consider progressive disclosure: summary first,
  detail on demand.
- **Stale data without indication:** If data has a timestamp, show it.
  If data is stale, say so.

### Accessibility notes

- Charts need text alternatives (summary in alt text, full data in a
  table).
- Interactive chart elements (tooltips, drilldowns) must be keyboard-
  accessible.
- Colour-coded status indicators need redundant cues (icon, text
  label, pattern).
- Data tables need proper `<th>` scope attributes and caption elements.

______________________________________________________________________

## 5. Portfolio / cultural pages

### Communication structure

Framing statement → Work selection logic → Sequence → Depth → Contact or
conversion path.

### First-screen priorities

1. **Identity** — who is this, and what do they do? One sentence, not a
   mission statement.
2. **Best work, visible immediately** — the strongest piece, not a
   loading animation.
3. **Navigation logic** — how is the work organised? By type, by date,
   by client, by medium?

### Design philosophy

Portfolio pages present work. The design should frame the work, not compete
with it. A portfolio that is itself a design showpiece risks upstaging its own
content. Unless the portfolio design is itself the work (a creative
technologist's personal site, for instance), restraint in the container lets
the content breathe.

### Hierarchy notes

- Work thumbnails or titles at primary volume.
- Descriptions, client names, dates at secondary volume.
- Detail pages: title, brief, and process narrative at comfortable
  reading hierarchy; full-size work images or embeds.
- Contact / hire CTA visible from any point in the portfolio.

### Specific risks

- **Grid of identical thumbnails:** If every project is a same-sized
  square with the same visual treatment, the portfolio communicates "I have
  many projects" but not "this one is exceptional." Consider hierarchy within
  the grid.
- **Lightbox-only viewing:** If work can only be seen in a modal overlay
  that traps focus or breaks back-button behaviour, the experience suffers.
- **Missing context:** A beautiful image with no explanation of the
  problem it solved, the constraints it faced, or the outcome it achieved is a
  gallery, not a portfolio.

### Accessibility notes

- Project images need meaningful alt text describing what the project
  is, not just "Screenshot of project."
- Filtering and sorting must be keyboard-accessible.
- Video or interactive work needs text descriptions of what it
  demonstrates.

______________________________________________________________________

## 6. Archive / index pages

### Communication structure

Scope statement → Browse/filter/search → Entries with sufficient scent →
Pagination or progressive loading.

### Design philosophy

Archive pages help people find something. Findability depends on information
scent: each entry must carry enough context (title, date, category, excerpt,
thumbnail) for the user to judge relevance without clicking through.

### Hierarchy notes

- Entry titles carry the loudest voice.
- Metadata (date, category, author) at secondary volume.
- Excerpts or descriptions at tertiary volume.
- Filters and search at utility volume — accessible but not dominant.

### Specific risks

- **Title-only lists:** Entries with titles but no description or
  excerpt. Weak scent; the user must click to learn what each entry contains.
- **Infinite scroll without landmarks:** Endless lists with no way to
  bookmark position, no "back to top", and no visible count or progress.
- **Absent search:** For large archives, browsing alone is inadequate.

### Accessibility notes

- Pagination controls must be keyboard-accessible with clear labels
  ("Page 3 of 12", not just "3").
- Filter state changes must be announced to screen readers.
- "Load more" buttons need clear labelling and focus management.

______________________________________________________________________

## 7. Support / help pages

### Communication structure

Problem identification → Solution → Escalation path.

### Design philosophy

People arrive at support pages after something has gone wrong. They are often
frustrated, confused, or anxious. The design should be calm, direct, and fast.
Decorative elements are unwelcome. Clarity is kindness.

### First-screen priorities

1. **Search** — prominent, functional, with good results.
2. **Most common problems** — visible without searching.
3. **Contact/escalation** — visible, not buried.

### Hierarchy notes

- Problem/question titles at primary volume.
- Solution text at comfortable reading volume.
- Related problems at secondary volume.
- Contact options always visible or one click away.

### Specific risks

- **Chatbot wall:** Forcing users through a chatbot before allowing
  access to written help or human contact. This frustrates users who know what
  they need and delays those in crisis.
- **Circular help:** Articles that link to other articles that link back
  to the first, without ever providing a direct answer.
- **Hidden contact information:** Burying phone numbers, email
  addresses, or live-chat access behind multiple clicks.

### Accessibility notes

- Search must be keyboard-accessible with visible focus.
- Expandable FAQ sections must use proper disclosure patterns
  (`<details>`/`<summary>` or ARIA disclosure).
- Step-by-step troubleshooting must work without images (the fix should
  be described in text, with screenshots as supplements).
