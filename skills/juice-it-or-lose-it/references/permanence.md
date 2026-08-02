# Permanence

What the world remembers about what happened. The opposite failure mode is
Salyh's "abrupt disappearance" and Nijman's "empty battlefield" — events occur,
then leave no trace, and the world feels reset and amnesiac.

Permanence costs little — modern hardware will happily render thousands of
corpses, shells, and decals — and pays back in scene density, narrative, and
the player's sense that their actions have weight.

## Categories of permanence

### Combat aftermath

Corpses, debris, weapons dropped by killed enemies. Nijman is emphatic: "Why
leave the fucking battlefield empty after it's over?" The dead bodies, expended
ammunition, and broken cover communicate the cost and history of the fight.

The most-cited example is Hotline Miami. Bodies, blood pools, and dropped
weapons stay until the level resets. When the player walks back through a
cleared floor to the exit, they pass through their own carnage. The mechanical
purpose is shortcut and pacing; the emotional purpose is reflection — the game
refuses to let the player skip past what they just did.

Implementation:

- **Corpse sprites** persist after death animation. Either a static "dead"
  sprite or the final frame of the death animation.
- **Drop weapons** at the death position with appropriate physics.
- **Cap at the level boundary** — clear corpses on level transition, not on
  screen exit.

If the engine struggles with high entity counts, consider a soft cap with FIFO
eviction — the oldest corpses fade out as new ones spawn.

### Spent ammunition

Bullet shells. Spent grenade pins. Empty magazines. Nijman recommends letting
these stay forever, and adds the offhand suggestion that it would be funny to
apply physics to the shells until you can swim in them. Operationally:

- **Shell ejection** on every shot. Shell sprite spawned at the gun, given a
  small randomized velocity and rotation, falls under gravity.
- **Settle on contact** with the ground. Physics either sleep or is zeroed out;
  the shell sprite stops moving.
- **No collision with the player.** Shells are decorative. They should not
  block movement or interact with gameplay.
- **Cap or persistent.** Modern hardware handles thousands of decorative
  entities. A FIFO cap of, say, 500 shells per level keeps memory bounded
  without ever feeling like the player is running out.

### Decals on the world

Marks left on the geometry rather than as standalone entities. More efficient
than entities because they render as projected textures or stamped sprite quads.

- **Bullet holes** on walls.
- **Scorch marks** at explosion sites.
- **Blood splatters** on floors and walls (Hotline Miami again).
- **Footprints** on snow, sand, mud — Witcher 3, Death Stranding.
- **Wheel tracks** for vehicles.

Decals should fade slowly or persist until level reset. A bullet hole that
disappears in three seconds is worse than no bullet hole at all.

### State-based world changes

Larger-scale persistence: the world reflects the player's accumulated history.

- **Killed boss is dead.** Their throne room contains their corpse on
  subsequent visits.
- **Looted containers stay open.** With the lid lifted and the inventory icon
  different.
- **Burned villages stay burned.** Cleared dungeons stay cleared.
- **NPC reactions change.** Someone who saw the player commit a crime treats
  them differently next time.

This crosses into save-game design and persistence systems. The juice angle is
that the world *feels* responsive to the player — and the easiest way for a
world to feel responsive is to actually be responsive.

### Idle aliveness

The flip side of permanence. The world should not be still when the player
isn't acting on it. Salyh frames the failure as "dead stillness" — a screen
frozen between player inputs reads as broken or boring.

- **Idle animations on characters.** Boxers bobbing, soldiers shifting weight,
  cats grooming. Street Fighter's exaggerated idle stances are the canonical
  reference.
- **Background motion.** Banners flapping, smoke columns drifting, leaves
  falling, water rippling.
- **NPCs going about their lives.** Even simple AI states (walk to point A,
  idle, walk to point B) read as life.
- **Particle ambience.** See `particles.md`. Dust motes, embers, falling snow.
- **UI breathing.** Slow scale or alpha pulses on important UI elements during
  waits.

## Common mistakes

- **Pop-out disappearance.** Objects vanishing on the same frame the player
  interacts with them. Always pair with at least a sparkle, fade, or smoke
  puff. See Salyh's three patterns: sparkle-burst, fade-out, smoke-bomb.
- **Inconsistent persistence.** Some corpses stay, some vanish, some flicker
  out after a delay. The world's rules must be legible.
- **Permanence that costs gameplay.** Bullet shells with collision that block
  movement; corpses that hide loot. Decorative permanence must be decorative.
- **Frozen idle.** A character who stops dead when the player stops controlling
  them reads as a paused asset, not a person.
- **Decals that disappear at unexpected moments.** Either persist them forever
  or fade them on a clear schedule. Surprise eviction is the worst of both
  worlds.

## Implementation notes

- **Pool persistent decorative objects.** Even if you intend them to last
  forever, having a pool means you control the budget and can FIFO if needed.
- **Render them in a different layer.** Persistent decoration usually doesn't
  need per-frame physics or AI; flag and skip.
- **Don't serialize everything.** Save-game files don't need to remember every
  shell. Decide which permanence is gameplay-relevant (cleared dungeons) and
  which is purely visual (bullet shells), and persist accordingly.
