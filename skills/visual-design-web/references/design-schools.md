# Design-school lenses

Use these as ideation lenses during concept territory generation, not as dogma.
For each lens, ask: what does this mode communicate, when is it earned, and
what does it risk on the web?

______________________________________________________________________

## Contents

1. Swiss / International
2. Neo-modern
3. Postmodern / deconstructive
4. Brutalist
5. Motion-first
6. Data-visualization
7. Computational / generative
8. Cultural / postcolonial
9. Revivalist / nostalgic
10. Organic / humanist
11. Editorial / magazine
12. Luxury / refined

______________________________________________________________________

## 1. Swiss / International

**Communicates:** Authority, clarity, rationality, institutional confidence.

**Visual hallmarks:** Mathematical grids, restrained palette, sans-serif type
(Helvetica lineage or contemporary grotesques), generous whitespace, systematic
spacing, photography treated as information not decoration.

**When earned:** Content-heavy sites, institutional or governmental contexts,
design systems that must scale across many teams, any project where trust is
built through transparency and order.

**Web strengths:** Naturally responsive grid logic, strong heading hierarchy,
excellent scan-path discipline, pairs well with accessibility requirements.

**Web risks:** Can flatten into "corporate oatmeal" — disciplined to the point
of anonymity. If every element is equally restrained, nothing commands
attention. Requires exceptional typography to stay alive.

**Convention guidance:** Preserve standard navigation patterns. Swiss design
already favours convention; the risk is boredom, not confusion.

______________________________________________________________________

## 2. Neo-modern

**Communicates:** Technical sophistication, forward motion, considered
minimalism with an editorial sensibility.

**Visual hallmarks:** Asymmetric layouts with strong vertical rhythm,
monospaced or geometric type for accent, restrained colour with one or two
sharp accents, generous negative space used structurally, visible grids and
baselines as design elements.

**When earned:** Developer tools, design agencies, technical products,
portfolios where precision signals competence.

**Web strengths:** Clean hierarchy, fast loading if images are sparse, strong
responsive behaviour, works well with dark themes.

**Web risks:** Can tip into cold or unwelcoming. If the design signals "we are
very clever" without corresponding clarity, it fails the five-second test.
Monospaced body text reduces reading speed.

**Convention guidance:** Standard navigation essential. Experimental scroll
behaviour (horizontal scroll, scroll-jacking) must justify itself against the
disorientation cost.

______________________________________________________________________

## 3. Postmodern / deconstructive

**Communicates:** Disruption, irony, cultural literacy, rejection of hierarchy,
layered meaning.

**Visual hallmarks:** Overlapping type, collage, mixed scales, fragmented
grids, visible process marks, clashing typefaces used deliberately,
anti-hierarchy (everything at the same volume, or deliberate inversion).

**When earned:** Cultural institutions, experimental art, music, fashion,
editorial platforms addressing an audience that expects visual challenge,
campaigns where disruption is the message.

**Web strengths:** Memorable. Can create strong first impressions and brand
recognition. Useful when the audience actively seeks novelty.

**Web risks:** Severe. Overlapping elements break screen readers.
Anti-hierarchy makes scanning impossible. Fragmented grids collapse on small
screens. Clashing scales fail zoom tests. The lens must preserve semantic
structure underneath visual disruption — headings must still be headings, links
must still read as links, focus must still be visible.

**Convention guidance:** Primary navigation must remain findable and
keyboard-accessible even when the visual treatment is chaotic. Decorative
disruption of layout must not extend to wayfinding or action elements.

______________________________________________________________________

## 4. Brutalist

**Communicates:** Authenticity, anti-design, function over polish, transparency
about the medium, deliberate friction.

**Visual hallmarks:** Raw HTML aesthetics, system fonts or monospaced stacks,
minimal colour (often black/white with one accent), visible structure (borders,
rules), dense text, no hero images, no stock photography, no gradient sheen.

**When earned:** Tools, technical documentation, personal sites, creative
projects that want to signal "substance over surface", contexts where
anti-aesthetic is itself the statement.

**Web strengths:** Extremely fast. Light payloads. Strong focus visibility if
styled deliberately. Readable at any zoom level. Forces content to do the work.

**Web risks:** Can confuse users who interpret rawness as brokenness. Dense
text without hierarchy fails scanning. System fonts vary across platforms. If
brutalism is just "ugly on purpose" without communication clarity, it fails the
thesis test.

**Convention guidance:** Navigation should still follow expected patterns.
Brutalism's strength is stripping decoration, not stripping affordance.

