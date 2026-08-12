# Movement & Tweening

The first and broadest channel of juice. Anything that moves over time —
position, scale, rotation, alpha, colour — should move with intent, not at
constant velocity.

## The lazy lerp

Before reaching for a tween library, the cheapest possible easing is the
framewise interpolation:

```python
# Move 10% of the remaining distance every frame.
# Fast at first, asymptotically slow at the end. Costs nothing.
x += (target_x - x) * 0.1
```

This is what Jonasson and Purho describe as "this baby right here" in the talk
— a one-liner that turns linear motion into something that feels alive. The
constant (here `0.1`) tunes responsiveness. Higher values snap faster; lower
values feel heavier. For frame-rate independence, multiply by `dt * rate`
instead of using a fixed factor.

Use the lazy lerp when you need feel-good motion now and don't want a
dependency. Use a proper tween library when you need timing precision,
multi-stage choreography, or specific easing curves.

## Easing curves

Robert Penner's 2002 equations are still the standard. The names follow the
pattern `ease{In|Out|InOut}{Curve}`:

- **`In`**: starts slow, ends fast. Useful for departures and disappearances.
- **`Out`**: starts fast, ends slow. Useful for arrivals — feels like
  deceleration into rest.
- **`InOut`**: slow at both ends, fast in the middle. Useful for transitions
  where both ends matter.

Common curves, from gentle to aggressive:

- **Sine**: subtlest. Use when motion should be felt but not noticed.
- **Quad / Cubic / Quart / Quint**: progressively sharper polynomials. Cubic is
  the workhorse default.
- **Expo**: very sharp; almost a snap with anticipation. Use for sudden reveals.
- **Back**: overshoots the target then settles. Adds confidence and luxury —
  Jonasson and Purho call this "very luxurious." Use sparingly for arrivals.
- **Elastic**: oscillates around the target. Toy-like; great for cartoonish UI,
  dangerous for combat.
- **Bounce**: simulates a ball coming to rest. The talk's "crazy one." Great
  for arrivals of physical-feeling objects.

Reference cheatsheet of the curve shapes: `assets/easing-curves.md`.

## When to use which curve

| Situation                               | Recommended curve                         |
| --------------------------------------- | ----------------------------------------- |
| Object enters the scene from off-screen | `easeOutCubic` or `easeOutBack`           |
| Object exits the scene                  | `easeInCubic` or `easeInQuad`             |
| Modal panel opens                       | `easeOutQuart`                            |
| Damage number floats up and fades       | `easeOutQuad` (position) + linear (alpha) |
| Pickup pops on collection               | `easeOutBack` (scale)                     |
| Camera settles to new target            | `easeOutCubic`                            |
| Game-paused dim overlay                 | `easeInOutSine`                           |
| Cartoon character lands                 | `easeOutBounce`                           |

Avoid `linear` unless you have a reason — constant velocity reads as
mechanical. The exception: tiling backgrounds, conveyor belts, anything that is
genuinely uniform motion.

## Squash and stretch

Animation principle borrowed wholesale from Disney. Objects deform along their
motion axis to communicate velocity, anticipation, and impact.

**On the playfield:**

- Paddle stretches horizontally as the player drags it; squashes vertically.
  Magnitude proportional to mouse-offset velocity.
- Ball stretches along its velocity vector. More dramatic with gravity; subtle
  without.
- Ball briefly scales up on collision, then eases back via `easeOutBack` or
  `easeOutElastic`.
- Character squashes vertically on landing, then stretches as it rebounds.

**For UI:**

- Buttons squash slightly when pressed (~0.95× scale, 50ms `easeOutQuad`).
- Icons stretch vertically when picked up for drag.

The rule: **conserve volume**. If something stretches in X by 20%, squash it in
Y by ~17% (`1 / 1.2`) so it doesn't appear to gain or lose mass.

## Stagger and random delay

When several elements tween in together, give each a small randomised offset
(typically 30–150ms). This breaks visual unison and reads as organic. Jonasson
and Purho stagger their block grid this way for the level intro — the same
animation with stagger looks orders of magnitude better than without.

```python
for i, block in enumerate(blocks):
    delay = i * 0.04 + random.uniform(0, 0.08)
    block.tween_to(target, duration=0.6, ease=ease_out_back, delay=delay)
```

## Anticipation and follow-through

Two more Disney principles that map directly to juice:

- **Anticipation**: a small reverse motion before the main action. The
  character crouches before jumping; the gun pulls back before firing.
  Communicates intent and adds weight. Bloodborne uses this aggressively to
  make slow weapons feel responsive — the wind-up animation may be slow, but
  the *first frame* snaps into a new pose.
- **Follow-through**: motion continues after the main action ends. Gun barrel
  keeps wobbling after the shot; cape flutters after the jump lands. Salyh's
  piece on Marvel's Avengers counts seven follow-through effects on a single
  hammer swing.

## Colour and alpha tweens

Often forgotten. Examples that punch above their weight:

- **Hit flash**: target sprite goes pure white for one frame, then eases back
  to its base colour over ~150ms. Universally legible as "got hit."
- **Damage tint**: the player's screen edges tint red for a second when they
  take damage. Ease in over 100ms, ease out over 800ms.
- **Pickup glow**: collectibles pulse alpha or scale on a sine loop, drawing
  the eye.
- **Death fade**: enemy sprite fades to alpha 0 over 300ms while drifting
  upward.

## Lerping the camera, not the world

Lurp/lerp the camera target rather than snapping it. The camera follows the
player at, say, 0.1 of the distance per frame — the world feels weighty, the
camera feels operated by a person. Layer this with look-ahead (camera shifts
toward the direction of motion or aim) and you get the Vlambeer / Hotline Miami
feel for free.

## Implementation notes

- **Frame-rate independence.** All tweens should use elapsed time (dt), not
  frame counts. Browser tabs and 144Hz displays will expose any frame-counted
  tween.
- **Cancellable tweens.** A new tween on the same property should override or
  blend with the in-flight one, not stack.
- **No tweening for input-driven motion.** Player movement should be 1:1 with
  input. Tweens are for autonomous motion. The player will fight against any
  easing curve you put between their stick and their character.
