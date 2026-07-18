# Clarity & Restraint

The discipline of *not* juicing. Or, more accurately, of juicing in service of legibility rather than against it.

The Reddit thread "Game juice is overrated" makes a real point, even if it conflates "overused" with "overrated." Games that juice every event indiscriminately produce sensory-overload screens that are hard to read, hard to play, and inaccessible to a meaningful percentage of players. Salyh's "Mistake #6: Lack of Clarity" is the same observation from inside the practice.

This reference exists to balance the others. Read it after — or alongside — any of the other category references.

## The clarity test

After juicing an event, ask: **could the player still tell what happened, and what to do next?**

- If a hit is buried under particles and shake, the player loses track of damage taken.
- If pickups and decoration look the same, players miss pickups.
- If every UI element pulses, none of them stand out.
- If the screen flashes white on every event, the player misses the event that *needs* a flash.

Squint at the screen. If the answer is no, cut something.

## Visual hierarchy

Salyh's framing: "If something is important, make it big; make it high-contrast; make it wiggle. If an element isn't important, shrink or remove it."

The eye is drawn to:

1. **Motion** — fastest-moving thing wins.
2. **Contrast** — highest contrast against the background wins.
3. **Size** — biggest thing wins.
4. **Centre and rule-of-thirds intersections** — focal positions in the framing.
5. **Bright, saturated colour** — particularly on a desaturated background.

Use the hierarchy to direct attention where it needs to go. Conversely, use it to *suppress* attention to incidental elements.

The Rocket League example: when the goal-scoring popup appears, all other UI fades. The flash and the popup are not louder; the rest of the screen is quieter. Same effect, different mechanism.

## Reserved channels

A useful technique: pre-allocate juice channels by event importance, and don't cross them.

| Channel | Reserved for |
|---|---|
| Screen-wide flash | Death, level transition, boss spawn |
| Slow-motion | Boss kill, climactic event, replay |
| Screen shake (heavy) | Explosions, level-changing impacts |
| Screen shake (light) | Generic combat hits |
| Hit-stop | Significant melee impacts, boss reactions |
| Voice line | Major milestones (scoring streaks, achievements) |
| Confetti / sparkle | Pickups, completions, positive events |

Crossing the channels — slow-motion on every basic hit, voice lines on every pickup — devalues the heavy techniques. By the time the boss dies, the player is numb.

## Damage numbers and floating text

Contested. A faction in the Reddit thread argues damage numbers are immersion-breaking; another argues they're essential feedback. The real answer is genre-dependent:

- **RPGs and ARPGs**: damage numbers are part of the loop. Make them tween, fade, scale, colour-coded by element/severity.
- **Action games**: usually skip them. Visual hit feedback (flash, knockback, sound, particles) carries the same information without the chrome.
- **Number-driven roguelikes / IDLE / autobattlers**: numbers are gameplay; juice them aggressively.
- **Horror, narrative, sim**: skip them entirely.

If unsure, ship them as a toggle.

## Accessibility as restraint

Treating accessibility as constraint forces clarity. Designing for these users improves the design for everyone:

- **Reduced motion.** A toggle that disables or attenuates screen shake, slow-motion, parallax, camera kick. Vlambeer added this to Nuclear Throne after playtesters reported nausea.
- **Photosensitive epilepsy.** Avoid full-screen white flashes on frequent events. If used at all, gate behind a toggle, and follow WCAG 2.1's three-flashes-per-second guideline.
- **Colour-blind palettes.** Don't rely on red-vs-green for state. Pair colour with shape, position, or pattern.
- **Audio cues with visual alternatives.** Low-health alarm: also tint the screen edges. Directional sound: also show an off-screen indicator.
- **Subtitles.** See `sound.md`.
- **Independent volume mixing.** Music, SFX, voice, UI as separate sliders.
- **CRT / scanline shader toggle.** A point made by horror-game players in the Reddit thread: forced retro-effect shaders mask asset quality at the cost of legibility, and many players want them off.
- **Damage-number toggle.** As above.
- **Camera-shake intensity slider** rather than just on/off. Some players want some shake, just less.

These toggles are cheap to ship and meaningfully expand the audience. The cost of *not* having them is real players quitting on minute one.

## When juice is genuinely a problem

The Reddit thread isn't entirely wrong. The criticisms with merit:

- **Sameness across indie games.** Vlambeer's aesthetic — big bullets, screen shake, pixel art, fast camera — has been so widely emulated that it now reads as generic. If your game looks like every other Vlambeer descendant, the juice is doing work, but it's also flattening your identity.
- **Juice as gameplay disguise.** Vampire Survivors is mostly a stat-driven slot machine; the juice (animations, level-up jingles, sound stacking on enemy hits) is the carrier wave. This works for that game. It does not work for a game whose underlying loop is broken — the juice will not fix it, and may obscure your ability to diagnose what's actually wrong.
- **Stim over substance.** Fighting games like Smash Ultimate over-applied hit-stop on every smash attack until the cumulative pause time meaningfully slowed combat. The fix is the same as everywhere else: reserve the heavy techniques for the heavy events.

## A test for excess

Play the game. Then play it again with all juice disabled (have a debug toggle for this; you'll need it for performance work anyway). If the underlying game is fun without the juice, the juice is amplifying something real. If the underlying game is dull, the juice is concealing the problem. Fix the game first.

This is the inverse of the workflow rule from `SKILL.md`: don't polish before the mechanic works. Both rules point at the same truth — juice serves the game, never the other way round.

## Common clarity failures

- **Particle-obscured pickups.** Players miss collectibles behind smoke clouds.
- **Damage flash that hides the player sprite.** A full-white silhouette during invincibility frames is fine; one that lasts so long the player loses track of their own position is not.
- **UI animation that delays player input.** The level-complete popup that takes 3 seconds to scale in, blocking the next-level button. Make all UI animations cancellable on input.
- **Mismatched feedback weights.** A small hit producing a bigger response than a critical hit teaches the player to ignore the response entirely.
- **Audio mix that buries SFX under music.** SFX is feedback; music is mood. Default mix should keep SFX prominent.
