"""Built-in mouths and blinks for mascots that only have body art.

Drop in one picture of your mascot, set MOUTH (and optionally EYES) in mascot.py, and the engine draws
the 9 lip-sync mouth shapes and the blink lids on top of it. `cover` paints over the mouth that is already
in your picture so the two don't fight.

Each shape is drawn once at 4x and cached as a full-canvas layer, exactly like a hand-drawn sprite.
"""
from __future__ import annotations

from typing import List, Tuple

from PIL import Image, ImageChops, ImageDraw

SS = 4
Pt = Tuple[float, float]


def rgba(c, a=255):
    if isinstance(c, str):
        h = c.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)
    return tuple(c[:3]) + (c[3] if len(c) > 3 else a,)


def _quad(p0, c, p1, n=20) -> List[Pt]:
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1]) for t in (i / n for i in range(n + 1))]


def _cubic(p0, c1, c2, p1, n=24) -> List[Pt]:
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p1[0],
                    u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p1[1]))
    return out


# Mouth shapes in units where the widest open mouth ("D") is 120 wide.
# (width, height, top teeth, tongue, top-lip flatness, tongue raised)
OPEN = {
    "B": (78, 30, 10, 0.0, 0.2, False),    # K S T: teeth showing
    "C": (104, 52, 11, 0.8, 0.35, False),  # EH AE
    "D": (120, 96, 10, 1.0, 0.35, False),  # AA: wide open
    "E": (74, 74, 0, 0.6, 1.4, False),     # AO ER: round
    "F": (44, 40, 0, 0.0, 1.6, False),     # UW OW W: pucker
    "G": (92, 34, 16, 0.0, 0.1, False),    # F V: top teeth on the lip
    "H": (98, 62, 9, 0.9, 0.35, True),     # L: tongue up
    "smile": (128, 70, 12, 0.9, -0.6, False),
}


