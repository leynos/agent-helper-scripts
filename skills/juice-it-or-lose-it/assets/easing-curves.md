# Easing Curves Cheatsheet

The Robert Penner equations (2002), which are the de facto standard for tween
easing in games and UI. Most engines and tween libraries ship them under these
exact names.

`t` is a normalized time in `[0, 1]`. The function returns the eased progress,
also in `[0, 1]`. Multiply by your value range to get position/scale/alpha.

## Naming convention

- `easeIn{Curve}`: starts slow, ends fast. Acceleration. Good for departures.
- `easeOut{Curve}`: starts fast, ends slow. Deceleration. Good for arrivals.
- `easeInOut{Curve}`: slow at both ends, fast in the middle. Good for
  transitions.

## Reference table

| Curve            | When to reach for it                                                          |
| ---------------- | ----------------------------------------------------------------------------- |
| `easeInOutSine`  | Subtlest. Smooth fades, gentle UI transitions.                                |
| `easeOutSine`    | Soft arrivals where you don't want to draw attention.                         |
| `easeOutQuad`    | Default for most arrivals. Lightweight.                                       |
| `easeOutCubic`   | Slightly punchier arrival. The general-purpose workhorse.                     |
| `easeOutQuart`   | Snappy arrival. UI panels, modals.                                            |
| `easeOutQuint`   | Very snappy. Almost feels like a snap with a tail.                            |
| `easeOutExpo`    | Hardest of the standard easings. Sudden reveals, alerts.                      |
| `easeOutBack`    | Overshoots target then settles. Adds confidence. Pickups, dialogue popups.    |
| `easeOutElastic` | Oscillates around target. Toy-like. Cartoonish UI; risky in serious contexts. |
| `easeOutBounce`  | Simulates ball coming to rest. Excellent for objects landing on a surface.    |
| `easeInQuad`     | Default for departures.                                                       |
| `easeInCubic`    | Sharper departure.                                                            |
| `easeInBack`     | Pulls back before launching forward — anticipation.                           |

## Implementations

```python
import math

def ease_in_sine(t):
    return 1 - math.cos((t * math.pi) / 2)

def ease_out_sine(t):
    return math.sin((t * math.pi) / 2)

def ease_in_out_sine(t):
    return -(math.cos(math.pi * t) - 1) / 2

def ease_in_quad(t):
    return t * t

def ease_out_quad(t):
    return 1 - (1 - t) * (1 - t)

def ease_in_out_quad(t):
    return 2 * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 2) / 2

def ease_in_cubic(t):
    return t ** 3

def ease_out_cubic(t):
    return 1 - (1 - t) ** 3

def ease_in_out_cubic(t):
    return 4 * t ** 3 if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2

def ease_out_quart(t):
    return 1 - (1 - t) ** 4

def ease_out_quint(t):
    return 1 - (1 - t) ** 5

def ease_out_expo(t):
    return 1 if t == 1 else 1 - 2 ** (-10 * t)

def ease_out_back(t, overshoot=1.70158):
    c1 = overshoot
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

def ease_out_elastic(t):
    c4 = (2 * math.pi) / 3
    if t == 0: return 0
    if t == 1: return 1
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * c4) + 1

def ease_out_bounce(t):
    n1 = 7.5625
    d1 = 2.75
    if t < 1 / d1:
        return n1 * t * t
    elif t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    elif t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    else:
        t -= 2.625 / d1
        return n1 * t * t + 0.984375
```

## Usage skeleton

```python
def tween(obj, prop, start, end, duration, ease=ease_out_cubic):
    """Generator-style tween. Yields each frame's value."""
    elapsed = 0
    while elapsed < duration:
        t = elapsed / duration
        eased = ease(t)
        setattr(obj, prop, start + (end - start) * eased)
        elapsed += yield  # caller sends dt
    setattr(obj, prop, end)
```

In a real game, use the engine's tween library — they handle cancellation,
chaining, looping, callbacks, frame-rate independence, and edge cases.
Hand-rolling tween infrastructure is its own programmer trap.

## Visual reference

The full grid of curve shapes (the `easeIn*` / `easeOut*` / `easeInOut*`
variants of each family) is at <https://easings.net> with live previews and
code in multiple languages.

## Tuning notes

- **Duration matters more than curve.** Most "wrong-feeling" tweens are too
  slow, not the wrong curve. Try 200–400ms first; only reach for sub-200ms if
  the action is repetitive (combat hits) or super-200ms if it's narratively
  significant.
- **Match curve to physics.** An object falling under gravity follows
  `easeInQuad` (acceleration). An object decelerating to a stop follows
  `easeOut*`. Picking the curve that matches the implied physics costs nothing
  and reads as natural.
- **Overshoot sparingly.** `easeOutBack` and `easeOutElastic` are delicious in
  small doses and exhausting in large ones. Reserve for events the player
  should celebrate or notice.
- **InOut for transitions, Out for arrivals, In for departures.** A useful
  default mapping.
