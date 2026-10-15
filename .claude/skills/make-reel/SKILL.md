---
name: make-reel
description: Turn a topic or script into a finished Instagram Reel where the mascot is a small floating video-call tile (like your own tile in a WhatsApp call) and the rest of the screen shows designed motion graphics synced to the words, with captions, SFX and -14 LUFS audio. Use when the user wants a reel, short or "a video about X" from a script, with the mascot instead of footage of themselves. Replaces talking-head-reel for mascot reels (no raw video needed).
---

# make-reel: script -> mascot video-call reel

The mascot speaks the script (cloned voice). The **whole screen** is designed graphics (pro style, full-screen "AUDIO mode").
The mascot is a ~360 px rounded tile that glides between spots on the screen. Run everything from the repo root.
`PY=.venv/bin/python`, `K=.claude/skills/make-reel/scripts`, `NAME` = the mascot (default `amrut`), `W=<take dir>/work`.

## 0. Inputs
- **Script** (the exact words). If the user only gives a topic, write it with the `reel-script` skill rules first
  (hook under 12 words, proof by 3-10 s, comment prompt at 25-30 s, share CTA). Do not invent facts; flag claims to verify.
- Optional: Instagram handle (only used if you add a CTA line), photos to show. Never block on these.
- Voice: the mascot's `VOICE` (clone needs `HF_TOKEN` in `.env`). On a quota stop (a 3 min script is ~10 parts and the free quota is small) finished parts are cached: rerun the same `take` command after the quota resets, or ask for a recording and pass `--audio`. The scene design is keyed to phrase numbers, so a stand-in voice can be used to design/preview first.

## 1. Take (voice + word timings, no video yet)
```bash
bash $K/setup.sh                                   # READY
$PY make.py take NAME --script script.txt          # prints the take dir T (voice.wav + take.json)
mkdir -p $T/work && cp script.txt $T/work/script.txt
$PY $K/probe.py $T/voice.wav $T/work               # must say mode=audio
```

## 2. Captions + timing
```bash
$PY $K/make_phrases.py $T/work/script.txt $T/work --highlight "term one,term two,..."   # prints p0..pN
$PY $K/timing_from_take.py $T/work $T                                                     # timing.json from Whisper, no espeak
```
Highlight the 1-3 key words per sentence (numbers, names, the claim). Keep the numbered phrase list in front of you.

## 3. Design (`$T/work/spec.json` + `$T/tile_path.json`)
Read `references/spec.md` (section 0 = pro style, section 8 = full-screen coordinates) and study
`assets/example_spec_pro_sip.json`. Use `"style":"pro"`, an explicit `"trim":[0,<voice duration>]` (this keeps the mascot tile
in sync), a subject-grounded 7-colour `palette`, one idea per scene, each visual appearing on the phrase it illustrates.
Show, don't repeat the captions: numbers -> `number`/`chart`, named things -> `box` + `flow`, before/after -> `chart`.

**The tile (360x360) covers one spot at a time.** Spots: `tl tr ml mr bl br`, each box inside the content zone
(y 260-1120; x 36-396 left, x 684-1044 right; rows y 260 / 510 / 760). Plan the tile path first, then design every scene so
its content stays clear of the tile's current box. Write `tile_path.json`: `[[0,"br"],[5.16,"mr"],[8.5,"tl"], ...]`
(seconds, spot; it glides there over 0.55 s). Move it on scene changes, about every 4-6 s, never mid-sentence of a key visual.
Keep headlines left-aligned (x 96) and narrow enough to miss a right-hand tile, or park the tile on the left.

```bash
$PY $K/render.py $T/work --check                         # validate; fix warnings
$PY $K/render.py $T/work --preview 1.8 4.2 7.4 ...       # stills -> $T/work/preview_sheet.jpg ; READ IT, fix, re-preview
```

## 4. Render + compose
```bash
PYTHON=$PY bash $K/run_bg.sh $T/work                      # background; poll $T/work/progress.json (~40 s for 22 s)
$PY $K/render.py $T/work --finish $T/graphics.mp4         # SFX, cleanup, -14 LUFS audio
$PY make.py tile NAME $T                                  # the mascot-only square (slow part: a few minutes, runs on 3 cores)
$PY make.py reel NAME $T $T/graphics.mp4                  # -> $T/NAME-reel.mp4
```
If you change `spec.json` after a render, delete `$T/work/segs/` first. `make.py tile` can run while the graphics render.
Then pull stills from the FINAL mp4 (`ffmpeg -ss t -i reel.mp4 -frames:v 1 ...`) at every tile position, including one
mid-glide, and READ them: tile never covers text, mouth moves, captions readable.

## 5. Report back
Output path, length, loudness, which numbers/claims come from the script and need verifying, sources, and a caption
(hook line, one line of context, comment question, 5-8 hashtags). Offer `make.py cover NAME $T "2-3 WORD QUESTION"`.

## Tile look
`engine/reel.py`: `side` (default 360, `--side`), rounded corners, light border, soft shadow, idle float. Head-and-shoulders
crop comes from the mascot (`STYLE["tile_crop"] = (x, y, size)` in `mascot.py` to adjust).

## Learned rules
(Add one-line rules here when the user gives feedback.)
- Graphics style is always `"style":"pro"` (confirmed by the user). Don't offer collage or classic unless they ask.
