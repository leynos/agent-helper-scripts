# Camera

The camera is the player's eye. Every adjustment to its position, target, framing, or motion shapes how the action reads. Used well, the camera amplifies impact, directs attention, and contributes more juice per line of code than almost any other channel.

Used badly, the camera induces nausea, hides important state, and breaks immersion.

## Screen shake

The headline technique. A brief, controlled jitter applied to the camera position on impactful events. The Jonasson/Purho demo demonstrates the gulf between no-shake and shake on a Breakout collision — the ball goes from "stupid tennis ball" to "motherfucking comet."

### Implementation

The cheap version: random offset per frame, decayed over time.

```python
class ScreenShake:
    def __init__(self):
        self.intensity = 0.0
        self.decay = 8.0  # higher = shorter shake

    def trigger(self, intensity):
        # Take the max so a small shake during a big shake doesn't reduce it
        self.intensity = max(self.intensity, intensity)

    def update(self, dt):
        self.intensity = max(0, self.intensity - self.decay * dt)
        return (
            random.uniform(-1, 1) * self.intensity,
            random.uniform(-1, 1) * self.intensity,
        )
```

The better version: drive the offset with Perlin or simplex noise rather than uniform random. The motion is smoother and less seizure-inducing while still reading as shake. Sample the noise function at `time * frequency`, scaled by intensity.

### Tuning

- **Intensity proportional to event weight.** Light hit: 2 pixels. Big explosion: 20 pixels. Apocalypse: more, but use the slow-mo trick to prevent the screen becoming unreadable.
- **Short duration.** 100–250ms is plenty. Longer reads as an effect rather than a reaction.
- **Decay, don't cliff.** Linear or exponential decay back to zero, not a hard cutoff.

### When to **not** use screen shake

- On every basic event. Shake on every footstep is noise.
- In games requiring sustained precision (slow puzzlers, aiming-heavy shooters).
- Without an off-toggle. Some players experience motion sickness from shake; Vlambeer added a Nuclear Throne setting for exactly this reason after playtest reports of nausea.
- For purely positive events. Shake reads as impact and aggression. A pickup wants confetti, not shake.

## Camera kick

A subtler cousin of shake, invented by Nijman for Luftrausers. On firing a weapon, shift the camera in the *opposite* direction of the shot for a single frame, then lerp back. The visual cue is identical to recoil — the world moves, so the player's gun must have pushed against it.

```python
def on_fire(direction):
    camera.kick(direction * -8)  # 8 pixels opposite the firing direction
    # camera.kick adds to a kick offset that decays back to zero
```

This compounds beautifully with knockback on the player and screen shake at the muzzle. Three small techniques, one large feeling.

## Hit-stop / hit-pause / sleep

Pause the entire game (or just the affected entities) for 30–80ms when something significant happens. The brain reads this as weight — there is more to process at this moment, so time slows.

Nijman uses a `sleep` instruction in Game Maker; in custom code it's a flag that skips the simulation for N frames while continuing to render.

```python
hit_stop_until = 0

def on_significant_hit():
    global hit_stop_until
    hit_stop_until = time.now() + 0.05  # 50ms freeze

def update(dt):
    if time.now() < hit_stop_until:
        return  # skip simulation, keep rendering
    # ... normal update ...
```

Used heavily in Street Fighter, God of War, every fighting game, and Devil May Cry. The Reddit thread on game juice mentions this as one of the most-emulated tricks. Misused, it makes a game feel sluggish — apply it only to events that genuinely deserve emphasis.

A related technique: **slow motion**, a sustained partial time-scale (typically 0.2–0.5×) lasting 200ms–2s. The dashpong goal explosion uses this. Different from hit-stop because it's longer, rendered at reduced rate rather than frozen, and usually scoped to the entire game state rather than individual entities.

## Camera lerp / smoothing

Snap-to-target cameras feel mechanical. Lerping the camera position toward the player at 5–15% per frame produces the "operated by a person" feel.

```python
camera.x += (target.x - camera.x) * 0.1 * dt * 60
camera.y += (target.y - camera.y) * 0.1 * dt * 60
```

Tune the rate per axis if needed — vertical smoothing in platformers often needs to be slower than horizontal, especially when the player is in a falling state, to avoid the camera lurching down on every drop.

## Look-ahead

Shift the camera target slightly toward the player's direction of motion or aim. The player sees more of what they're approaching and less of what they're leaving. Hotline Miami offsets the camera toward the mouse cursor for exactly this reason — the targeting reticle pulls the camera into the threat.

```python
look_ahead = player.velocity.normalised() * 80
camera_target = player.position + look_ahead
```

For a shooter where the player aims independently of motion, blend the velocity offset with the aim offset, weighting by recent activity.

## Dynamic framing

The dashpong dev describes a camera that computes the average position of all relevant objects (players + ball) and frames them, zooming in or out based on how spread apart they are. Useful for any multi-object game where the action can fragment across the playfield: party games, twin-stick co-op, tactics games.

```python
def frame_objects(objects, padding=100):
    xs = [o.x for o in objects]
    ys = [o.y for o in objects]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    span_x = (max(xs) - min(xs)) + padding * 2
    span_y = (max(ys) - min(ys)) + padding * 2
    zoom = min(screen_width / span_x, screen_height / span_y)
    return cx, cy, zoom
```

Lerp toward this target rather than snapping. Cap zoom in and out to sensible extremes.

## Replays and instant-replay highlights

If the game has discrete climactic events (goals, kills, level completions) that are easy to miss in real time, a 2–4 second replay immediately afterwards costs little and amplifies the moment substantially. The dashpong dev built this for goals — same physics buffer, camera follows the ball, time scaled. The viewer sees what they almost missed.

## Common mistakes

- **Too much screen shake.** "Add screen shake to a puzzle game and you're wrong" is a Reddit joke; in reality, screen shake on a puzzle game is just bad. Use it where impact exists.
- **Shake without an off-switch.** Inaccessibility for motion-sensitive players.
- **Camera that snaps.** Almost always worse than a smoothed camera, even at high smoothing rates that make it feel near-instant.
- **Look-ahead that overshoots.** If the camera moves too far ahead, the player's character is too close to the trailing edge of the screen and misses incoming threats.
- **Hit-stop on every event.** Stops the game from breathing; cumulative latency reads as input lag.
- **Letting the camera obscure the player.** All camera tricks must serve "can the player see what they need to see?" Lose the camera trick before losing the legibility.
