# Particles & Debris

Cheap, high-leverage juice. A puff of smoke at a collision communicates
"something happened here" without changing any underlying mechanic.

The programmer trap, called out by both Jonasson/Purho and Nijman: do **not**
build your own particle system from scratch. The pleasure of writing one is
real; the cost of finishing it before you ship is also real. Use whatever your
engine ships with, or a small library. Spend the saved time tuning emission
parameters.

## Categories of particle effect

### Impact puffs

A short burst of smoke or dust at the collision point. The classic
Jonasson/Purho example: when the ball hits a block, emit a small grey cloud
that fades out over 300–500ms.

Tuning notes:

- 5–15 particles, not 100.
- Random initial velocity in a small cone aimed away from the impact normal.
- Quick alpha fade-out; slight upward drift if the world has gravity.

### Trails

Recorded positions of a moving object, drawn back over time. Two
implementations:

1. **Stamped sprites**: emit a fading sprite at the object's current position
   every frame. Cheap; works with any shape.
2. **Triangulated strip**: keep a rolling buffer of the last N positions and
   draw a tapered ribbon along them. Slightly more work; looks much better for
   fast-moving objects.

The dashpong dev's approach: keep a position buffer for the ball, draw a line
that lerps in colour between white (untouched) and the player's team colour
(touched). Trail thickness tapers to zero at the tail.

### Debris

Pieces of a destroyed object that fall away under gravity. Three increasingly
elaborate options:

1. **Fade-out**: just shrink and fade the destroyed object's sprite. Cheap.
2. **Sprite scatter**: replace the destroyed object with 4–8 smaller sprite
   pieces, each given a random velocity, rotation, and gravity. The
   Jonasson/Purho default.
3. **Triangulated shatter**: cut the sprite into mesh triangles, applying
   outward velocity, rotation, and gravity to each. The dashpong goal-explosion
   uses this. Cosmetically gorgeous; more code than it deserves.

Whichever method, **darken the debris by 20–40%** so it visually separates from
intact objects on the playfield. Without darkening, broken blocks blend with
unbroken ones during chaotic moments.

### Confetti and sparkles

For successful events — pickups, completions, achievements. Bright, varied
colours; small, fast-moving particles; usually emitted from the centre of the
celebrated object outward. Mario coins do this; Starbound's quest reward bag
does this.

The rule of thumb the talk endorses: "Confetti always works."

### Background ambience

Idle particles unconnected to any specific event — drifting dust, embers,
leaves, rain, distant smoke columns. They keep the screen alive when no player
input is happening, addressing Salyh's "dead stillness" failure mode.

These should be subtle and slow. They are stage dressing, not feedback.

## Particles as gameplay reinforcement

Tie particle behaviour to game state, not just events:

- **Background particles deflect on goal events.** The dashpong dev applies an
  explosion's gravity to the ambient particle field — the world reacts to the
  impact, not just the impact site.
- **Trails change colour with state.** A power-up makes the player's trail
  flicker between two colours.
- **Particle density rises with intensity.** A combo system spawns more
  aggressive impact effects as the multiplier climbs.

## Permanence in particles

Most particles fade and die. A few should not:

- **Bullet shells** that pile on the floor permanently. Nijman explicitly
  recommends this — modern hardware can handle thousands of shells trivially,
  and the visible ammunition history reads as combat aftermath.
- **Scorch marks** at explosion sites that decal onto the ground.
- **Blood splatters** that decal and stay until the level ends (Hotline Miami's
  signature).
- **Bullet holes** in walls.

Permanent particles cross over into the territory of `references/permanence.md`.

## Common mistakes

- **One-size-fits-all impact.** The same burst on every collision becomes
  invisible. Vary by surface, weapon, intensity.
- **Overdense emitters.** A hundred-particle burst on a frequent event is
  GPU-expensive and visually noisy. Five well-tuned particles read better.
- **Linear motion.** Particles obeying constant velocity look like sprite spam.
  Apply gravity, drag, and easing.
- **Symmetric emission.** A perfect circle of particles reads as a procedural
  emitter, not a physical event. Bias the cone, vary the count, randomize the
  timing.
- **Foreground particles obscuring play.** The aesthetic win must not cost
  legibility. If players are missing bullets or pickups behind a smoke cloud,
  the smoke is wrong.

## Implementation notes

- **Emitter pooling.** Allocate a fixed pool of particle objects and reuse
  them. Garbage-collected languages especially will hitch on per-frame
  allocation.
- **Soft caps.** Set a hard maximum particles-per-frame budget. Drop oldest
  when exceeded. The scene will degrade gracefully under load.
- **Off-screen culling.** Particles beyond the camera should not consume update
  time. Most engines handle this; verify yours does.
- **Z-ordering.** Decide deliberately whether particles render in front of or
  behind game-critical sprites. Inconsistent z-order is a leading cause of
  "this looks wrong but I can't say why."
