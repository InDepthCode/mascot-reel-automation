"""Sparky: a teal electric creature, every part drawn in code with Skia.

Every part is drawn on the SAME canvas (W x H) in the same coordinates, so the
compositor only alpha-stacks layers: ears -> pose (body, arms, blank face) ->
eyes -> mouth. Vector paths are rendered with Skia (anti-aliased, gradients,
blur), saved as transparent PNGs.

    pip install skia-python
    python mascots/sparky/draw.py        # or: python make.py draw sparky  -> sprites/*.png

The sprites are already committed, so you only need Skia to change the art. Edit the colours below,
re-run, then `python make.py check sparky` to see the model sheet. Put a square PNG at
mascots/sparky/logo.png to swap the lightning badge on the collar for your own logo.
"""
import math
import os

import numpy as np
import skia
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sprites")
ICON = os.path.join(HERE, "logo.png")   # optional; without it the collar tag shows a lightning bolt

W, H = 1200, 1500
CX = 600


def C(hexs, a=255):
    h = hexs.lstrip("#")
    return skia.Color(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


YEL = "#33D6C4"  # body colour (YEL_* = the body ramp: base, shade, deep shade, highlight)
YEL_SH = "#16A99A"
YEL_DEEP = "#0C7D73"
YEL_HI = "#C8FFF7"
BELLY = "#A9F6EB"
OUT_C = "#0A2A30"
TEAL = "#2DD4BF"
TEAL_SH = "#0E9C8A"
TEAL_HI = "#A7F7EC"
TIP, TIP_SH, TIP_HI = "#1B2340", "#0E1428", "#6170A0"   # Pikachu-style dark ear tips
CHEEK, CHEEK_SH, CHEEK_LT = "#FF6B7D", "#D9435A", "#FFB0BA"  # coral cheeks
GOLD, GOLD_HI = "#FFD43A", "#FFF3B0"                        # collar
MOUTH = "#5A1726"
TONGUE = "#F07A8C"
EYE = "#24150D"
EYE_MID = "#1F3B4A"

LINE = 9  # main outline width


# ── geometry helpers ─────────────────────────────────────────────────────────

def blob(pts, closed=True, tension=1.0):
    """Smooth path through points (Catmull-Rom -> cubic Bezier)."""
    p = skia.Path()
    n = len(pts)
    p.moveTo(*pts[0])
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n] if closed or i > 0 else pts[i]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if closed or i + 2 < n else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6 * tension, p1[1] + (p2[1] - p0[1]) / 6 * tension)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6 * tension, p2[1] - (p3[1] - p1[1]) / 6 * tension)
        p.cubicTo(*c1, *c2, *p2)
    if closed:
        p.close()
    return p


def oval(cx, cy, rx, ry):
    p = skia.Path()
    p.addOval(skia.Rect.MakeLTRB(cx - rx, cy - ry, cx + rx, cy + ry))
    return p


def shifted(path, dx, dy):
    q = skia.Path(path)
    q.offset(dx, dy)
    return q


def op(a, b, kind):
    return skia.Op(a, b, kind)


UNION, DIFF, INTER = skia.PathOp.kUnion_PathOp, skia.PathOp.kDifference_PathOp, skia.PathOp.kIntersect_PathOp


def fill(cv, path, color, blur=0, shader=None, alpha=None):
    paint = skia.Paint(AntiAlias=True, Color=C(color) if isinstance(color, str) else color)
    if alpha is not None:
        paint.setAlphaf(alpha)
    if shader is not None:
        paint.setShader(shader)
    if blur:
        paint.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur))
    cv.drawPath(path, paint)


def stroke(cv, path, width=LINE, color=OUT_C, cap=skia.Paint.kRound_Cap):
    paint = skia.Paint(AntiAlias=True, Color=C(color), Style=skia.Paint.kStroke_Style,
                       StrokeWidth=width, StrokeJoin=skia.Paint.kRound_Join, StrokeCap=cap)
    cv.drawPath(path, paint)


def shade(cv, sil, base_path=None, sh=(26, 34), hi=(-22, -30), sh_col=YEL_SH, hi_col=YEL_HI, sh_a=1.0, hi_a=0.85):
    """Cel shading clipped to the silhouette: a crescent of shadow lower-right, light upper-left."""
    base = base_path or sil
    cv.save()
    cv.clipPath(sil, doAntiAlias=True)
    fill(cv, op(base, shifted(base, -sh[0], -sh[1]), DIFF), sh_col, alpha=sh_a)
    fill(cv, op(base, shifted(base, -hi[0], -hi[1]), DIFF), hi_col, blur=6, alpha=hi_a)
    cv.restore()


