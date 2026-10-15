"""Your mascot's settings. Fill in the CHANGE ME lines, then run:  python make.py check <name>

The art lives in sprites/ next to this file (see README.md in this folder for the full list).
Smallest working mascot: ONE picture saved as sprites/pose_idle.png + the MOUTH setting below.
"""

NAME = "Amrut"

# ── Art ─────────────────────────────────────────────────────────────────────
# Every PNG in sprites/ must be the same size and line up (export each layer from the same canvas).
CANVAS = None           # None = read it from sprites/pose_idle.png
FEET = None             # (x, y) the point it stands on. None = bottom-centre of the canvas
FACE = None             # (x, y) where the camera punches in. None = 40% down the canvas
SCALE = 0.74            # on-screen size. 1.0 = one sprite pixel per video pixel (video is 1080x1920)
PLACE = (540, 1872)     # where FEET lands in the video. Raise y (e.g. 1990) to crop a waist-up character

# ── Mouth ───────────────────────────────────────────────────────────────────
# Option A (best): draw 9 mouth sprites, mouth_A.png ... mouth_H.png + mouth_X.png (README.md shows each shape).
# Option B (fast): let the engine draw them. Read the mouth position off the grid in out/<name>/check/grid.png.
MOUTH = dict(
    at=(733, 613),          # centre of the mouth, in sprite pixels
    width=165,              # how wide the widest "AH" mouth is
    line="#2A1B24",         # outline colour
    inside="#5A1726",       # inside of the mouth
    tongue="#F07A8C",
    teeth="#FFFFFF",
    line_width=8,
    # Your picture already has a mouth? Paint over it with the skin colour:
    cover=dict(color="#CA805E", size=(200, 84)),
)

# ── Eyes (optional) ─────────────────────────────────────────────────────────
# Option A: eyes_open.png, eyes_half.png, eyes_closed.png (+ eyes_happy.png, eyes_wide.png).
# Option B: blinking lids drawn over the eyes already in your picture:
EYES = dict(left=(617, 411), right=(841, 411), size=(58, 34), lid="#CB8566", line="#2A1F2A")

# ── Swinging parts (optional) ───────────────────────────────────────────────
# Ears, tails, antennae, hair: their own full-canvas PNGs, rotated about a pivot every frame.
PARTS = [
    # dict(sprite="ear_l", pivot=(505, 405), behind=True, side=-1),
    # dict(sprite="ear_r", pivot=(695, 405), behind=True, side=1),
]

# ── Voice ───────────────────────────────────────────────────────────────────
VOICE = {"provider": "clone", "ref_audio": "mascots/amrut/voice_ref.wav"}   # my cloned voice, text-only: --text
# VOICE = {"provider": "elevenlabs", "voice_id": "YOUR_VOICE_ID"}     # needs ELEVENLABS_API_KEY in .env
# VOICE = {"provider": "file"}                                        # Voicebox / your own recording: --audio

# ── Look + behaviour ────────────────────────────────────────────────────────
STYLE = dict(
    background=("#1E2126", "#2C313B"),   # gradient top / bottom
    glow="#6070FF",                       # light behind the mascot
    accent="#FFD43A",                     # caption keyword colour
    caption_y=300,
    captions=True,
)
KEYWORDS = ["free", "comment"]           # these words turn the accent colour in captions
# Spoken word -> (pose, eyes or None, seconds, camera punch-in). Poses: idle excited point wave shrug think
TRIGGERS = {
    # "boom": ("excited", "happy", 0.9, True),
}
