"""Loads a mascot: mascots/<name>/mascot.py (settings) + mascots/<name>/sprites/*.png (art).

Every setting has a default, so a mascot.py can be as short as NAME + CANVAS + FEET.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASCOTS = os.path.join(ROOT, "mascots")

MOUTH_SHAPES = ["X", "A", "B", "C", "D", "E", "F", "G", "H"]   # Rhubarb Lip Sync's mouth set
EYE_STATES = ["open", "half", "closed", "happy", "wide"]
POSE_NAMES = ["idle", "excited", "point", "wave_a", "wave_b", "shrug", "think"]

DEFAULT_TRIGGERS = {
    # spoken word -> (pose, eyes or None, seconds held, camera punch-in)
    "boom": ("excited", "happy", 0.9, True),
    "wow": ("excited", "wide", 0.9, True),
    "insane": ("shrug", "wide", 1.0, True),
    "crazy": ("shrug", "wide", 1.0, True),
    "ridiculous": ("shrug", "half", 0.9, False),
    "here's": ("think", "half", 1.0, False),
    "this": ("point", None, 0.8, False),
    "free": ("excited", "happy", 0.9, True),
    "comment": ("excited", "happy", 1.4, True),
    "follow": ("point", None, 1.0, False),
}

DEFAULT_STYLE = dict(
    background=("#1E2126", "#2C313B"),   # top / bottom of the backdrop gradient
    glow="#6070FF",                       # soft light behind the mascot
    dots=True,                            # faint dot grid
    accent="#FFD43A",                     # caption keyword colour
    caption_y=300,                        # caption baseline from the top of a 1080x1920 frame
    caption_size=92,
    caption_words=3,                      # words per caption group
    captions=True,
    card_box=None,                        # (x0, y0, x1, y1) of the info cards. None = under the chin, above the Instagram buttons
)


@dataclass
class Mascot:
    name: str
    folder: str
    canvas: Tuple[int, int]
    feet: Tuple[float, float]
    face: Tuple[float, float]
    scale: float = 1.0
    place: Tuple[float, float] = (540, 1872)
    mouth: Optional[dict] = None
    eyes: Optional[dict] = None
    parts: List[dict] = field(default_factory=list)
    triggers: Dict[str, tuple] = field(default_factory=dict)
    keywords: List[str] = field(default_factory=list)
    style: dict = field(default_factory=dict)
    voice: dict = field(default_factory=dict)
    smile_poses: List[str] = field(default_factory=lambda: ["excited", "wave_a", "wave_b"])

    @property
    def sprites(self) -> str:
        return os.path.join(self.folder, "sprites")

    def has(self, sprite: str) -> bool:
        return os.path.exists(os.path.join(self.sprites, f"{sprite}.png"))

    def poses(self) -> List[str]:
        return sorted(f[5:-4] for f in os.listdir(self.sprites) if f.startswith("pose_") and f.endswith(".png"))

    def pose(self, name: str) -> str:
        """Sprite name for a pose, falling back so a mascot with only pose_idle.png still works."""
        chain = {"wave_a": ["wave_a", "wave", "wave_b"], "wave_b": ["wave_b", "wave_a", "wave"]}.get(name, [name])
        for n in chain + ["idle"]:
            if self.has(f"pose_{n}"):
                return f"pose_{n}"
        raise FileNotFoundError(f"{self.sprites}/pose_idle.png is missing (every mascot needs at least that one)")

    @property
    def sprite_mouths(self) -> bool:
        return all(self.has(f"mouth_{m}") for m in MOUTH_SHAPES)

    @property
    def sprite_eyes(self) -> bool:
        return all(self.has(f"eyes_{e}") for e in ("open", "half", "closed"))

    def image(self, sprite: str) -> Image.Image:
        return Image.open(os.path.join(self.sprites, f"{sprite}.png")).convert("RGBA")


def folder_of(name_or_path: str) -> str:
    if os.path.isdir(name_or_path):
        return os.path.abspath(name_or_path)
    path = os.path.join(MASCOTS, name_or_path)
    if not os.path.isdir(path):
        have = ", ".join(sorted(d for d in os.listdir(MASCOTS) if not d.startswith("_")))
        raise SystemExit(f"No mascot called '{name_or_path}'. You have: {have}. Make one with: python make.py new {name_or_path}")
    return path


def load(name_or_path: str) -> Mascot:
    folder = folder_of(name_or_path)
    spec = importlib.util.spec_from_file_location("mascot_settings", os.path.join(folder, "mascot.py"))
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    g = lambda k, d=None: getattr(cfg, k, d)
    canvas = g("CANVAS")
    if not canvas:
        idle = os.path.join(folder, "sprites", "pose_idle.png")
        canvas = Image.open(idle).size if os.path.exists(idle) else (1200, 1500)
    canvas = tuple(canvas)
    return Mascot(
        name=g("NAME", os.path.basename(folder)),
        folder=folder,
        canvas=canvas,
        feet=tuple(g("FEET") or (canvas[0] / 2, canvas[1])),
        face=tuple(g("FACE") or (canvas[0] / 2, canvas[1] * 0.4)),
        scale=float(g("SCALE", 1.0)),
        place=tuple(g("PLACE") or (540, 1872)),
        mouth=g("MOUTH"),
        eyes=g("EYES"),
        parts=list(g("PARTS", [])),
        triggers={**DEFAULT_TRIGGERS, **g("TRIGGERS", {})},
        keywords=[k.lower() for k in g("KEYWORDS", [])],
        style={**DEFAULT_STYLE, **g("STYLE", {})},
        voice=dict(g("VOICE", {"provider": "say"})),
        smile_poses=list(g("SMILE_POSES", ["excited", "wave_a", "wave_b"])),
    )