def canvas():
    surf = skia.Surface(W, H)
    cv = surf.getCanvas()
    cv.clear(skia.ColorTRANSPARENT)
    return surf, cv


def save(surf, name):
    img = surf.makeImageSnapshot()
    arr = img.toarray(colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kUnpremul_AlphaType)
    os.makedirs(OUT, exist_ok=True)
    Image.fromarray(arr).save(os.path.join(OUT, f"{name}.png"))


# ── character shapes ─────────────────────────────────────────────────────────

HEAD_C = (600, 610)


def head_path():
    cx, cy = HEAD_C
    pts = []
    for i in range(20):
        a = i / 20 * 2 * math.pi
        rx, ry = 335, 282
        x = math.cos(a)
        y = math.sin(a)
        # fuller cheeks low on the sides, slightly flatter crown
        bulge = 1 + 0.06 * max(0, math.sin(a)) * abs(math.cos(a)) * 2.2
        crown = 1 - 0.05 * max(0, -math.sin(a)) ** 3
        pts.append((cx + rx * x * bulge, cy + ry * y * crown))
    return blob(pts)


def body_path():
    return blob([
        (600, 830), (775, 860), (880, 965), (925, 1120), (900, 1262), (800, 1346),
        (600, 1380), (400, 1346), (300, 1262), (275, 1120), (320, 965), (425, 860),
    ])


def ear_path(side):
    """Left ear (side=-1) / right ear (+1): a short, round-tipped leaf from the crown."""
    pts = [(455, 425), (380, 350), (318, 245), (300, 150), (335, 108), (395, 128),
           (465, 205), (520, 300), (552, 392)]
    if side > 0:
        pts = [(2 * CX - x, y) for x, y in pts]
    return blob(pts)


def tuft_path():
    """Three-point spark tuft on the crown (the character's own mark)."""
    return blob([(548, 352), (566, 270), (590, 318), (612, 236), (628, 312), (664, 262), (652, 352)], tension=0.6)


def ear_tip(side):
    tip = oval(330 if side < 0 else 2 * CX - 330, 118, 120, 110)
    return tip


def foot_path(side):
    return oval(CX + side * 132, 1370, 98, 48)


def arm_path(shoulder, hand, r0=58, r1=50, hr=62):
    """Tapered capsule from shoulder to hand, plus a round mitten hand."""
    (x0, y0), (x1, y1) = shoulder, hand
    a = math.atan2(y1 - y0, x1 - x0)
    nx, ny = -math.sin(a), math.cos(a)
    p = skia.Path()
    p.moveTo(x0 + nx * r0, y0 + ny * r0)
    p.lineTo(x1 + nx * r1, y1 + ny * r1)
    p.lineTo(x1 - nx * r1, y1 - ny * r1)
    p.lineTo(x0 - nx * r0, y0 - ny * r0)
    p.close()
    p = op(p, oval(x0, y0, r0, r0), UNION)
    p = op(p, oval(x1, y1, hr, hr * 0.94), UNION)
    return p


def finger_path(hand, angle_deg, length=62, r=17):
    a = math.radians(angle_deg)
    x1, y1 = hand[0] + math.cos(a) * length, hand[1] + math.sin(a) * length
    return arm_path(hand, (x1, y1), r0=r, r1=r, hr=r)


SHOULDER_L, SHOULDER_R = (365, 995), (835, 995)

POSES = {
    # name: (left hand, right hand, extras)
    "idle": ((352, 1175), (848, 1175), None),
    "excited": ((250, 690), (950, 690), None),
    "point": ((352, 1175), (1000, 900), "point_r"),
    "wave_a": ((352, 1175), (980, 700), "palm_r"),
    "wave_b": ((352, 1175), (1030, 760), "palm_r"),
    "shrug": ((255, 1060), (945, 1060), "palms_up"),
    "think": ((352, 1175), (712, 905), "chin"),
}


# ── drawing ──────────────────────────────────────────────────────────────────

def draw_ear(cv, side):
    ear = ear_path(side)
    fill(cv, ear, YEL)
    cv.save()
    cv.clipPath(ear, doAntiAlias=True)
    shade(cv, ear, sh=(-20 * side, 30), hi=(16 * side, -20))
    fill(cv, ear_tip(side), TIP)
    fill(cv, op(ear_tip(side), shifted(ear_tip(side), 14 * side, -18), DIFF), TIP_SH)
    fill(cv, oval(342 if side < 0 else 2 * CX - 342, 128, 34, 22), TIP_HI, blur=10, alpha=0.6)
    cv.restore()
    # tip boundary line
    cv.save()
    cv.clipPath(ear, doAntiAlias=True)
    stroke(cv, ear_tip(side), width=6)
    cv.restore()
    stroke(cv, ear)


