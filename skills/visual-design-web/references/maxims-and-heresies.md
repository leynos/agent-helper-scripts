# Maxims and heresies

Guiding principles for the skill's positions, and a compact book of heresies —
antipatterns that routinely reduce discoverability, clarity, or accessibility.

______________________________________________________________________

## Maxims

These are not rules. They are positions the skill defends until the designer
provides sufficient justification to override them.

### Communication

- **Every page needs a thesis.** If you cannot state the page's purpose
  in one sentence, the page is trying to do too much.
- **Signal before flourish.** Communicate the thesis before investing
  in aesthetic expression. A beautiful page that does not communicate is a
  decorated failure.
- **What stays clear when attention is thin and patience is thinner?**
  Design for the distracted, the stressed, the sceptical, and the rushed — not
  for the calm, attentive ideal user.

### Hierarchy and navigation

- **Distinctive accents, conventional affordances.** Visual language can
  be adventurous; navigation, links, buttons, and form controls should behave
  as expected.
- **Let headings do some of the navigation.** A well-written heading
  set is a table of contents for both sighted and screen-reader users.
- **Which link, button, or heading carries the strongest scent?** If the
  answer is unclear, the hierarchy needs work.

### Content as design material

- **Use real text unless image-text is genuinely essential.** Text in
  images cannot be resized, reflowed, translated, or read by assistive
  technology.
- **Photography for reality; illustration for simplification.** Choose
  the image type that matches the purpose.
- **Every image must explain, orient, reassure, or intensify meaning.**
  If it fills space or "sets a mood" without communicating, it is payload
  without purpose.
- **Use literal language where stakes are high.** Cleverness in error
  messages, legal text, and medical information costs clarity.

### Trust and consistency

- **Consistency buys trust; uniformity is optional.** A system can be
  consistent in its principles while varying in its expression across contexts.
- **What makes this page trustworthy?** If the design cannot point to
  specific trust cues, the page asks for faith without evidence.

### Accessibility as design

- **Accessible constraints are compositional tools.** Contrast ratios,
  target sizes, focus visibility, and text-spacing resilience are design
  parameters, not punishment. They shape composition the way a sonnet's form
  shapes language.
- **Decoration is welcome; decoration that obscures purpose is not.**
  The question is never "is it decorative?" but "does the decoration interfere
  with communication?"

### Performance and payload

- **If the visual payload is huge, the idea had better be worth it.**
  Large images, video backgrounds, and heavy animation are design decisions
  with user costs: loading time, data consumption, battery drain, and the
  patience of a visitor who has not yet decided to stay.

### Evidence

- **What should the user remember tomorrow?** If the page is forgotten
  within an hour, either the thesis is weak or the hierarchy failed to land it.
- **Pretty can flatter a broken experience.** The aesthetic-usability
  effect means attractive designs are perceived as more usable than they are.
  Always test behaviour, not just preference.

______________________________________________________________________

## Book of heresies

These are design choices that the skill flags as antipatterns. Each heresy
includes what it is, why it persists, and what to do instead.

### 1. Hidden primary navigation

**The heresy:** Hiding the site's main navigation behind a hamburger menu on
desktop, or behind a gesture with no visible affordance.

**Why it persists:** Designers prize visual cleanliness. Visible navigation
uses space. Hamburger menus are familiar from mobile.

**Why it fails:** Nielsen Norman Group research consistently shows that visible
navigation increases discoverability, reduces time to task, and reduces user
effort. On desktop, where screen space is abundant, hiding navigation is an
aesthetic choice that imposes a usability cost. On mobile, the hamburger is a
reasonable compromise; on desktop, it is rarely justified.

**Instead:** Show primary navigation visibly. If the site has many sections,
prioritize the most-used items and provide a "More" or secondary navigation
path.

### 2. Ambiguous link text

**The heresy:** "Read more", "Click here", "Learn more", "See details" — links
whose destination cannot be determined from the link text alone.

**Why it persists:** Convenience. Generic link text is easy to template.

**Why it fails:** Screen-reader users navigate by link list; ambiguous links
are meaningless out of context. Sighted users scanning the page cannot tell
where the link goes without reading surrounding text. Information scent is weak.

**Instead:** Descriptive link text that states the destination or purpose:
"Read the full accessibility audit", "Compare pricing plans", "View the
deployment guide."

### 3. Text baked into images

**The heresy:** Rendering text as part of an image — headlines in hero images,
body text in infographics, navigation labels in graphical menus.

**Why it persists:** Pixel control. Designers want precise type rendering,
custom fonts without web-font loading, or text integrated into photographic
compositions.

**Why it fails:** Text in images cannot be resized by the user, reflowed to
different viewport widths, translated by machine or human translators, read by
screen readers (unless duplicated in alt text), or overridden by user
text-spacing preferences.

