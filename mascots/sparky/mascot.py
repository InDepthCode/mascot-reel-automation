"""Sparky: teal electric creature. Hand-off-able example of a fully drawn sprite pack.

Art: sprites/ (made by draw.py, every layer 1200x1500 on the same registration).
"""

NAME = "Sparky"

# ── Art ─────────────────────────────────────────────────────────────────────
CANVAS = (1200, 1500)   # every PNG in sprites/ is exactly this size
FEET = (600, 1395)      # the point it stands on (sprite pixels)
FACE = (600, 680)       # where the camera punches in
SCALE = 0.98            # on-screen size: 1.0 = one sprite pixel per video pixel (video is 1080x1920)
PLACE = (540, 1872)     # where FEET lands in the video frame

# Parts that swing on their own (rotate about a pivot, kick on every pose change).
PARTS = [
    dict(sprite="ear_l", pivot=(505, 405), behind=True, side=-1),
    dict(sprite="ear_r", pivot=(695, 405), behind=True, side=1),
]

# ── Voice ───────────────────────────────────────────────────────────────────
# Zero-setup macOS voice, pitched up for a cartoon sound:
VOICE = {"provider": "say", "voice": "Samantha", "rate": 200, "pitch": 1.3}
# Better: an ElevenLabs voice (python make.py design-voice sparky "..." makes a brand-new one):
# VOICE = {"provider": "elevenlabs", "voice_id": "YOUR_VOICE_ID"}

# ── Look + behaviour ────────────────────────────────────────────────────────
STYLE = dict(background=("#1E2126", "#2C313B"), glow="#6070FF", accent="#FFD43A")
KEYWORDS = ["boom", "free", "comment", "ridiculous"]      # gold in the captions
TRIGGERS = {"hey": ("wave", None, 1.0, False)}            # word -> (pose, eyes, seconds, punch-in)