______________________________________________________________________

## 5. Motion-first

**Communicates:** Dynamism, narrative progression, delight, temporal structure,
premium feel.

**Visual hallmarks:** Scroll-triggered animations, page transitions,
micro-interactions on state changes, parallax (used surgically, not as
wallpaper), kinetic typography, choreographed load sequences.

**When earned:** Product launches, storytelling experiences, portfolios where
process matters, brand sites where the motion is itself the content, onboarding
flows.

**Web strengths:** Can guide scan paths through choreography. Scroll- triggered
reveals give temporal control over information density. State-change animation
clarifies what happened.

**Web risks:** High. Motion without purpose is decoration that moves.
Reduced-motion users get a degraded or broken experience unless the skill
explicitly plans fallbacks. Performance-heavy. Can delay access to content.
Parallax often breaks on mobile. Scroll-jacking steals user agency.

**Convention guidance:** Every motion must answer: "What does this teach,
confirm, or orient?" If the answer is "it looks cool", cut it.
`prefers-reduced-motion` must be respected as a first-class design path, not a
kill switch that makes the page boring.

______________________________________________________________________

## 6. Data-visualization

**Communicates:** Evidence, pattern, insight, analytical rigour, transparency.

**Visual hallmarks:** Charts, graphs, maps, annotated data, restrained colour
palettes optimized for categorical and sequential distinction, small multiples,
sparklines, explanatory annotations.

**When earned:** Dashboards, reports, journalism, research outputs, any context
where the primary content is quantitative or relational.

**Web strengths:** Strong information density when well executed. Annotations
guide scanning. Small multiples are inherently responsive.

**Web risks:** Colour-only encoding excludes colour-blind users. Charts without
text alternatives exclude screen-reader users. Over-decoration of charts (3D
effects, excessive animation) reduces comprehension. Complex interactive charts
can be inaccessible without keyboard support and ARIA labelling.

**Convention guidance:** Non-colour cues (pattern, shape, annotation) alongside
colour. Alt text or structured data tables as alternatives to visual charts.
Key findings stated in text, not only in the chart.

______________________________________________________________________

## 7. Computational / generative

**Communicates:** Emergence, complexity, algorithmic craft, systems thinking,
the aesthetic of the process itself.

**Visual hallmarks:** Procedural graphics (noise fields, particle systems,
cellular automata), parametric type, interactive visual systems,
code-as-design-medium.

**When earned:** Creative technology, art installations, music/audio platforms,
AI-adjacent products, experimental interfaces.

**Web strengths:** Unique. Every visit can yield different visuals. Interactive
variants create engagement. WebGL/Canvas capable of remarkable output.

**Web risks:** Performance. Canvas and WebGL are expensive. Generative visuals
with no fallback fail on low-power devices. Screen readers cannot interpret
canvas content without explicit text alternatives. Computationally generated
backgrounds can fight with foreground content for attention.

**Convention guidance:** The generative layer must not interfere with text
readability, navigation, or action elements. If the generative element is
purely atmospheric, it should degrade gracefully (static fallback image or
plain colour).

______________________________________________________________________

## 8. Cultural / postcolonial

**Communicates:** Specificity, identity, resistance to homogenization,
rootedness in a particular tradition or community.

**Visual hallmarks:** Culturally specific colour palettes, vernacular
typography (or bespoke type drawing on non-Latin traditions), local imagery and
illustration styles, layout patterns informed by specific visual cultures,
materials and textures referencing physical craft.

**When earned:** Organizations rooted in specific cultural contexts,
multilingual sites, diaspora communities, any project where "default Western
tech aesthetic" would erase the identity the site represents.

**Web strengths:** Immediately distinctive. Communicates care and belonging for
the target audience.

**Web risks:** Cultural specificity misapplied is appropriation. The design
must be informed by the community it represents, not applied as flavouring by
an outsider. Bespoke type must still meet contrast and size requirements.
Non-Latin scripts need particular typographic care (line height, word spacing,
directionality).

**Convention guidance:** Navigation and action patterns should still be
discoverable. Cultural specificity in visual language should not extend to
unfamiliar wayfinding if the audience includes people new to the site.

______________________________________________________________________

## 9. Revivalist / nostalgic

**Communicates:** Warmth, familiarity, craft, heritage, analogue texture,
counter-position to tech sterility.

**Visual hallmarks:** Period typography (Art Deco, Victorian, mid-century
modern, 1990s web), desaturated or sepia palettes, film grain and texture
overlays, skeuomorphic elements, hand-drawn illustration, retro-computing
aesthetics.

