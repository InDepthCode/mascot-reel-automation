"""`python make.py check NAME`: is the art complete and lined up? Writes a model sheet and a coordinate grid."""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from . import pack
from .animate import FONTS, Scene

GOOD, WARN, BAD = "  ok  ", "  --  ", "  !!  "


def run(name: str, out: str) -> bool:
    m = pack.load(name)
    os.makedirs(out, exist_ok=True)
    ok = True
    print(f"{m.name}  ({m.folder})")
    print(f"  canvas {m.canvas[0]}x{m.canvas[1]}  feet {m.feet}  face {m.face}  scale {m.scale}")

    if not m.has("pose_idle"):
        print(BAD + "sprites/pose_idle.png is missing. Every mascot needs it.")
        return False
    for f in sorted(os.listdir(m.sprites)):
        if f.endswith(".png"):
            size = Image.open(os.path.join(m.sprites, f)).size
            if size != tuple(m.canvas):
                print(BAD + f"{f} is {size[0]}x{size[1]}, expected {m.canvas[0]}x{m.canvas[1]}")
                ok = False
    poses = m.poses()
    missing = [p for p in pack.POSE_NAMES if p not in poses and not (p.startswith("wave") and "wave" in poses)]
    print(GOOD + f"poses: {', '.join(poses)}")
    if missing:
        print(WARN + f"no {', '.join(missing)}: those beats will use idle (fine, just less lively)")

    if m.sprite_mouths:
        print(GOOD + "mouths: drawn sprites A-H + X" + (" + smile" if m.has("mouth_smile") else ""))
    elif m.mouth:
        print(GOOD + f"mouths: built-in, drawn at {m.mouth['at']} (width {m.mouth.get('width', 120)})")
    else:
        print(BAD + "no mouth: add mouth_A..H + mouth_X sprites, or set MOUTH in mascot.py")
        ok = False
    if m.sprite_eyes:
        print(GOOD + "eyes: drawn sprites")
    elif m.eyes:
        print(GOOD + "eyes: built-in blinking lids")
    else:
        print(WARN + "no blinking (optional: eyes_open/half/closed sprites or EYES in mascot.py)")
    for p in m.parts:
        if not m.has(p["sprite"]):
            print(BAD + f"PARTS lists {p['sprite']}.png but it is not in sprites/")
            ok = False

    _grid(m, os.path.join(out, "grid.png"))
    if ok:
        _sheet(m, os.path.join(out, "model_sheet.png"))
    return ok


def _layer(s: Scene, pose: str, eyes: str, mouth: str) -> Image.Image:
    m = s.m
    im = Image.new("RGBA", m.canvas, (0, 0, 0, 0))
    for p in m.parts:
        if p.get("behind", True):
            im.alpha_composite(m.image(p["sprite"]))
    im.alpha_composite(m.image(m.pose(pose)))
    for name in (f"eyes_{eyes}", f"mouth_{mouth}"):
        s.sw, s.sh = m.canvas
        s._spr.pop(name, None)
        im.alpha_composite(s.spr(name))
    for p in m.parts:
        if not p.get("behind", True):
            im.alpha_composite(m.image(p["sprite"]))
    return im


class _Stub(Scene):
    """A Scene with no take, just to reuse the sprite loader."""

    def __init__(self, m):
        self.m, self._spr, self.k = m, {}, 1.0
        self.sw, self.sh = m.canvas


def _sheet(m: pack.Mascot, path: str):
    s = _Stub(m)
    font = ImageFont.truetype(os.path.join(FONTS, "Oswald-Bold.ttf"), 26)
    bg = (34, 37, 42)
    tw = 400
    th = int(tw * m.canvas[1] / m.canvas[0])
    combos = [("idle", "open", "X"), ("excited", "happy", "smile"), ("point", "open", "D"),
              ("wave_a", "open", "smile"), ("shrug", "half", "C"), ("think", "half", "A")]
    names = ["X", "A", "B", "C", "D", "E", "F", "G", "H"]
    cw = tw * 3 // len(names)
    fx, fy = m.face
    half = int(min(m.canvas) * 0.2)
    face_box = (int(fx - half), int(fy - half * 1.05), int(fx + half), int(fy + half * 0.95))
    fh = int(cw * (face_box[3] - face_box[1]) / (face_box[2] - face_box[0]))
    sheet = Image.new("RGB", (tw * 3, th * 2 + fh + 80), bg)
    d = ImageDraw.Draw(sheet)
    for i, (pose, eyes, mouth) in enumerate(combos):
        im = _layer(s, pose, eyes, mouth).resize((tw, th), Image.LANCZOS)
        x, y = (i % 3) * tw, (i // 3) * th
        sheet.paste(im, (x, y), im)
        d.text((x + 14, y + 10), m.pose(pose)[5:].upper(), font=font, fill=(160, 166, 176))
    y0 = th * 2 + 20
    for i, mo in enumerate(names):
        face = _layer(s, "idle", "open", mo).crop(face_box).resize((cw - 6, fh), Image.LANCZOS)
        sheet.paste(face, (i * cw + 3, y0 + 34), face)
        d.text((i * cw + 10, y0), mo, font=font, fill=(160, 166, 176))
    sheet.save(path)


def _grid(m: pack.Mascot, path: str):
    """pose_idle on a labelled 50 px grid, plus where FEET / FACE / MOUTH / EYES currently point."""
    im = Image.new("RGBA", m.canvas, (58, 62, 70, 255))
    im.alpha_composite(m.image("pose_idle"))
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(os.path.join(FONTS, "Oswald-Bold.ttf"), 18)
    W, H = m.canvas
    for x in range(0, W, 50):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 70 if x % 100 else 130), width=1)
        if x % 100 == 0:
            d.text((x + 3, 3), str(x), font=font, fill=(255, 230, 120))
    for y in range(0, H, 50):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 70 if y % 100 else 130), width=1)
        if y % 100 == 0:
            d.text((3, y + 2), str(y), font=font, fill=(255, 230, 120))

    def mark(pt, label, col):
        x, y = pt
        d.ellipse([x - 9, y - 9, x + 9, y + 9], outline=col, width=4)
        d.text((x + 13, y - 12), label, font=font, fill=col, stroke_width=2, stroke_fill=(0, 0, 0))
    mark(m.feet, "FEET", (90, 255, 140))
    mark(m.face, "FACE", (120, 200, 255))
    if m.mouth and not m.sprite_mouths:
        mark(m.mouth["at"], "MOUTH", (255, 110, 140))
    if m.eyes and not m.sprite_eyes:
        mark(m.eyes["left"], "EYE L", (255, 170, 60))
        mark(m.eyes["right"], "EYE R", (255, 170, 60))
    im.convert("RGB").save(path)