def draw_arm(cv, shoulder, hand, extra, side):
    parts = arm_path(shoulder, hand)
    a = math.degrees(math.atan2(hand[1] - shoulder[1], hand[0] - shoulder[0]))
    if extra == f"point_{'r' if side > 0 else 'l'}":
        parts = op(parts, finger_path(hand, a, length=78, r=21), UNION)
        parts = op(parts, finger_path(hand, a - 90 * side, length=40, r=19), UNION)
    elif extra == f"palm_{'r' if side > 0 else 'l'}" or extra == "palms_up":
        # open mitten: a thumb sticking out the inside edge
        parts = op(parts, finger_path(hand, a - 75 * side if extra != "palms_up" else a - 100 * side, length=44, r=20), UNION)
    else:
        parts = op(parts, finger_path(hand, a + 70 * side, length=32, r=20), UNION)
    fill(cv, parts, YEL)
    shade(cv, parts, sh=(14, 22), hi=(-12, -18))
    stroke(cv, parts)


def draw_cheek(cv, side):
    cx, cy = CX + side * 228, 728
    glow = skia.GradientShader.MakeRadial((cx, cy), 92, [C(CHEEK, 120), C(CHEEK, 0)])
    fill(cv, oval(cx, cy, 92, 92), skia.ColorWHITE, shader=glow)
    ch = oval(cx, cy, 54, 48)
    grad = skia.GradientShader.MakeRadial((cx - 12, cy - 14), 64, [C(CHEEK_LT), C(CHEEK), C(CHEEK_SH)])
    fill(cv, ch, skia.ColorWHITE, shader=grad)
    fill(cv, oval(cx - 16, cy - 16, 14, 10), "#FFFFFF", alpha=0.85)
    stroke(cv, ch, width=6)


def draw_collar_and_tag(cv):
    band = skia.Path()
    band.moveTo(420, 880)
    band.quadTo(600, 985, 780, 880)
    paint = skia.Paint(AntiAlias=True, Color=C(OUT_C), Style=skia.Paint.kStroke_Style, StrokeWidth=44,
                       StrokeCap=skia.Paint.kRound_Cap)
    cv.drawPath(band, paint)
    paint.setColor(C(GOLD))
    paint.setStrokeWidth(32)
    cv.drawPath(band, paint)
    paint.setColor(C(GOLD_HI, 170))
    paint.setStrokeWidth(8)
    hl = skia.Path()
    hl.moveTo(450, 892)
    hl.quadTo(600, 968, 750, 892)
    cv.drawPath(hl, paint)
    # ring + tag with the real app icon
    ring = oval(600, 958, 20, 20)
    stroke(cv, ring, width=16)
    stroke(cv, ring, width=8, color="#D9DEE5")
    tag = skia.Rect.MakeXYWH(600 - 66, 972, 132, 132)
    rr = skia.RRect.MakeRectXY(tag, 30, 30)
    shadow = skia.Path()
    shadow.addRRect(skia.RRect.MakeRectXY(tag.makeOffset(8, 12), 30, 30))
    fill(cv, shadow, "#000000", blur=10, alpha=0.25)
    cv.save()
    cv.clipRRect(rr, doAntiAlias=True)
    if os.path.exists(ICON):
        icon = skia.Image.open(ICON)
        cv.drawImageRect(icon, tag, skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear))
    else:
        bg = skia.Path()
        bg.addRect(tag)
        fill(cv, bg, "#14182E")
        bolt = blob([(612, 990), (566, 1046), (598, 1046), (582, 1088), (636, 1026), (604, 1026), (622, 990)], tension=0.0)
        fill(cv, bolt, GOLD)
        stroke(cv, bolt, width=5)
    gloss = skia.GradientShader.MakeLinear([(0, 972), (0, 1040)], [C("#FFFFFF", 70), C("#FFFFFF", 0)])
    p = skia.Path()
    p.addRect(tag)
    fill(cv, p, skia.ColorWHITE, shader=gloss)
    cv.restore()
    border = skia.Path()
    border.addRRect(rr)
    stroke(cv, border, width=8)


