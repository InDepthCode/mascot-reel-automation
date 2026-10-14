# CLAUDE.md

Talking-mascot video builder. A mascot = `mascots/<name>/mascot.py` (settings) + `mascots/<name>/sprites/*.png` (art).
`python make.py` is the only entry point; run `python make.py -h` for commands.

## Pipeline

`engine/voice.py` (script -> wav) -> `engine/lipsync.py` (wav -> take.json: Rhubarb mouth cues, Whisper words,
loudness) -> `engine/animate.py` (take + sprites -> 1080x1920 mp4, multiprocessing + ffmpeg).
`engine/pack.py` loads settings with defaults; `engine/procedural.py` draws mouths/blinks for one-picture mascots;
`engine/bake.py` turns a code-drawn rig into a sprite pack; `engine/check.py` validates art and writes the model sheet
and coordinate grid.

## Rules

- Every sprite in a mascot is the same size and registration. Never resize one layer on its own.
- Verify visually: after `python make.py check NAME`, read `out/NAME/check/model_sheet.png` and `grid.png`; after a
  render, `python make.py sheet NAME <take dir> t1 t2 ...` and read `sheet.png`. Don't call a mascot done unseen.
- Keep it dependency-light: Pillow + numpy are required, everything else (Whisper, Rhubarb, Skia, ElevenLabs) must
  stay optional with a working fallback.
- Secrets live in `.env` (gitignored). Never commit `.env`, `out/` or `tools/`.
- Only use art the user owns or made. Don't recreate trademarked characters.
