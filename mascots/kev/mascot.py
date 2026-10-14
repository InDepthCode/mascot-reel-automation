"""Kev: a waist-up cartoon guy (backwards cap, stubble, tank top), drawn in code by rigs/doodle_rig.py.

Art: sprites/ is baked by draw.py (python make.py draw kev). Change STYLE in draw.py for other looks.
"""

NAME = "Kev"

# ── Art ─────────────────────────────────────────────────────────────────────
CANVAS = (1350, 1299)   # draw.py prints these three if they change
FEET = (627, 1209)
FACE = (636, 380)
SCALE = 1.0
PLACE = (540, 1990)     # waist-up character: tuck the bottom of the shirt below the frame

# ── Voice ───────────────────────────────────────────────────────────────────
VOICE = {"provider": "say", "voice": "Eddy (English (US))", "rate": 190}
# VOICE = {"provider": "elevenlabs", "voice_id": "YOUR_VOICE_ID"}

# ── Look + behaviour ────────────────────────────────────────────────────────
STYLE = dict(background=("#0E5C63", "#0A3B44"), glow="#2DD4BF", accent="#FFD43A")
KEYWORDS = ["boom", "free", "comment", "claude"]
TRIGGERS = {"strong": ("excited", "happy", 1.2, True)}