def draw_pose(name):
    surf, cv = canvas()
    lh, rh, extra = POSES[name]
    # ground shadow
    fill(cv, oval(CX, 1408, 300, 34), "#000000", blur=18, alpha=0.28)
    # arms that go behind the body (raised ones read better in front, so all in front)
    head, body = head_path(), body_path()
    sil = op(head, body, UNION)
    # feet behind body bottom
    for s in (-1, 1):
        f = foot_path(s)
        fill(cv, f, YEL_SH)
        fill(cv, op(f, shifted(f, 0, -16), DIFF), YEL_DEEP)
        stroke(cv, f)
    fill(cv, sil, YEL)
    # belly patch
    belly = blob([(600, 1010), (735, 1060), (790, 1190), (720, 1320), (600, 1345), (480, 1320), (410, 1190), (465, 1060)])
    cv.save()
    cv.clipPath(body, doAntiAlias=True)
    fill(cv, belly, BELLY)
    cv.restore()
    # body shading, then the shadow the head casts on the body
    shade(cv, body, sh=(30, 26), hi=(-26, -22))
    cv.save()
    cv.clipPath(op(body, head, DIFF), doAntiAlias=True)
    fill(cv, shifted(head, 6, 34), YEL_SH, blur=10, alpha=0.9)
    cv.restore()
    draw_collar_and_tag(cv)
    # head over the collar ends, shaded
    fill(cv, head, YEL)
    shade(cv, head, sh=(24, 30), hi=(-28, -34))
    tuft = tuft_path()
    fill(cv, tuft, YEL)
    shade(cv, tuft, sh=(10, 14), hi=(-8, -10))
    cv.save()
    cv.clipPath(op(tuft, head, DIFF), doAntiAlias=True)
    stroke(cv, tuft, width=LINE + 1)
    cv.restore()
    # soft top light on the crown
    crown = skia.GradientShader.MakeRadial((520, 470), 260, [C("#FFFFFF", 110), C("#FFFFFF", 0)])
    cv.save()
    cv.clipPath(head, doAntiAlias=True)
    fill(cv, oval(520, 470, 260, 200), skia.ColorWHITE, shader=crown)
    cv.restore()
    # outlines: whole silhouette + the chin line where head meets body
    stroke(cv, sil, width=LINE + 1)
    cv.save()
    cv.clipPath(body, doAntiAlias=True)
    stroke(cv, head, width=LINE - 1)
    cv.restore()
    for s in (-1, 1):
        draw_cheek(cv, s)
    # nose
    nose = blob([(586, 698), (614, 698), (606, 714), (594, 714)])
    fill(cv, nose, OUT_C)
    # arms last, in front
    draw_arm(cv, SHOULDER_L, lh, extra, -1)
    draw_arm(cv, SHOULDER_R, rh, extra, 1)
    save(surf, f"pose_{name}")


def draw_ears():
    for side, nm in ((-1, "ear_l"), (1, "ear_r")):
        surf, cv = canvas()
        draw_ear(cv, side)
        save(surf, nm)


# ── eyes ─────────────────────────────────────────────────────────────────────

EYE_L, EYE_R = (468, 606), (732, 606)


def one_eye(cv, c, kind, look=(0, 0)):
    x, y = c
    if kind in ("open", "wide", "half"):
        rx, ry = (52, 66) if kind != "wide" else (58, 76)
        e = oval(x, y, rx, ry)
        g = skia.GradientShader.MakeLinear([(x, y - ry), (x, y + ry)], [C(EYE), C(EYE), C(EYE_MID)], [0, 0.55, 1])
        fill(cv, e, skia.ColorWHITE, shader=g)
        hx, hy = x + look[0], y + look[1]
        hr = 19 if kind != "wide" else 15
        fill(cv, oval(hx - 15, hy - 24, hr, hr), "#FFFFFF")
        fill(cv, oval(hx + 17, hy + 20, 8, 8), "#FFFFFF", alpha=0.9)
        # teal sparkle in the iris
        fill(cv, oval(hx - 4, hy + 30, 16, 9), "#7FE9FF", alpha=0.55, blur=3)
        if kind == "half":
            cut = skia.Path()
            cut.addRect(skia.Rect.MakeLTRB(x - rx - 12, y - ry - 12, x + rx + 12, y - 4))
            lid = op(oval(x, y, rx + 6, ry + 6), cut, INTER)
            fill(cv, lid, YEL)
            line = skia.Path()
            line.moveTo(x - rx - 2, y - 6)
            line.quadTo(x, y + 6, x + rx + 2, y - 6)
            stroke(cv, line, width=9)
    elif kind == "closed":
        line = skia.Path()
        line.moveTo(x - 50, y + 4)
        line.quadTo(x, y + 30, x + 50, y + 4)
        stroke(cv, line, width=11)
    elif kind == "happy":
        line = skia.Path()
        line.moveTo(x - 48, y + 18)
        line.quadTo(x, y - 40, x + 48, y + 18)
        stroke(cv, line, width=13)


