"""Bake the doodle rig (doodle_rig.py + doodle_styles.py) into a sprite pack for one art style.

Used by mascots/kev/draw.py and mascots/anime/draw.py. Styles: wimpy, familyguy, simpsons, pokemon, anime.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import doodle_rig as R            # noqa: E402
import doodle_styles as S         # noqa: E402
from doodle_rig import Arm, Mouth, State  # noqa: E402
from engine.bake import bake      # noqa: E402

A = R.ARM_POSES
# engine pose name -> (screen-left arm, screen-right arm). Never both hands overhead: it reads badly.
POSES = {
    "idle": (A["rest"], A["rest"]),
    "excited": (A["flex"], A["flex"]),
    "point": (A["rest"], A["point_side"]),
    "wave_a": (A["rest"], A["wave"]),
    "wave_b": (A["rest"], Arm(80, 146, "open")),
    "shrug": (A["open_low"], A["open_low"]),
    "think": (A["hips"], A["point_up"]),
}
V = R.VISEMES
# Rhubarb mouth letter -> the rig's mouth shape
MOUTHS = {
    "X": V["rest"], "A": V["MBP"], "B": V["C"], "C": V["E"], "D": V["A"], "E": V["O"], "F": V["U"],
    "G": V["FV"], "H": V["L"],
    "smile": Mouth(w=58, h=36, up=0.18, teeth=1.0, tongue=0.45, smile=1.0),
}
EYES = {
    "open": dict(),
    "half": dict(blink=0.45),
    "closed": dict(blink=1.0),
    "happy": dict(blink=0.8, brow=0.5),
    "wide": dict(lid=0.0, brow=0.8),
}


def bake_style(style: str, out_dir: str, scale: float = 1.0, logo: str = None) -> dict:
    R.LOGO = logo

    def render(pose, mouth, eyes):
        l, r = POSES[pose]
        st = State(armL=l, armR=r, mouth=MOUTHS[mouth], boil=0, **EYES[eyes])
        return S.draw(st, scale, style, sticker=True)

    return bake(render, POSES, MOUTHS, EYES, out_dir)
