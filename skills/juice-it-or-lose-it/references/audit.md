# Audit Checklist

Use this when reviewing an existing build rather than designing from scratch. It is structured as a set of yes/no questions per category, plus follow-up notes for each. Score the build, identify the gaps, prioritise the cheapest wins.

The intent is that running through this checklist on a build takes 30–60 minutes and produces a ranked list of additions that, if implemented, would meaningfully improve game feel.

## How to run an audit

1. **Play the game** for at least one full session before consulting the checklist. First impressions are the most reliable signal of feel.
2. **Take notes** on anything that felt wrong, unclear, dead, or excessive. Don't try to articulate the cause — just mark the moment.
3. **Walk the checklist** with the build still fresh. Tick each item; for "no" items, note severity (low / medium / high) and the cheapest known fix.
4. **Cross-reference with first-impression notes.** Any moment that felt wrong but doesn't show up in the checklist is a missing question. Add it for next time.
5. **Rank the gaps.** Cost on one axis, payoff on the other. Cheap-and-high-payoff first.

## Movement & tweening

- [ ] Does any non-input motion in the game use easing rather than linear interpolation?
- [ ] Do objects entering or leaving the scene tween in/out, rather than appearing/disappearing instantaneously?
- [ ] Does the player's avatar squash and stretch on landing, attacking, or other significant actions?
- [ ] Do projectiles, balls, or pickups scale up briefly on collision, then ease back?
- [ ] Do batched objects (a row of spawning enemies, a grid of UI elements) appear with a small randomised stagger?
- [ ] Do collectibles, important UI elements, or pickups have an idle pulse drawing the eye?
- [ ] Are there any anticipation poses or wind-ups before significant actions?
- [ ] Are there follow-through motions after significant actions (recoil, weapon-wobble, cape flutter)?

If most of these are "no" — particularly the easing question — start with `references/movement.md` and address the largest, most frequent moving objects first.

## Sound

- [ ] Is there sound on every input that doesn't move the character (firing, jumping, ability use, menu navigation)?
- [ ] Is there sound on every collision, varied by the colliding pair (ball-wall vs ball-block vs ball-paddle)?
- [ ] Is there sound on state changes (level start, level end, death, low-health, power-up activation)?
- [ ] Is there sound on UI transitions (menu open, panel slide, button hover and click)?
- [ ] Are repeated sounds pitch-varied or sample-rotated to avoid fatigue?
- [ ] Do streak/combo events use rising-pitch chains?
- [ ] Do impact and weapon sounds have low-frequency presence (the bass-boost trick)?
- [ ] Is there music, even placeholder?
- [ ] Are SFX, music, voice, and UI on independent volume sliders?
- [ ] Are voice lines (if any) subtitled?

If most of these are "no," sound is almost certainly the highest-payoff next investment. See `references/sound.md`.

## Camera

- [ ] Does the camera lerp toward the player rather than snapping?
- [ ] Is there look-ahead biasing the camera in the direction of motion or aim?
- [ ] Is there screen shake on impactful events?
- [ ] Is the screen shake intensity proportional to event weight (small hit = small shake)?
- [ ] Is screen shake driven by Perlin/simplex noise rather than uniform random? (Not strictly required, but smoother.)
- [ ] Is there a screen-shake intensity setting in the options menu, including off?
- [ ] Is there hit-stop / freeze frames on significant impacts? (Optional but high-impact.)
- [ ] For multi-object games: does the camera frame the relevant action, zooming as needed?
- [ ] On firing weapons, is there a camera kick in the opposite direction?

`references/camera.md` covers the techniques.

## Particles & debris

- [ ] Do collisions produce a small puff of smoke, dust, or sparks at the impact point?
- [ ] Do moving projectiles or fast-moving characters have a trail?
- [ ] Do destroyed objects produce debris (sprites or shatter triangles) that falls under gravity?
- [ ] Is destroyed-object debris visually distinct from intact objects (darker, smaller, rotating)?
- [ ] Do successful events (pickups, completions) produce sparkles or confetti?
- [ ] Is there ambient background motion (drifting particles, wind, embers, dust motes)?
- [ ] Are particle emitters varied by event type, not one-size-fits-all?
- [ ] Are particles foreground-respectful (not obscuring gameplay-critical elements)?

See `references/particles.md`.

## Permanence

- [ ] Do enemy corpses persist after death (until level reset)?
- [ ] Do bullet shells, spent grenades, dropped weapons persist?
- [ ] Are there decals on the world (bullet holes, scorch marks, blood, footprints)?
- [ ] Does the world reflect player history (cleared dungeons stay cleared, killed bosses stay dead)?
- [ ] Do characters have idle animations rather than freezing between commands?
- [ ] Does the background have motion when the player is idle?

See `references/permanence.md`.

## Personality

- [ ] Do interactive objects have eyes, a face, or some equivalent personhood marker?
- [ ] Do those eyes track the relevant target (player, ball, threat)?
- [ ] Do faces or sprites change expression on emotional events (success, failure, surprise)?
- [ ] Do characters blink or have other small idle motions?
- [ ] Does the player's avatar have personality through motion (bouncy / heavy / nervous)?

See `references/personality.md`.

## Clarity & restraint

- [ ] If you squint at the screen during a chaotic moment, can you tell what's happening and what to do next?
- [ ] Are heavy techniques (slow-motion, full-screen flash, voice lines) reserved for major events?
- [ ] Do common events use lighter techniques than rare events?
- [ ] Is there a reduced-motion accessibility toggle?
- [ ] Are there independent volume sliders for music, SFX, voice, UI?
- [ ] If using full-screen flashes, do they comply with photosensitivity guidelines (no more than 3 per second)?
- [ ] If using a CRT / retro shader, is it toggleable?
- [ ] If using damage numbers, are they toggleable?
- [ ] Does state read primarily through shape, position, and contrast rather than colour alone?
- [ ] Can the player skip or cancel UI animations with input?

See `references/clarity.md`.

## Cross-cutting questions

- [ ] **The strip-everything test**: if you stripped out the points, plot, level design, and music, would the basic input/response loop still feel satisfying?
- [ ] **The new-player test**: when someone unfamiliar plays the game for 5 minutes, where do they get confused, frustrated, or bored?
- [ ] **The juice-off test**: with all juice disabled (debug toggle), is the underlying game fun? If not, the priority is the underlying game, not the juice.
- [ ] **The frequency map**: list the events that fire most often. Are they juiced lightly enough not to fatigue, varied enough not to repeat?
- [ ] **The rare-event map**: list the events that fire rarely but matter (boss kill, level transition, achievement). Are they juiced heavily enough to read as significant?

## Output format

When using this checklist for a structured review, produce something like:

```
Build: <name> @ <commit>
Reviewed: <date>

Severity: high / medium / low
Cost: low / medium / high (effort to implement)

[H/L] Movement: no easing on level-intro animations.
      → Add easeOutBack on block grid spawn. ~2hrs.
[H/M] Sound: no sound on UI button clicks.
      → 5 minutes with sfxr per button. ~30min total.
[M/L] Particles: no impact puff on bullet hits.
      → Existing particle system, new emitter config. ~1hr.
[L/H] Personality: no faces on any object.
      → Larger task; defer until art pipeline supports it.
```

Sort by severity desc, then cost asc, and present the top ten as a prioritised work plan.