def draw_eyes():
    for kind in ("open", "half", "closed", "happy", "wide"):
        surf, cv = canvas()
        for c in (EYE_L, EYE_R):
            one_eye(cv, c, kind)
        save(surf, f"eyes_{kind}")


# ── mouths (Rhubarb shapes A-H, X, plus smile) ──────────────────────────────

MX, MY = 600, 762
MS = 1.45  # mouth scale


def open_mouth(cv, w, h, teeth_top=0, tongue=0.0, flat_top=0.35, teeth_bottom=0, tongue_up=False):
    w, h, teeth_top = w * MS, h * MS, teeth_top * MS
    x0, x1 = MX - w / 2, MX + w / 2
    top = MY - h * 0.28
    p = skia.Path()
    p.moveTo(x0, top)
    p.quadTo(MX, top - h * flat_top * 0.25, x1, top)
    p.cubicTo(x1 + w * 0.05, top + h * 0.75, MX + w * 0.28, top + h, MX, top + h)
    p.cubicTo(MX - w * 0.28, top + h, x0 - w * 0.05, top + h * 0.75, x0, top)
    p.close()
    fill(cv, p, MOUTH)
    cv.save()
    cv.clipPath(p, doAntiAlias=True)
    if tongue:
        ty = top + h * (0.35 if tongue_up else 0.62)
        fill(cv, oval(MX, ty + h * 0.3, w * 0.36 * tongue + 10, h * 0.42), TONGUE)
        fill(cv, oval(MX - w * 0.08, ty + h * 0.12, w * 0.1, h * 0.08), "#FFB3BF", alpha=0.7)
    if teeth_top:
        t = skia.Path()
        t.addRect(skia.Rect.MakeLTRB(x0, top - 20, x1, top + teeth_top))
        fill(cv, t, "#FFFFFF")
    if teeth_bottom:
        t = skia.Path()
        t.addRect(skia.Rect.MakeLTRB(x0, top + h - teeth_bottom, x1, top + h + 20))
        fill(cv, t, "#FFFFFF")
    cv.restore()
    stroke(cv, p, width=8)
    return p


def draw_mouths():
    def make(name, fn):
        surf, cv = canvas()
        fn(cv)
        save(surf, f"mouth_{name}")

    def cat(cv, width=1.0):
        p = skia.Path()
        p.moveTo(MX - 52 * width, MY - 8)
        p.quadTo(MX - 26 * width, MY + 20, MX, MY - 2)
        p.quadTo(MX + 26 * width, MY + 20, MX + 52 * width, MY - 8)
        stroke(cv, p, width=10)

    def pressed(cv):
        p = skia.Path()
        p.moveTo(MX - 50, MY + 2)
        p.quadTo(MX, MY + 14, MX + 50, MY + 2)
        stroke(cv, p, width=12)

    make("X", lambda cv: cat(cv))                                                   # rest
    make("A", pressed)                                                               # M B P
    make("B", lambda cv: open_mouth(cv, 78, 30, teeth_top=10, flat_top=0.2))         # K S T, teeth
    make("C", lambda cv: open_mouth(cv, 104, 52, teeth_top=11, tongue=0.8))          # EH AE
    make("D", lambda cv: open_mouth(cv, 120, 96, teeth_top=10, tongue=1.0))          # AA
    make("E", lambda cv: open_mouth(cv, 74, 74, tongue=0.6, flat_top=1.4))           # AO ER (round)
    make("F", lambda cv: open_mouth(cv, 44, 40, flat_top=1.6))                       # UW OW W (pucker)
    make("G", lambda cv: open_mouth(cv, 92, 34, teeth_top=16, flat_top=0.1))         # F V
    make("H", lambda cv: open_mouth(cv, 98, 62, teeth_top=9, tongue=0.9, tongue_up=True))  # L
    make("smile", lambda cv: open_mouth(cv, 128, 70, teeth_top=12, tongue=0.9, flat_top=-0.6))


if __name__ == "__main__":
    draw_ears()
    for p in POSES:
        draw_pose(p)
    draw_eyes()
    draw_mouths()
    print("sprites ->", OUT)
