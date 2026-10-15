"""Graphics reel + mascot tile -> a video-call style reel: the mascot is a small rounded tile (like your own tile in a
WhatsApp video call) that glides between spots on the screen while the rest of the frame shows the designed graphics.

    compose("graphics.mp4", "tile.mp4", "reel.mp4", keys=[[0, "br"], [5, "tr"], [11, "bl"]])

keys = [[seconds, spot], ...]: the tile glides to `spot` starting at that second (first entry = where it starts).
Spots sit inside the content zone (y 260-1120), clear of Instagram's top bar and caption area."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFilter

W = 1080
TOP, BOTTOM, EDGE = 260, 1120, 36     # content zone of the full-screen graphics
RADIUS, PAD = 56, 70


def spots(side: int) -> dict:
    mid_y = (TOP + BOTTOM - side) // 2
    return {"tl": (EDGE, TOP), "tr": (W - EDGE - side, TOP), "ml": (EDGE, mid_y), "mr": (W - EDGE - side, mid_y),
            "bl": (EDGE, BOTTOM - side), "br": (W - EDGE - side, BOTTOM - side)}


def default_keys(dur: float, every: float = 4.5) -> list:
    order = ["tr", "br", "bl", "tl"]
    return [[round(i * every, 2), order[i % 4]] for i in range(int(dur // every) + 1)]


def _expr(keys: list, pos: dict, axis: int, move: float = 0.55) -> str:
    """Position as an ffmpeg expression of t: the start spot plus a smoothstep glide for every move."""
    out = str(pos[keys[0][1]][axis])
    for (_, a), (t, b) in zip(keys, keys[1:]):
        d = pos[b][axis] - pos[a][axis]
        if d:
            u = f"clip((t-{t})/{move},0,1)"
            out += f"+({d})*{u}*{u}*(3-2*{u})"
    return out


def _art(side: int, d: str):
    """Soft shadow and a thin light border, drawn at 4x for smooth edges."""
    k = 4
    ring = Image.new("RGBA", (side * k, side * k), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle((0, 0, side * k - 1, side * k - 1), RADIUS * k, outline=(255, 255, 255, 215), width=5 * k)
    ring.resize((side, side), Image.LANCZOS).save(os.path.join(d, "ring.png"))
    sh = Image.new("RGBA", (side + 2 * PAD, side + 2 * PAD), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((PAD, PAD, PAD + side, PAD + side), RADIUS, fill=(0, 0, 0, 150))
    sh.filter(ImageFilter.GaussianBlur(26)).save(os.path.join(d, "shadow.png"))


def compose(graphics: str, tile: str, out: str, keys: Optional[list] = None, side: int = 360) -> str:
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", graphics],
                               capture_output=True, text=True, check=True).stdout)
    pos = spots(side)
    keys = sorted(keys or default_keys(dur), key=lambda k: k[0])
    bad = [s for _, s in keys if s not in pos]
    if bad:
        raise SystemExit(f"unknown tile spot {bad[0]!r}: use one of {', '.join(pos)}")
    x = _expr(keys, pos, 0) + "+7*sin(2*PI*t/3.7)"        # idle float, like a tile held in a hand
    y = _expr(keys, pos, 1) + "+9*sin(2*PI*t/2.9+1)"
    R = RADIUS
    alpha = (f"if(gt(abs(X-W/2),W/2-{R})*gt(abs(Y-H/2),H/2-{R}),"
             f"if(lte(hypot(abs(X-W/2)-(W/2-{R}),abs(Y-H/2)-(H/2-{R})),{R}),255,0),255)")
    with tempfile.TemporaryDirectory() as d:
        _art(side, d)
        graph = (f"[1:v]scale={side}:{side},format=yuva444p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='{alpha}'[t];"
                 f"[0:v][2:v]overlay=x='{x}-{PAD}':y='{y}-{PAD}+16'[a];"
                 f"[a][t]overlay=x='{x}':y='{y}'[b];"
                 f"[b][3:v]overlay=x='{x}':y='{y}'[v]")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", graphics, "-i", tile,
               "-loop", "1", "-framerate", "30", "-i", os.path.join(d, "shadow.png"),
               "-loop", "1", "-framerate", "30", "-i", os.path.join(d, "ring.png"),
               "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-threads", "2", "-pix_fmt", "yuv420p", "-c:a", "copy", "-t", f"{dur:.3f}", "-movflags", "+faststart", out]
        subprocess.run(cmd, check=True)
    return out