**When earned:** Brands with heritage, food/drink, craft, music, cultural
events, personal sites, creative tools that want to signal "made by hand."

**Web strengths:** Emotional warmth. Distinct from contemporary tech defaults.
Can create strong brand recall.

**Web risks:** Nostalgia as wallpaper obscures content. Retro type that is
technically decorative (text-in-image) violates accessibility requirements.
Heavy texture/image layers slow loading. Skeuomorphism can confuse affordances
(does this look clickable because it looks like a physical button, or because
it is one?).

**Convention guidance:** Period-appropriate visual treatment should not extend
to period-inappropriate interaction patterns. Navigation must still be standard
web navigation, even if it wears a vintage costume.

______________________________________________________________________

## 10. Organic / humanist

**Communicates:** Warmth, approachability, imperfection, human touch, care.

**Visual hallmarks:** Rounded forms, hand-drawn elements, warm colour palettes,
soft shadows, natural textures, humanist sans-serif or serif type, illustration
over photography, gentle curves in layout.

**When earned:** Health and wellbeing, education, childcare, community
organizations, any product that needs to feel approachable and unthreatening.

**Web strengths:** Reduces anxiety. Warm colour and rounded form signal safety.
Illustration can simplify complex information better than photography.

**Web risks:** Soft contrast and pastel palettes can fail WCAG contrast
minimums. Rounded, low-contrast buttons may lack sufficient non-text contrast.
"Friendly" should not mean "vague" — headings and actions still need clarity.

**Convention guidance:** Standard. This lens works well within conventional
patterns; its distinctiveness comes from surface treatment, not structural
novelty.

______________________________________________________________________

## 11. Editorial / magazine

**Communicates:** Authority, curation, cultural literacy, considered taste,
narrative confidence.

**Visual hallmarks:** Strong type hierarchy (dramatic size contrast between
display and body), art-directed imagery, pull quotes, column layouts, drop
caps, sectional colour shifts, generous whitespace used rhythmically.

**When earned:** Publishing, journalism, long-form content, brands with strong
editorial voice, cultural commentary, luxury.

**Web strengths:** Excellent scan-path control through type hierarchy. Pull
quotes create entry points. Column layouts work well on wide screens.

**Web risks:** Magazine layouts that rely on fixed column widths break on
mobile. Art-directed imagery can be heavy. Drop caps and pull quotes must be
real text, not images. If columns reflow to single-column on mobile, the
hierarchy must still work without the spatial drama.

**Convention guidance:** Navigation should be clear despite the editorial
treatment. Feature articles can push layout further than index pages.

______________________________________________________________________

## 12. Luxury / refined

**Communicates:** Exclusivity, quality, restraint, confidence, premium
positioning.

**Visual hallmarks:** Minimal palette (often monochrome with metallic or jewel
accents), serif or high-contrast sans-serif type, extreme whitespace,
large-scale photography or single-object focus, slow or absent animation, thin
rules and hairline details.

**When earned:** High-end products, architecture, fashion, hospitality,
professional services, any context where premium positioning is the primary
message.

**Web strengths:** Light content density makes hierarchy effortless. Whitespace
gives room for focus styles and target sizes.

**Web risks:** Thin type and hairline details can fail contrast requirements.
Extreme whitespace can waste the first screen (the "cinematic hero slab"
antipattern — a gorgeous image that starves the viewport of information).
Photography-heavy pages are slow. If the luxury treatment prioritizes
atmosphere over information, the five-second test fails.

**Convention guidance:** Navigation can be minimal but must remain
discoverable. Hamburger-only navigation on desktop is not justified by
aesthetic minimalism.

______________________________________________________________________

## Using lenses in combination

Lenses can be mixed. Common productive hybrids:

- **Swiss + Data-viz** — institutional clarity with rich information
  display.
- **Neo-modern + Motion-first** — technical product with choreographed
  narrative.
- **Organic + Editorial** — warm, approachable long-form content.
- **Brutalist + Cultural** — raw structure carrying specific identity.
- **Revivalist + Computational** — retro-futurist: period aesthetics
  driven by generative systems.

When combining, one lens should dominate and the other season. Two lenses at
equal volume cancel each other's communicative clarity.

______________________________________________________________________

## The remix exercise

Take the same brief. Render it through three different lenses. For each, note:

1. What message shifts?
2. What audience shifts?
3. What risks emerge?
4. Which conventions now feel natural to break?
5. Which conventions become even more essential to keep?

This exercise prevents premature convergence on the "obvious" direction.
