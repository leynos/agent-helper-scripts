# Personality

The Kyle Gabler maxim, lifted from World of Goo and recounted in the
Jonasson/Purho talk: **"Add eyes to anything."**

Personality is the cheapest path from "object" to "character." A blob with eyes
is a creature; a paddle with eyes is a player; a door with eyes is a
participant. The cognitive shift in the player happens immediately and is
disproportionate to the implementation effort.

## The three-element personality kit

The smallest unit of "this object is alive" is:

1. **Eyes** that track something — usually the player, the ball, the cursor, or
   the next threat.
2. **A mouth** that changes shape on emotional events — open in surprise, smile
   on success, frown on failure.
3. **Idle reactions** that play between events — blinks, weight shifts,
   anticipation poses.

Jonasson and Purho add all three to their Breakout paddle in roughly the last
minute of the demo. The paddle goes from a coloured rectangle to a creature
with feelings about its job. The investment is trivial; the return is enormous.

### Eyes that track

A pair of small black ovals on the object. Each frame, compute the angle from
the eye centre to the tracked target and offset the pupil along that vector,
capped at a small radius so it stays inside the eye.

```python
def update_eye(eye, target, max_offset=2):
    dx = target.x - eye.x
    dy = target.y - eye.y
    dist = math.hypot(dx, dy)
    if dist > 0:
        eye.pupil_x = (dx / dist) * max_offset
        eye.pupil_y = (dy / dist) * max_offset
```

The Jonasson/Purho paddle tracks the ball. It works because the eyes' attention
reinforces the player's attention — both look at the same thing, and the paddle
becomes an ally.

### Blinking

Periodically hide the eyes for one or two frames. Random interval between 2–6
seconds. The implementation is "literally setting the eye sprite invisible for
100ms" — the simplicity is its own joke.

```python
next_blink = random.uniform(2, 6)
blink_duration = 0.1
```

### Mouth shapes

A small mouth sprite or a couple of vertices. Shape changes on event:

- **Default**: small smile or neutral line.
- **Hit something**: open mouth (surprise) for 200ms.
- **Lost something**: frown — flip the smile vertically.
- **Idle**: slow breathing — sine wave on the y-scale.

The Jonasson/Purho paddle smiles when it hits the ball and frowns when the ball
escapes. Same paddle, two states, more emotional connection than most
platformer protagonists.

### Bigger eyes

The talk's last note on eyes: "make the eyes a bit bigger." Almost universal
advice in cartooning — large eyes read as more expressive, more sympathetic,
and more legible at distance. If you find yourself uncertain whether your
character's eyes are too big, they probably aren't.

## Beyond the kit

### Reactive sprites

The whole sprite reacts to events, not just the face:

- **Squash on landing.** See `movement.md` on squash and stretch.
- **Lean into motion.** Character tilts forward when running fast.
- **Recoil on damage.** Brief flinch backwards before resuming control. The
  flinch must not exceed input latency tolerance — typically <100ms — or it
  feels like the character ignored the player.
- **Anticipation poses.** Crouch before a jump, wind up before a throw.

### Personality through motion

Even without a face, motion conveys character:

- A character with bouncy walk + perky landing reads as upbeat.
- A character with heavy footfalls + slow turn reads as imposing.
- A character with quick darting movement + quick stops reads as nervous or
  precise.

Jonasson and Purho's ball — without a face — gains personality through its
rotation, scaling, stretching, and colour reactions. It feels like a
participant, not an automaton.

### Voice and call-outs

For any character with audible output, even non-verbal "ohs" and "argh"s
humanise. The dashpong dev added a voice announcement for goal events —
different reactions for "scoring spree," "domination," etc. The voice is short,
sampled, and triggered on event. The cumulative effect is a game that comments
on itself.

Caveats:

- **Don't loop voice lines.** Three to five variants minimum for any frequently
  triggered call.
- **Don't say everything.** Voice-overs that narrate every event become
  tiresome; reserve them for milestones.
- **Subtitle them.** See `sound.md` on accessibility.

## When to skip personality

Some genres benefit from objectivity, not personhood:

- **Hard puzzles.** Personality on puzzle pieces can imply they have a will of
  their own, which is misleading.
- **Realistic simulators.** Eyes on a Cessna would break the simulation tone.
- **Tools and utilities.** A spreadsheet with eyes is the wrong kind of company.

But these are exceptions. The default lean should be toward personality,
particularly for any object the player interacts with frequently.

## Common mistakes

- **Eyes that don't track.** Static eyes look dead. The minimum viable eye does
  *something* in response to game state.
- **Mouths that overact.** A mouth that opens to a full O on every event
  becomes noise. Reserve big expressions for big events.
- **Personality on hostile objects only.** Giving enemies personality but the
  player's tools none makes the world feel adversarial. Give the player's
  possessions personality too — their weapon, their pet, their UI.
- **Inconsistent personality scope.** If one paddle has eyes, both paddles need
  eyes. Mismatched personhood reads as bug.
