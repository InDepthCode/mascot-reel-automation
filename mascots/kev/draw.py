"""Kev: the doodle rig in the Family Guy-inspired style, baked into sprites/.

    python mascots/kev/draw.py            # or: python make.py draw kev

Want a different look? Change STYLE to wimpy (notebook doodle), simpsons, pokemon or anime.
Put a square PNG at mascots/kev/logo.png to print it on the tank top.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rigs"))
from bake_doodle import bake_style  # noqa: E402

STYLE = "familyguy"

if __name__ == "__main__":
    logo = os.path.join(HERE, "logo.png")
    info = bake_style(STYLE, os.path.join(HERE, "sprites"), scale=1.0, logo=logo if os.path.exists(logo) else None)
    print("sprites ->", os.path.join(HERE, "sprites"))
    print("paste into mascot.py if the size changed:", info)
