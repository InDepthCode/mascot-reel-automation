"""Turn a code-drawn character into a sprite pack.

If your mascot is drawn by a function (like rigs/doodle_rig.py) instead of by hand, write a draw.py that
calls `bake()`. It renders every pose, mouth and eye state, then:
  - pose_*.png  = the full body with a resting mouth and open eyes
  - mouth_*.png = only the pixels around the mouth (found by diffing against the resting face)
  - eyes_*.png  = only the pixels around the eyes
so the engine can stack them exactly like hand-drawn layers. All layers are cropped to one shared canvas.

    bake(render, poses={...}, mouths={...}, eyes={...}, out_dir="sprites")
    render(pose_name, mouth_name, eye_name) -> (RGBA image, (feet_x, feet_y))
"""
from __future__ import annotations

import os
from typing import Callable, Dict, Tuple

from PIL import Image, ImageChops

Box = Tuple[int, int, int, int]


def _union(a: Box, b: Box) -> Box:
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _diff_box(a: Image.Image, b: Image.Image) -> Box:
    d = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 6 else 0)
    return d.getbbox()


def _patch(src: Image.Image, box: Box) -> Image.Image:
    out = Image.new("RGBA", src.size, (0, 0, 0, 0))
    out.paste(src.crop(box), box[:2])
    return out


def bake(render: Callable, poses, mouths, eyes, out_dir: str, rest_mouth="X", open_eyes="open", pad=6) -> dict:
    """Writes the pack and returns {"canvas", "feet", "face"} for mascot.py."""
    os.makedirs(out_dir, exist_ok=True)
    first = next(iter(poses))
    imgs: Dict[str, Image.Image] = {}
    feet = None
    for p in poses:
        im, feet = render(p, rest_mouth, open_eyes)
        imgs[f"pose_{p}"] = im
    base = imgs[f"pose_{first}"]

    mouth_box = None
    mouth_imgs = {}
    for m in mouths:
        im, _ = render(first, m, open_eyes)
        mouth_imgs[m] = im
        mouth_box = _union(mouth_box, _diff_box(base, im))
    eye_box = None
    eye_imgs = {}
    for e in eyes:
        im, _ = render(first, rest_mouth, e)
        eye_imgs[e] = im
        eye_box = _union(eye_box, _diff_box(base, im))

    def grow(b):
        return (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad) if b else None
    mouth_box, eye_box = grow(mouth_box), grow(eye_box)
    for m, im in mouth_imgs.items():
        imgs[f"mouth_{m}"] = _patch(im, mouth_box)
    for e, im in eye_imgs.items():
        imgs[f"eyes_{e}"] = _patch(im, eye_box)

    # one shared crop around everything that is ever drawn
    crop = None
    for im in imgs.values():
        crop = _union(crop, im.getchannel("A").getbbox())
    crop = (max(0, crop[0] - 4), max(0, crop[1] - 4), min(base.width, crop[2] + 4), min(base.height, crop[3] + 4))
    for name, im in imgs.items():
        im.crop(crop).save(os.path.join(out_dir, f"{name}.png"))
    face = ((mouth_box[0] + mouth_box[2]) / 2 - crop[0], (eye_box[1] + mouth_box[3]) / 2 - crop[1]) if eye_box else None
    return {"canvas": (crop[2] - crop[0], crop[3] - crop[1]),
            "feet": (round(feet[0] - crop[0]), round(min(feet[1], crop[3]) - crop[1])),
            "face": tuple(round(v) for v in face) if face else None}
