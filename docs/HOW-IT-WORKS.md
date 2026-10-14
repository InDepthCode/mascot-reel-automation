# How Claude Codes Influencers works

## The whole system

```
╔═════════════════════════════════════════════════════════════════════════════════════════════╗
║                              CLAUDE CODES INFLUENCERS                                       ║
║                    a picture + a script  ──►  a talking mascot video                        ║
╚═════════════════════════════════════════════════════════════════════════════════════════════╝

 ┌──────────────────────────── STAGE 1 · CREATE THE MASCOT (once) ───────────────────────────┐
 │                                                                                           │
 │   YOU UPLOAD                                                                              │
 │   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                                  │
 │   │ a drawing    │   │ a PNG with   │   │ reference    │                                  │
 │   │ on a plain   │   │ transparent  │   │ images of a  │                                  │
 │   │ background   │   │ background   │   │ character    │                                  │
 │   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘                                  │
 │          └────────┬─────────┘                  │                                          │
 │                   ▼                            ▼                                          │
 │   PATH A · make.py create  (2 minutes)   PATH B · Claude Code draws it  (draw-mascot)     │
 │   ┌────────────────────────────────┐     ┌────────────────────────────────────────┐       │
 │   │ 1 cut out    flat bg / alpha / │     │ Claude studies the refs: shapes,       │       │
 │   │              rembg             │     │ palette, line weight, signature parts  │       │
 │   │ 2 normalise  trim, size, pad   │     │            │                           │       │
 │   │              -> pose_idle.png  │     │            ▼                           │       │
 │   │ 3 Claude     reads it on a     │     │ writes draw.py (Skia or the PIL rig)   │       │
 │   │   pixel grid: mouth, eyes,     │     │            │                           │       │
 │   │   skin, ink, colours, voice    │     │            ▼                           │       │
 │   │ 4 Claude     checks rendered   │     │ paints every layer in code:            │       │
 │   │   mouths + blinks, nudges them │     │ 7 poses · 9 mouths · 5 eyes · ears     │       │
 │   │   (up to 3 rounds)             │     │            │                           │       │
 │   │ 5 writes mascot.py             │     │ model sheet ──► compare to refs ──┐    │       │
 │   └───────────────┬────────────────┘     │            ▲──────── fix ◄────────┘    │       │
 │                   │                      └────────────┬───────────────────────────┘       │
 │                   └──────────────┬────────────────────┘                                   │
 │                                  ▼                                                        │
 │              mascots/<name>/                                                              │
 │              ├── mascot.py    settings: canvas, feet, face, mouth, eyes, parts,           │
 │              │                voice, colours, keywords, trigger words                     │
 │              ├── sprites/     same-size transparent layers                                │
 │              │    pose_idle  pose_excited  pose_point  pose_wave_a/b  pose_shrug ...      │
 │              │    mouth_X A B C D E F G H (+smile)    eyes_open half closed happy wide    │
 │              │    ear_l  ear_r  tail ...   (anything that swings)                         │
 │              └── refs/        your original pictures                                      │
 │                                                                                           │
 │              python make.py check <name>  ──►  model_sheet.png + grid.png                 │
 └───────────────────────────────────────────────────────────────────────────────────────────┘

 ┌──────────────────────────── STAGE 2 · MAKE A VIDEO (every post) ──────────────────────────┐
 │                                                                                           │
 │   python make.py video <name> --text "Hey! Comment the word mascot..."                    │
 │                                                                                           │
 │   ① VOICE                     ② LIP SYNC                       ③ ANIMATE                  │
 │   ┌───────────────────┐       ┌──────────────────────────┐     ┌────────────────────────┐ │
 │   │ script            │       │ Rhubarb: sounds ─► mouth │     │ every frame (30 fps):  │ │
 │   │   │               │       │   "HEY"  ─►  C  D  B     │     │                        │ │
 │   │   ▼               │       │   "MOM"  ─►  A  E  A     │     │  backdrop + glow       │ │
 │   │ macOS say  (free) │ wav   │ Whisper: word timings    │take │   + swinging parts     │ │
 │   │ ElevenLabs (best) │──────►│   captions + triggers    │────►│   + pose  ◄─ trigger   │ │
 │   │ Voicebox (local)  │       │ loudness envelope        │.json│   + eyes  ◄─ blinks    │ │
 │   │ your mic  --audio │       │   bounce + jaw energy    │     │   + mouth ◄─ Rhubarb   │ │
 │   └───────────────────┘       └──────────────────────────┘     │   squash, sway, punch  │ │
 │                                                                │   + captions           │ │
 │                                                                └───────────┬────────────┘ │
 │                                                                            ▼              │
 │                                                        ffmpeg ─►  1080x1920 mp4 + audio   │
 │                                                                   out/<name>/<take>/      │
 └───────────────────────────────────────────────────────────────────────────────────────────┘

        ┌──────── one frame, back to front ────────┐       trigger words (mascot.py)
        │  ░░░░░░ gradient backdrop + glow ░░░░░░  │       "boom"    ─► excited + punch-in
        │        ╱╲        ╱╲   ◄─ ears (swing)    │       "here's"  ─► think
        │       ╭──────────────╮                   │       "crazy"   ─► shrug
        │       │   ◉      ◉   │ ◄─ eyes (blink)   │       "comment" ─► excited + punch-in
        │       │      ▽       │                   │       start     ─► wave hello
        │       │    ╰─D─╯     │ ◄─ mouth (cue)    │       end       ─► wave bye
        │   ╭───┴──────────────┴───╮               │
        │   │   pose_point  ──►    │ ◄─ pose       │
        │   ╰──────────────────────╯               │
        │      "COMMENT THE WORD"  ◄─ captions     │
        └──────────────────────────────────────────┘
```

