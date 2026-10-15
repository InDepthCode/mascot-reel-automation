# Your mascot's art

Everything goes in `sprites/`. **Every PNG must be the same size with a transparent background, and the layers must line up.**
The easy way to get that: draw the character on one canvas in Procreate, Photoshop, Krita, Figma or Canva, put each part
on its own layer, and export each layer separately at full canvas size.

## Level 1: one picture (5 minutes)

| File | What it is |
|---|---|
| `pose_idle.png` | Your mascot, standing. |

Then set `MOUTH` in `mascot.py`. `python make.py check <name>` writes `out/<name>/check/grid.png` with pixel coordinates
over your picture, so you can read off where the mouth goes. If the picture already has a mouth drawn on it, turn on
`cover` with the skin colour so the engine's talking mouth replaces it.

Want blinking? Set `EYES` too (centre of each eye, eye size, skin colour for the lids).

## Level 2: poses

Add any of these and the mascot uses them when it hears a trigger word (see `TRIGGERS` in `mascot.py`).
Missing ones fall back to `pose_idle.png`.

| File | Used for |
|---|---|
| `pose_excited.png` | Big moments: "boom", "free", the call to action |
| `pose_point.png` | "this", "follow" |
| `pose_wave_a.png` + `pose_wave_b.png` | Hello at the start, bye at the end (two frames of the wave, it flips between them) |
| `pose_shrug.png` | "crazy", "ridiculous" |
| `pose_think.png` | "here's" |

Pose layers should have **no mouth and no eyes** if you also draw mouth and eye sprites (Level 3). If you use the
built-in mouth instead, leave the eyes in and skip the mouth.

## Level 3: hand-drawn mouths (best lip sync)

Nine mouths, named after the shapes Rhubarb Lip Sync outputs. Draw only the mouth on each layer, in the same spot.

| File | Shape | Sounds |
|---|---|---|
| `mouth_X.png` | Resting, closed | silence |
| `mouth_A.png` | Lips pressed together | **M, B, P** |
| `mouth_B.png` | Slightly open, teeth together | **K, S, T**, most consonants |
| `mouth_C.png` | Open | **EH, AE** (b**e**d, c**a**t) |
| `mouth_D.png` | Wide open | **AA** (f**a**ther) |
| `mouth_E.png` | Rounded, slightly open | **AO, ER** (**o**ff, b**ir**d) |
| `mouth_F.png` | Puckered | **UW, OW, W** (y**ou**, sh**ow**) |
| `mouth_G.png` | Top teeth on the bottom lip | **F, V** |
| `mouth_H.png` | Open, tongue up behind the teeth | **L** |
| `mouth_smile.png` | Optional happy rest mouth | silence while waving or excited |

Look at `../sparky/sprites/` or run `python make.py check sparky` to see a full set.

## Level 3: hand-drawn eyes

| File | |
|---|---|
| `eyes_open.png` | normal |
| `eyes_half.png` | mid-blink, and the "hmm" look |
| `eyes_closed.png` | blink |
| `eyes_happy.png` | optional: ^ ^ eyes on excited beats |
| `eyes_wide.png` | optional: shocked |

## Extra: swinging parts

Ears, tails, antennae and hair can be their own layers. List them in `PARTS` with a pivot point (where they attach) and
they sway, flick on every pose change and bounce with the voice. `behind=True` draws them behind the body.

## Code-drawn mascots

If you would rather draw the character in code, add a `draw.py` that writes these same PNGs into `sprites/`
(see `../sparky/draw.py` for Skia, `../kev/draw.py` for a full rig with `engine/bake.py`). `python make.py draw <name>`
runs it.
