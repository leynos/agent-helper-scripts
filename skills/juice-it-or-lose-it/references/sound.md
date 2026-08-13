# Sound

The single highest-leverage juice category. Jonasson and Purho describe it as
"probably one of the most important parts you can add" and "the most
cost-effective thing you can add to a game to make it juicier." Their Steve
Swink demo — two circles passing through each other — perfectly illustrates:
identical visuals, but with sound the circles read as bouncing off each other
instead of passing through.

Sound communicates physicality. Without it, game objects feel like abstractions
on a screen. With it, they have weight, texture, and consequence.

Despite this, sound is "an extremely often ignored part of game development."
Treat it as a peer of art and code, not as a finishing touch.

## What every event needs

At minimum, sound on:

- **Player input that doesn't move the character** (firing, jumping in mid-air,
  ability use, menu confirmation).
- **Every collision**, varied by what hits what. A ball hitting a wall sounds
  different to a ball hitting a block.
- **State changes** (level start, level complete, death, respawn, low health,
  power-up active).
- **UI transitions** (menu open, panel slide, button hover and click).

Silence on any of these reads as broken. Players will report the game "feels
weird" without being able to identify why.

## The bass-boost trick

A widely told story (recounted by Nijman, sourced to a designer at Raven
Software): the team had an unpopular gun in a Wolfenstein game. Investors
complained about the gameplay. The designer opened the gunshot WAV in Audacity,
applied 12dB of bass boost, and saved. The investors, on next play, said the
gunplay felt great. Same bullets, same recoil, same damage — just deeper sound.

Operationalizing:

- Boost low frequencies on impact and weapon sounds (60–250Hz).
- Compress dynamic range so transients don't clip but punch hard.
- Layer a short low-frequency thump under any high-frequency snap.

This is the difference between a bullet that sounds like a typewriter and a
bullet that sounds like a gun.

## Pitch variation prevents fatigue

A single sound effect, played verbatim 100 times in a minute, becomes grating.
Three approaches to break the pattern:

1. **Random pitch variance.** Apply a small ±5–15% pitch shift each time the
   effect plays. Cheap; sufficient for most cases.
2. **Sample rotation.** Record 3–5 variants of the same effect; pick one at
   random.
3. **Rising-pitch combos.** When the same effect fires in quick succession,
   raise the pitch each time. Resets after a short silence. The Jonasson/Purho
   block-streak effect uses this; Mario's stomp-combo uses this; Peggle's brick
   streak uses this. The result reads as a melodic build that intrinsically
   rewards keeping the chain alive.

```python
# Rising-pitch combo
combo_index = 0
last_hit_time = 0
COMBO_RESET = 1.0  # seconds of silence resets the streak

def on_block_hit():
    global combo_index, last_hit_time
    if time.now() - last_hit_time > COMBO_RESET:
        combo_index = 0
    pitch = 1.0 + min(combo_index, 12) * 0.0595  # semitone steps
    play_sound("hit.wav", pitch=pitch)
    combo_index += 1
    last_hit_time = time.now()
```

## Sample selection

For prototyping, sfxr (and its descendants jsfxr, bfxr, ChipTone) is the
reference tool. Nijman: "I made those sounds in sfxr which everybody uses."
Generate quickly, iterate, replace later if needed.

When commissioning or buying real sound effects:

- **Short, punchy, pre-attack-ready.** No leading silence; the transient should
  hit on frame 1.
- **Mono unless directional matters.** Stereo positioning is the engine's job.
- **Consistent gain staging.** All hit sounds at roughly the same RMS so the
  mix doesn't whip.
- **Variants for repeated events.** Three variants minimum for any sound that
  fires more than once a minute.

## Music

Music is largely outside the scope of moment-to-moment juice, but it shapes the
perceived character of the whole. The Jonasson/Purho demo is plain right up
until music is added, at which point "it feels almost like a real game instead
of a crappy demo."

Practical notes:

- **Loop seamlessly.** Audible loop points break immersion harder than no music
  at all.
- **React to game state.** Stem-based tracks that swap layers on combat / calm
  / boss are the gold standard. A cheap version: lowpass-filter the music when
  the player is in a menu or low-health.
- **Duck for events.** Side-chain compression on the music bus, triggered by
  impactful SFX, makes hits read louder without raising their absolute volume.

## Common mistakes

- **One sound, used everywhere.** A single hit sound across all weapons,
  surfaces, and intensities reads as a placeholder.
- **Tinny, thin, low-quality samples.** Listeners can't always articulate why,
  but they hear it.
- **No variation on repeated events.** See pitch variation, above.
- **Music too loud, SFX too quiet.** SFX is the feedback channel; music is the
  mood channel. Mix accordingly: SFX should always be audible over the music in
  default settings, and the player should have independent sliders.
- **No sound on UI.** A menu button without click feedback feels like the game
  has stopped responding.

## Accessibility

- **Independent volume sliders** for music, SFX, voice, and UI.
- **Subtitles** for any voice line.
- **Visual alternatives** for purely audible cues (a flash for a low-health
  alarm; a colour change for a directional sound).

## Tools

- **sfxr / bfxr / jsfxr / ChipTone** — generative SFX prototyping.
- **Audacity** — basic editing, EQ, compression.
- **freesound.org** — Creative Commons sample library; check licences.
- **FMOD / Wwise** — middleware for adaptive audio at scale; overkill for
  prototypes.
- **Niklas-style approach** — collaborate with a sound designer early. Jonasson
  and Purho repeatedly thank Niklas in the talk; the sound effects and music
  are credited to him by name. Sound is a craft, and a dedicated practitioner
  pays for themselves quickly.