**Instead:** Use real HTML text over background images. For infographics,
provide a text alternative. For logos, use alt text containing the brand name.

### 4. Colour-only meaning

**The heresy:** Using colour as the sole means of conveying information — red
for error, green for success, colour-coded chart segments with no other
distinguishing cue.

**Why it persists:** Colour is a fast, efficient signal. It requires minimal
visual space.

**Why it fails:** Approximately 8% of men and 0.5% of women have some form of
colour vision deficiency. Even users with typical colour vision may be in
environments (bright sunlight, low-quality displays) where colour distinctions
are hard to perceive.

**Instead:** Pair colour with a redundant cue: icon, text label, pattern,
border, position, or shape.

### 5. Decorative motion

**The heresy:** Animation that exists for atmosphere, not information —
elements that bounce, slide, or fade on scroll without teaching, confirming, or
orienting.

**Why it persists:** Motion signals premium quality and modernity. It is
fashionable. Clients associate animation with sophistication.

**Why it fails:** It costs performance. It distracts from content. It creates
accessibility barriers for users with motion sensitivities, vestibular
disorders, or cognitive differences. If `prefers-reduced- motion` turns it off
and nothing is lost, it was decorative.

**Instead:** Every animation must pass the motion justification test (see
`references/exercises-and-devices.md`). Motion that teaches, confirms, or
orients earns its cost. Motion that jiggles does not.

### 6. Cinematic hero slabs

**The heresy:** A full-viewport image or video that occupies the entire first
screen, with no headline, no value proposition, and no action. The user must
scroll past the postcard to discover what the page is about.

**Why it persists:** It looks spectacular in presentations. It signals premium
positioning. It is photogenic in dribbble posts.

**Why it fails:** The first screen is the most valuable real estate on the
page. A hero slab that contains no thesis wastes it. Users who arrive from
search, social, or email expect to confirm within seconds that they are in the
right place. If the first screen is all atmosphere and no information, a
percentage of visitors bounce before scrolling.

**Instead:** The first screen must contain the page thesis (headline + value
proposition), the primary action, and at least one trust cue. An image can
support these elements, but it must not replace them.

### 7. Stock-photo mood filler

**The heresy:** Generic stock photography (handshakes, open-plan offices,
diverse groups of attractive people smiling at laptops) used as a stand- in for
actual visual communication.

**Why it persists:** Real photography is expensive. Illustration requires
commissioning. Stock fills the space immediately.

**Why it fails:** Users have learned to ignore stock photography. It carries
zero information and negative credibility — it signals that the organization
did not care enough to show the real thing. Studies (NN/g) have found that
users skip generic images entirely.

**Instead:** If real photography is unavailable, consider illustration,
iconography, or no image at all. A well-typeset page with no imagery is more
trustworthy than one padded with generic stock. If stock must be used, select
images that are specific, contextual, and not obviously staged.

### 8. Invisible focus indicators

**The heresy:** Removing or suppressing the browser's default focus indicator
(`outline: none`) without providing a visible replacement.

**Why it persists:** The default focus ring is considered ugly. It appears on
click in some browsers, which designers find disruptive.

**Why it fails:** Focus indicators are the primary navigation tool for keyboard
users, who include people with motor disabilities, power users, and anyone with
a broken trackpad. Removing focus visibility makes the site unnavigable for
these users.

**Instead:** Style the focus indicator deliberately — make it part of the
design system. A custom focus ring (offset outline, box shadow, colour shift)
that meets contrast and area requirements is better than the default and
infinitely better than nothing. Use `:focus-visible` to show the indicator only
during keyboard navigation if click-triggered outlines are the concern.

### 9. Infinite scroll without escape

**The heresy:** Bottomless content feeds with no pagination, no "back to top"
link, no visible position indicator, and no way to bookmark or share a specific
position.

**Why it persists:** Engagement metrics. Infinite scroll reduces the friction
of pagination and keeps users in the feed.

**Why it fails:** Users lose their position if they navigate away and return.
Footer content becomes unreachable. There is no sense of progress or
completion. Screen-reader users may encounter performance issues as the DOM
grows.

**Instead:** Paginate, or use "load more" with clear position markers. If
infinite scroll is used, provide a persistent "back to top" control, show
position indicators, and ensure the footer is accessible via another route.

### 10. Form labels inside fields

**The heresy:** Using placeholder text as the only visible label for form
fields, with no persistent label above or beside the field.

**Why it persists:** Compact. Looks clean. Saves vertical space.

**Why it fails:** The label disappears as soon as the user starts typing,
leaving them unable to verify which field they are in. Users returning to check
their input cannot see the question. Placeholder text is typically
low-contrast. Screen readers may not consistently announce placeholder-as-label.

**Instead:** Visible labels above or beside each field, always. Use
placeholders only for supplementary hints (example format, not the field name).