def mouth_layer(shape: str, cfg: dict, canvas: Tuple[int, int]) -> Image.Image:
    """Full-canvas RGBA layer with one mouth shape drawn at cfg['at']."""
    W, H = canvas
    mx, my = cfg["at"]
    k = cfg.get("width", 120) / 120.0          # scale of the whole mouth set
    line = rgba(cfg.get("line", "#1A1A1E"))
    lw = cfg.get("line_width", 8)
    inside, tongue, teeth = rgba(cfg.get("inside", "#5A1726")), rgba(cfg.get("tongue", "#F07A8C")), rgba(cfg.get("teeth", "#FFFFFF"))

    # work in a local box around the mouth, supersampled
    bw, bh = int(220 * k + 2 * lw), int(170 * k + 2 * lw)
    ox, oy = mx - bw / 2, my - bh * 0.42
    im = Image.new("RGBA", (bw * SS, bh * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    P = lambda x, y: ((x - ox) * SS, (y - oy) * SS)

    cover = cfg.get("cover")
    if cover:
        cw, ch = cover.get("size", (150 * k, 70 * k))
        cx, cy = cover.get("at", (mx, my))
        d.ellipse([P(cx - cw / 2, cy - ch / 2), P(cx + cw / 2, cy + ch / 2)], fill=rgba(cover["color"]))

    def stroke(pts, width):
        d.line([P(*p) for p in pts], fill=line, width=int(width * SS), joint="curve")
        r = width * SS / 2
        for p in (pts[0], pts[-1]):
            x, y = P(*p)
            d.ellipse([x - r, y - r, x + r, y + r], fill=line)

    if shape == "X":                          # rest: a small closed smile
        w = 52 * k
        pts = _quad((mx - w, my - 8 * k), (mx - w / 2, my + 20 * k), (mx, my - 2 * k)) + \
              _quad((mx, my - 2 * k), (mx + w / 2, my + 20 * k), (mx + w, my - 8 * k))[1:]
        stroke(pts, lw + 2)
    elif shape == "A":                        # M B P: lips pressed
        w = 50 * k
        stroke(_quad((mx - w, my + 2 * k), (mx, my + 14 * k), (mx + w, my + 2 * k)), lw + 4)
    else:
        w, h, tt, tg, flat, up = OPEN[shape]
        w, h, tt = w * 1.45 * k, h * 1.45 * k, tt * 1.45 * k
        x0, x1 = mx - w / 2, mx + w / 2
        top = my - h * 0.28
        outline = _quad((x0, top), (mx, top - h * flat * 0.25), (x1, top)) + \
            _cubic((x1, top), (x1 + w * 0.05, top + h * 0.75), (mx + w * 0.28, top + h), (mx, top + h))[1:] + \
            _cubic((mx, top + h), (mx - w * 0.28, top + h), (x0 - w * 0.05, top + h * 0.75), (x0, top))[1:]
        poly = [P(*p) for p in outline]
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).polygon(poly, fill=255)
        fillim = Image.new("RGBA", im.size, (0, 0, 0, 0))
        fd = ImageDraw.Draw(fillim)
        fd.polygon(poly, fill=inside)
        if tg:
            ty = top + h * (0.35 if up else 0.62)
            rx, ry = w * 0.36 * tg + 10 * k, h * 0.42
            fd.ellipse([P(mx - rx, ty + h * 0.3 - ry), P(mx + rx, ty + h * 0.3 + ry)], fill=tongue)
        if tt:
            fd.rectangle([P(x0, top - 20 * k), P(x1, top + tt)], fill=teeth)
        fillim.putalpha(ImageChops.multiply(fillim.getchannel("A"), mask))
        im.alpha_composite(fillim)
        d = ImageDraw.Draw(im)
        stroke(outline + [outline[0]], lw)

    small = im.resize((bw, bh), Image.LANCZOS)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(small, (int(round(ox)), int(round(oy))))
    return out


def eyes_layer(state: str, cfg: dict, canvas: Tuple[int, int]) -> Image.Image:
    """Blink lids drawn over the eyes already in the art. 'open' and 'wide' draw nothing."""
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    if state not in ("half", "closed", "happy"):
        return out
    rx, ry = cfg.get("size", (50, 60))
    lid, line = rgba(cfg["lid"]), rgba(cfg.get("line", "#1A1A1E"))
    lw = cfg.get("line_width", 9)
    for (x, y) in (cfg["left"], cfg["right"]):
        pad = lw + 6
        box = (int(2 * rx + 2 * pad), int(2 * ry + 2 * pad))
        im = Image.new("RGBA", (box[0] * SS, box[1] * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        cx, cy = box[0] * SS / 2, box[1] * SS / 2
        R, Ry = (rx + 4) * SS, (ry + 4) * SS
        if state == "half":
            d.pieslice([cx - R, cy - Ry, cx + R, cy + Ry], 180, 360, fill=lid)
            d.rectangle([cx - R, cy - 2 * SS, cx + R, cy], fill=lid)
            pts = _quad((cx - R, cy - 4 * SS), (cx, cy + 8 * SS), (cx + R, cy - 4 * SS))
        else:
            d.ellipse([cx - R, cy - Ry, cx + R, cy + Ry], fill=lid)
            if state == "closed":
                pts = _quad((cx - R * 0.9, cy + 4 * SS), (cx, cy + R * 0.55), (cx + R * 0.9, cy + 4 * SS))
            else:   # happy: an upside-down U
                pts = _quad((cx - R * 0.85, cy + R * 0.3), (cx, cy - R * 0.75), (cx + R * 0.85, cy + R * 0.3))
        d.line(pts, fill=line, width=int(lw * SS), joint="curve")
        for p in (pts[0], pts[-1]):
            r = lw * SS / 2
            d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=line)
        small = im.resize(box, Image.LANCZOS)
        out.alpha_composite(small, (int(x - box[0] / 2), int(y - box[1] / 2)))
    return out
