---
name: juice-it-or-lose-it
description: Diagnose and add "juice" — game feel, feedback, and tactile polish — to games, prototypes, and interactive software. Use this skill whenever the user is building, polishing, prototyping, or reviewing a game (especially action, arcade, platformer, shooter, or rhythm games), or when they ask about game feel, juice, screen shake, hit feedback, particles, easing, tweening, screen pause/hitstop, juicy effects, "making it feel good", or why their prototype feels limp, lifeless, dry, or cheap. Also trigger when reviewing UI prototypes that need tactile response, or when the user mentions Jonasson, Purho, Vlambeer, Nuclear Throne, screen shake, or Steve Swink's "Game Feel" book. Apply even to non-game interactive software when the user wants buttons, transitions, or interactions to feel responsive and satisfying.
---

# Juice it or Lose it

A practical reference for adding "juice" — the layered visual, auditory, and
temporal feedback that makes interactive software feel alive. Distilled from
the Jonasson/Purho 2012 talk of the same name, Jan Willem Nijman's "The art of
screen shake," Steve Swink's *Game Feel*, Mark Brown's analysis, and
field-tested examples from Vlambeer, Cactus, dashpong, and others.

## What juice is, and what it isn't

Juice is **maximum output for minimum input** — every player action triggers a
cascading set of responses across multiple sensory channels. The original
framing comes from a 2005 Gamasutra piece on prototyping: a juicy game "feels
alive and responds to everything you do, tons of cascading action and response
for minimal user input."

Juice is **not** decoration. It is feedback. Reframing it as "feedback" rather
than "juice" prevents the most common failure mode — adding flash for flash's
sake. If a wobble, particle, or sound is not communicating something to the
player about cause, consequence, weight, or state, it is clutter. Clutter
degrades clarity, and clarity is more valuable than spectacle.

Juice also is **not** a substitute for gameplay. Add it after the core mechanic
works. Jonasson and Purho built a fully working Breakout clone before juicing
it. Nijman makes the same point: prototype the game first, then spend a year on
the menu.

## When to apply this skill

- Polishing a finished prototype that "feels off" or "feels cheap"
- Reviewing a build and producing a structured audit of feedback gaps
- Designing feedback for a single mechanic (a jump, a hit, a pickup, a death)
- Choosing easing curves or tween durations
- Diagnosing why a game feels sluggish or unresponsive
- Adding tactile response to non-game interfaces (transitions, button presses,
  drag-and-drop)

Do **not** apply this skill before the underlying mechanic exists. Polish
before the mechanic is settled wastes effort and entrenches bad design.

## The seven categories

Juice is most usefully decomposed into seven channels. Each gets its own
reference file. Read the ones relevant to the task at hand — do not load all of
them by default.

| Category            | Read when…                                                          | Reference                   |
| ------------------- | ------------------------------------------------------------------- | --------------------------- |
| Movement & tweening | Animating any property over time — position, scale, rotation, alpha | `references/movement.md`    |
| Particles & debris  | Events need spatial spread or visible aftermath                     | `references/particles.md`   |
| Sound               | Almost always; the highest-leverage category                        | `references/sound.md`       |
| Camera              | Playfield needs to react, or impact needs amplification             | `references/camera.md`      |
| Permanence          | The world should remember what happened                             | `references/permanence.md`  |
| Personality         | Inanimate elements need to feel alive                               | `references/personality.md` |
| Clarity & restraint | Always — and especially when the build feels "loud" or unreadable   | `references/clarity.md`     |

A separate file, `references/audit.md`, contains a structured checklist for
auditing an existing build. Use it when reviewing rather than building.

## The minimal layered-feedback pattern

When a single player action fires, layer responses across as many channels as
fit. The Jonasson/Purho ball-hits-block event in their demo stacks roughly
twelve effects on one collision:

1. Ball scales up briefly, then eases back (movement)
2. Ball flashes white, then eases back to colour (movement / clarity)
3. Ball rotates to face new direction (movement)
4. Ball stretches along its velocity vector (movement)
5. All blocks scale slightly toward or away from the impact (movement)
6. The wall the ball came from bounces (movement)
7. Block falls away with rotation, scaling, and darkening (movement / clarity)
8. Smoke puff emits at impact (particles)
9. Shatter debris falls from destroyed block (particles)
10. Ball trail extends behind the moving ball (particles)
11. Distinct collision sound, pitch-shifted on streaks (sound)
12. Screen shake proportional to impact (camera)

None of these alone changes the game. Stacked, they transform a sterile
prototype into something that demands replaying. **The point is the stack, not
any single effect.**

## Workflow

1. **Establish the polish baseline.** Confirm the core mechanic is settled. If
   it isn't, stop and finish the mechanic first.
2. **Inventory the events.** List every player-facing event: every input, every
   state change, every collision, every spawn, every death, every UI
   transition. This is the surface area for juicing.
3. **Rank events by frequency and weight.** Frequent events (movement, basic
   attacks) need light, fast, varied feedback to avoid fatigue.
   Rare-but-important events (boss kills, level transitions, death) earn
   heavier feedback — slow-mo, screen-wide flashes, voice cues.
4. **Layer across channels.** For each ranked event, sketch responses across
   the seven categories. Aim for at least three channels on common events and
   five-plus on rare ones.
5. **Build, then test on someone else.** You stop noticing your own juice
   within a day. Hand the build to someone unfamiliar — watch where they react
   and where they don't.
6. **Audit for clarity.** Run `references/audit.md` against the build. Cut
   anything that does not communicate. Add accessibility toggles for screen
   shake, flashing, and motion.

## Pitfalls

- **Linear motion everywhere.** Lerps are programmer-default and look
  mechanical. Real objects accelerate and decelerate. See
  `references/movement.md`.
- **Quiet or thin sound effects.** A bass-boosted gunshot is a cliché because
  it works. See `references/sound.md`.
- **Screen shake as a hammer.** Screen shake on every event becomes invisible
  and induces nausea in some players. Reserve it for impact and provide a
  toggle. See `references/camera.md`.
- **Juice in lieu of gameplay.** Vampire Survivors aside, no amount of confetti
  rescues a broken loop. Fix the loop first.
- **Particle-engine yak-shaving.** Building your own particle system from
  scratch is a known programmer trap. Use what your engine ships with. The
  juice comes from how you use it, not how you wrote it.
- **No accessibility escape hatches.** Some players get motion-sick from shake,
  some have photosensitive epilepsy, some find damage numbers
  immersion-breaking. Toggles cost almost nothing and broaden your audience.

## Source material

The skill draws on:

- **Martin Jonasson & Petri Purho**, *Juice it or lose it* (2012). The
  canonical talk; the Breakout demo is the worked example.
- **Jan Willem Nijman (Vlambeer)**, *The Art of Screen Shake* (2013). Thirty
  incremental polish steps applied to a stub shoot-em-up.
- **Steve Swink**, *Game Feel: A Game Designer's Guide to Virtual Sensation*
  (2008). Academic foundation; defines feel as "real-time control of virtual
  objects in a simulated space, with interactions emphasised by polish."
- **Mark Brown**, *Game Feel* (Game Maker's Toolkit, 2014). Concise
  consolidation of the above with practical examples.
- **Mike Salyh**, *6 Mistakes That'll Drain the 'Juice' Out Of Your Game* (Game
  Developer, 2020). The "anti-juice" framing.
- **Kyle Gabler**, "Add eyes to anything" — a maxim from World of Goo.
- **Robert Penner**, easing equation library (2002). The canonical reference
  for easing curves.

When working through this skill, prefer concrete examples from these sources
over invented ones. They have been studied and replicated for over a decade.
