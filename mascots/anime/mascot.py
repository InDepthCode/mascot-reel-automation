"""Anime: the same code-drawn rig as Kev in a modern anime style (rigs/doodle_styles.py "anime").

Art: sprites/ is baked by draw.py (python make.py draw anime).
"""

NAME = "Anime"

# ── Art ─────────────────────────────────────────────────────────────────────
CANVAS = (1348, 1304)
FEET = (626, 1214)
FACE = (640, 376)
SCALE = 1.0
PLACE = (540, 1990)

# ── Voice ───────────────────────────────────────────────────────────────────
VOICE = {"provider": "say", "voice": "Eddy (English (US))", "rate": 195}
# VOICE = {"provider": "elevenlabs", "voice_id": "YOUR_VOICE_ID"}

# ── Look + behaviour ────────────────────────────────────────────────────────
STYLE = dict(background=("#2A2050", "#46306E"), glow="#FF70B0", accent="#7FE9FF")
KEYWORDS = ["boom", "free", "comment", "anime"]