## The 9 mouth shapes (Rhubarb Lip Sync)

```
  X rest     A  M B P     B  K S T     C  EH AE     D  AA       E  AO ER     F  OO W     G  F V      H  L
   ‿          ━━          ▭▭▭          ◠◡◠          ⬭⬭⬭          ◯            o           ▬▿▬         ◠ᵕ◠
  silence   lips shut   teeth show   open        wide open   round        pucker     teeth on    tongue up
                                                                                     lip
```

## Image prompt (for an infographic of the system)

Paste into any image model (GPT Image, Gemini, Midjourney, Ideogram) to get a poster of the pipeline:

```
A clean, modern explainer infographic poster, 16:9, titled "CLAUDE CODES INFLUENCERS" in bold rounded white
letters at the top with the subtitle "a picture + a script = a talking mascot video". Dark navy-to-indigo gradient
background with a faint dot grid, soft teal and violet glows, flat vector style with subtle depth, thick rounded
outlines, generous spacing, like a polished developer-tool landing page.

The poster reads left to right in two rows.

TOP ROW, labelled "1 · CREATE THE MASCOT": on the left, three stacked image cards labelled "drawing", "transparent
PNG" and "reference art", each showing a simple cute cartoon creature. Arrows lead into two parallel tracks. Track A,
labelled "make.py create", shows a terminal window and a magnifying-glass icon with an orange starburst (Claude)
scanning the creature's face on a pixel grid, with small markers on the mouth and eyes and a checkmark loop labelled
"checks its own work". Track B, labelled "Claude Code draws it", shows a code editor with Python code and a
paintbrush turning into a sprite sheet. Both tracks merge into a folder icon labelled "mascots/your-mascot" that
fans out into a neat sprite sheet: 7 body poses (idle, excited, pointing, waving, shrugging, thinking), a row of 9
small mouth shapes labelled X A B C D E F G H, a row of eye states (open, half, closed, happy, wide) and two
floppy ears.

BOTTOM ROW, labelled "2 · MAKE A VIDEO": a script card with the text "Hey! Comment the word mascot" flows into a
microphone icon labelled "voice: ElevenLabs · Voicebox · say", then into a waveform with tiny mouth icons under each
syllable labelled "Rhubarb lip sync + Whisper captions", then into an exploded layer stack labelled "every frame"
(backdrop, ears, body pose, eyes, mouth, captions, shown as separated transparent panes), then into a vertical
smartphone showing the cartoon creature mid-sentence with its mouth open, bold white captions with one yellow
keyword, and a play button, labelled "1080x1920 mp4".

Small footer chips: "free & open source", "fork on GitHub", "no credits". Crisp legible text, consistent icon
style, teal (#2DD4BF), violet (#6070FF) and gold (#FFD43A) accents, no photorealism, no clutter.
```

Short version (for a thumbnail or a single square image):

```
Flat vector illustration: a cute teal cartoon creature mascot steps out of a sprite sheet (a grid of its own poses
and nine mouth shapes) into a vertical phone screen, mid-sentence with its mouth open, bold white captions under
it. Behind it a terminal window reads "python make.py video". Dark indigo background, teal and gold glow, thick
rounded outlines, playful and clean, title "CLAUDE CODES INFLUENCERS".
```
