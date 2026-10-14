"""Doodle rig: a waist-up cartoon character drawn entirely in code (PIL).

The "kev" example mascot: bold ink line, backwards cap, strong brows, stubble, athletic build, tank top.
mascots/kev/draw.py and mascots/anime/draw.py bake this rig into a sprite pack.

    img, origin = draw_mascot(State(...), scale=1.0)

`State` is every animatable control (mouth shape, blink, brows, head, both arms). The renderer
tweens States; nothing here knows about time except `boil`, the hand-drawn line-wobble index.
Full body with two-bone IK on both arms and legs, so hands and feet can be sent to exact points
(that is how the mascot grabs, pushes and kicks things in the edit; see stage.py).
"""
from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass, field, replace
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

INK = (26, 24, 28, 255)
PAPER = (253, 251, 244, 255)
CAP = (43, 140, 240, 255)
CAP_DARK = (28, 104, 196, 255)
TEAL = (20, 205, 195, 255)
TONGUE = (236, 112, 104, 255)
MOUTH_IN = (58, 22, 30, 255)
HAIR = (44, 34, 30, 255)
SHORTS = (38, 42, 58, 255)
SKIN = (240, 184, 146, 255)        # tan
SKIN_SH = (214, 150, 114, 255)     # shade side
BLUSH = (240, 150, 128, 255)
BEARD = (190, 140, 112, 255)       # stubble shadow under the dots
IRIS = (112, 72, 44, 255)
TANK = (24, 24, 28, 255)
TANK_HI = (78, 80, 92, 255)
WHITE = (255, 255, 255, 255)
LOGO = None   # optional path to a square logo PNG printed on the tank top (set by the mascot's draw.py)

LW = 6.0   # ink line width, local units
FINGERS = [(-27, 44), (-9, 54), (9, 52), (27, 42)]   # open-hand fingers (offset, length); some styles draw three
SS = 2     # supersample

Pt = Tuple[float, float]

# ───────────────────────────── mouth shapes ─────────────────────────────


@dataclass
class Mouth:
    """One mouth shape. w = half width, h = opening, up = how far the top lip lifts,
    teeth/tongue 0..1, smile = corner lift (closed shapes), tuck = lower lip under the top teeth (F/V)."""
    w: float = 46
    h: float = 0
    up: float = 0.25
    teeth: float = 0
    tongue: float = 0
    smile: float = 0.5
    tuck: float = 0

    def mix(self, o: "Mouth", k: float) -> "Mouth":
        L = lambda a, b: a + (b - a) * k
        return Mouth(L(self.w, o.w), L(self.h, o.h), L(self.up, o.up), L(self.teeth, o.teeth),
                     L(self.tongue, o.tongue), L(self.smile, o.smile), L(self.tuck, o.tuck))


VISEMES = {
    "rest": Mouth(w=44, h=0, smile=0.55),
    "MBP": Mouth(w=38, h=0, smile=0.0),                              # lips pressed: m b p
    "A": Mouth(w=54, h=70, up=0.22, teeth=0.75, tongue=0.55),        # ah / a / eye: jaw wide open
    "E": Mouth(w=62, h=44, up=0.30, teeth=1.0, tongue=0.35),         # eh / ee: wide, shallow
    "O": Mouth(w=30, h=54, up=0.38, teeth=0.0, tongue=0.25),         # oh / aw: tall round
    "U": Mouth(w=19, h=24, up=0.45, teeth=0.0, tongue=0.0),          # oo / w: small pucker
    "FV": Mouth(w=46, h=20, up=0.45, teeth=1.0, tongue=0.0, tuck=1), # f v: teeth on lip
    "L": Mouth(w=46, h=38, up=0.28, teeth=0.8, tongue=1.0),          # l / th: tongue up
    "C": Mouth(w=54, h=25, up=0.36, teeth=1.0, tongue=0.0),          # s z t d k g n sh ch: teeth together
    "R": Mouth(w=32, h=22, up=0.40, teeth=0.4, tongue=0.2),          # r / er: slight pucker
}

# ───────────────────────────── state ─────────────────────────────


@dataclass
class Arm:
    """a1/a2 = upper-arm / forearm direction in degrees: 0 hangs down, 90 points out to the side,
    180 straight up, negative swings in across the body. hand: fist | open | point | thumb."""
    a1: float = 10
    a2: float = 4
    hand: str = "fist"
    flex: float = 0.0   # extra bicep bulge 0..1

    def mix(self, o: "Arm", k: float) -> "Arm":
        L = lambda a, b: a + (b - a) * k
        return Arm(L(self.a1, o.a1), L(self.a2, o.a2), o.hand if k > 0.5 else self.hand, L(self.flex, o.flex))


ARM_POSES = {
    "rest": Arm(10, 4, "fist"),
    "hips": Arm(42, -52, "fist"),
    "point_up": Arm(58, 172, "point"),
    "point_side": Arm(78, 92, "point"),
    "flex": Arm(92, 205, "fist", 1.0),
    "open": Arm(46, 112, "open"),
    "open_low": Arm(34, 78, "open"),
    "wave": Arm(72, 162, "open"),
    "thumb": Arm(44, 128, "thumb"),
    "up": Arm(150, 176, "open"),
}


@dataclass
class State:
    """Everything animatable. Positions are in ground space: origin = the spot on the floor between
    the feet, y down (so heights are negative), local units (the character is ~1150 tall)."""
    mouth: Mouth = field(default_factory=lambda: VISEMES["rest"])
    blink: float = 0.0        # 0 open .. 1 closed
    lid: float = 0.15         # resting upper eyelid, 0 wide-eyed .. 0.6 sleepy
    brow: float = 0.0         # -1 frown .. +1 raised
    brow_tilt: float = 0.35   # + = confident / angled in
    look: Pt = (0.0, 0.0)     # pupil offset -1..1
    head_rot: float = 0.0     # degrees (roll)
    yaw: float = 0.0          # 3D head turn, + = toward screen right
    pitch: float = 0.0        # 3D head nod, - = up
    head_dx: float = 0.0
    head_dy: float = 0.0
    lean: float = 0.0         # whole upper body tilts about the hips, degrees (+ = to screen right)
    crouch: float = 0.0       # hips drop by this much
    hip_dx: float = 0.0       # hips shift sideways over the feet
    armL: Arm = field(default_factory=lambda: ARM_POSES["rest"])   # screen-left arm
    armR: Arm = field(default_factory=lambda: ARM_POSES["rest"])   # screen-right arm
    handL: Optional[Tuple[float, float, float]] = None   # (x, y, weight): IK target that overrides the pose
    handR: Optional[Tuple[float, float, float]] = None
    footL: Tuple[float, float, float] = (-70.0, 0.0, 0.0)   # (x, height above floor, toe pitch deg)
    footR: Tuple[float, float, float] = (70.0, 0.0, 0.0)
    boil: int = 0
    # expression extras (ignored by the built-in styles; handy for your own heads)
    wink: int = 0             # -1 / 1 closes that eye
    blush: float = 0.0        # 0..1 cheek blush
    smirk: float = 0.0        # 0..1 lifts the screen-right mouth corner

    def with_(self, **kw) -> "State":
        return replace(self, **kw)


# ───────────────────────────── drawing kit ─────────────────────────────


IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)   # a b c d tx ty :  x' = a x + c y + tx ;  y' = b x + d y + ty


def xf(tx: float = 0, ty: float = 0, deg: float = 0, k: float = 1.0):
    a = math.radians(deg)
    return (math.cos(a) * k, math.sin(a) * k, -math.sin(a) * k, math.cos(a) * k, tx, ty)


def mul(A, B):
    """A after B."""
    return (A[0] * B[0] + A[2] * B[1], A[1] * B[0] + A[3] * B[1], A[0] * B[2] + A[2] * B[3], A[1] * B[2] + A[3] * B[3],
            A[0] * B[4] + A[2] * B[5] + A[4], A[1] * B[4] + A[3] * B[5] + A[5])


def ap(M, pts: Sequence[Pt]) -> List[Pt]:
    return [(M[0] * x + M[2] * y + M[4], M[1] * x + M[3] * y + M[5]) for x, y in pts]


class Pen:
    """Maps local units onto the supersampled canvas (through an affine matrix) and draws wobbly ink."""
    AMP = 1.0     # global line-wobble multiplier; art styles set it (doodle = shaky, cel = clean)

    def __init__(self, d: ImageDraw.ImageDraw, ox: float, oy: float, s: float, boil: int, M=IDENT):
        self.d, self.ox, self.oy, self.s, self.boil, self.M = d, ox, oy, s, boil, M

    def at(self, M) -> "Pen":
        return Pen(self.d, self.ox, self.oy, self.s, self.boil, mul(self.M, M))

    def px(self, pts: Sequence[Pt]) -> List[Pt]:
        return [(self.ox + x * self.s, self.oy + y * self.s) for x, y in ap(self.M, pts)]

    def wob(self, pts: Sequence[Pt], seed: int, amp: float = 1.0) -> List[Pt]:
        """Low-frequency displacement along the path, re-rolled every boil step."""
        amp *= Pen.AMP
        r = random.Random(seed * 7919 + self.boil * 104729)
        p1, p2, p3, p4 = (r.uniform(0, 6.28) for _ in range(4))
        f1, f2 = r.uniform(0.012, 0.022), r.uniform(0.03, 0.05)
        out, acc, prev = [], 0.0, pts[0]
        for x, y in pts:
            acc += math.hypot(x - prev[0], y - prev[1])
            prev = (x, y)
            out.append((x + amp * (math.sin(acc * f1 + p1) + 0.5 * math.sin(acc * f2 + p2)),
                        y + amp * (math.sin(acc * f1 + p3) + 0.5 * math.sin(acc * f2 + p4))))
        return out

    def line(self, pts: Sequence[Pt], seed: int, w: float = LW, color=INK, amp: float = 1.6, wob: bool = True):
        p = self.px(self.wob(pts, seed, amp) if wob else pts)
        W = max(1, int(round(w * self.s)))
        self.d.line(p, fill=color, width=W, joint="curve")
        r = W / 2
        for x, y in (p[0], p[-1]):
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=color)

    def shape(self, pts: Sequence[Pt], seed: int, fill=PAPER, w: float = LW, outline=INK, amp: float = 1.6):
        wp = self.wob(list(pts) + [pts[0]], seed, amp)
        self.d.polygon(self.px(wp), fill=fill)
        if outline:
            self.line(wp, seed, w, outline, wob=False)

    def dot(self, c: Pt, r: float, color=INK):
        (x, y), R = self.px([c])[0], r * self.s
        self.d.ellipse((x - R, y - R, x + R, y + R), fill=color)

    def tube(self, a: Pt, b: Pt, w: float, col):
        p = self.px([a, b])
        W = int(round(w * self.s))
        self.d.line(p, fill=col, width=W)
        for x, y in p:
            self.d.ellipse((x - W / 2, y - W / 2, x + W / 2, y + W / 2), fill=col)


def bez(p0: Pt, p1: Pt, p2: Pt, n: int = 14) -> List[Pt]:
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in (i / n for i in range(n + 1))]


def arc(cx: float, cy: float, rx: float, ry: float, a0: float, a1: float, n: int = 28) -> List[Pt]:
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def rot(pts: Sequence[Pt], deg: float, c: Pt = (0, 0), dx: float = 0, dy: float = 0, k: float = 1.0) -> List[Pt]:
    a, (cx, cy) = math.radians(deg), c
    ca, sa = math.cos(a) * k, math.sin(a) * k
    return [(cx + (x - cx) * ca - (y - cy) * sa + dx, cy + (x - cx) * sa + (y - cy) * ca + dy) for x, y in pts]


# ───────────────────────────── the character ─────────────────────────────

HEAD_K = 1.17   # doodle proportions: big head, it carries the lip sync
NECK_PIVOT = (0.0, -30.0)
HEAD_C = (0.0, -205.0)
SHOULDER = (226.0, 92.0)
UPPER, FORE = 170.0, 158.0
TORSO_H = 340.0            # neck base down to the hips
HIP_J = (66.0, 352.0)      # hip joint, chest space
THIGH, SHIN = 160.0, 160.0
HIP_H = 338.0              # standing hip height over the floor
ANKLE_H = 30.0
_STUBBLE = None


def _stubble() -> List[Pt]:
    global _STUBBLE
    if _STUBBLE is None:
        r, pts = random.Random(11), []
        while len(pts) < 96:
            x, y = r.uniform(-135, 135), r.uniform(-150, -42)
            e = (x / 146) ** 2 + ((y + 205) / 172) ** 2
            band = 0.60 if abs(x) > 80 else 0.50
            if band < e < 0.93 and not (abs(x) < 34 and y < -130):
                pts.append((x, y))
        for _ in range(14):   # moustache line
            pts.append((r.uniform(-48, 48), r.uniform(-146, -132)))
        _STUBBLE = pts
    return _STUBBLE


def _head_outline(drop: float) -> List[Pt]:
    """Rounded head with a squarer jaw; `drop` stretches the chin when the mouth opens."""
    cx, cy = HEAD_C
    pts = []
    for i in range(72):
        t = math.radians(i * 5)
        c, s = math.cos(t), math.sin(t)
        e = 2.5 if s > 0 else 2.1
        x = 150 * math.copysign(abs(c) ** (2 / e), c)
        y = 170 * math.copysign(abs(s) ** (2 / e), s)
        if s > 0:
            x *= 1 - 0.10 * s            # taper to the jaw
            y += drop * s * s
        pts.append((cx + x, cy + y))
    return pts


def _draw_mouth(pen: Pen, m: Mouth, H, seed: int):
    cx, cy = 4.0, -104.0
    n = 18
    if m.h < 3:   # closed: one line, corners lifted by smile
        lift = 14 * m.smile
        pts = bez((cx - m.w, cy - lift * 0.55), (cx, cy + lift), (cx + m.w, cy - lift * 0.55))
        pen.line(H(pts), seed)
        if m.smile > 0.3:   # cheek tick, the classic doodle smirk
            pen.line(H(bez((cx + m.w + 6, cy - lift * 0.55 - 9), (cx + m.w + 13, cy - lift * 0.55), (cx + m.w + 6, cy - lift * 0.55 + 8), 6)), seed + 1, LW * 0.8)
        return
    top_h, bot_h = m.h * m.up, m.h * (1 - m.up)
    xs = [-m.w + 2 * m.w * i / n for i in range(n + 1)]
    prof = lambda x, p: max(0.0, 1 - abs(x / m.w) ** p)
    yu = [cy - top_h * prof(x, 2.2) ** 0.8 for x in xs]
    yl = [cy + bot_h * prof(x, 2.6) ** 0.7 for x in xs]
    up = [(cx + x, y) for x, y in zip(xs, yu)]
    lo = [(cx + x, y) for x, y in zip(xs, yl)]
    poly = up + lo[::-1]
    pen.d.polygon(pen.px(H(poly)), fill=MOUTH_IN)
    if m.tongue > 0.05:
        if m.tongue > 0.8:   # tongue lifted to the teeth (L / TH)
            ty = [max(u + 2, l - (l - u) * 0.78 * prof(x, 2.0)) for x, u, l in zip(xs, yu, yl)]
        else:
            ty = [max(u + 2, l - bot_h * 0.62 * m.tongue * prof(x * 1.25, 2.0)) for x, u, l in zip(xs, yu, yl)]
        pen.d.polygon(pen.px(H([(cx + x, y) for x, y in zip(xs, ty)] + lo[::-1])), fill=TONGUE)
    if m.teeth > 0.05:
        th = (9 + 9 * m.teeth) if m.h > 30 else m.h * 0.48
        te = [min(u + th * prof(x * 0.96, 6), l) for x, u, l in zip(xs, yu, yl)]
        pen.d.polygon(pen.px(H(up + [(cx + x, y) for x, y in zip(xs, te)][::-1])), fill=(255, 255, 255, 255))
        if m.h <= 30 and not m.tuck:   # clenched: bottom row too, with the bite line between
            be = [max(l - m.h * 0.46 * prof(x * 0.96, 6), u) for x, u, l in zip(xs, yu, yl)]
            pen.d.polygon(pen.px(H(lo + [(cx + x, y) for x, y in zip(xs, be)][::-1])), fill=(255, 255, 255, 255))
            pen.line(H([(cx - m.w * 0.82, cy + (bot_h - top_h) * 0.08), (cx + m.w * 0.82, cy + (bot_h - top_h) * 0.08)]), seed + 3, LW * 0.45, wob=False)
    pen.line(H(poly + [poly[0]]), seed, LW * 0.95, amp=1.0)
    if m.tuck:   # lower lip rolled under the top teeth
        pen.line(H(bez((cx - m.w * 0.7, cy + bot_h + 9), (cx, cy + bot_h + 17), (cx + m.w * 0.7, cy + bot_h + 9), 8)), seed + 2, LW * 0.7)


def _hand(pen: Pen, c: Pt, ang: float, kind: str, side: int, seed: int, black: bool):
    """Mitten hand at the wrist end. ang = forearm direction (radians from +y toward +x*side)."""
    dx, dy = math.sin(ang) * side, math.cos(ang)
    nx, ny = dy, -dx
    r = 39
    col = INK if black else SKIN
    grow = LW if black else 0

    def blob(center: Pt, rad: float):
        pen.dot(center, rad + grow, col)

    def finger(base: Pt, d: Pt, length: float, w: float):
        tip = (base[0] + d[0] * length, base[1] + d[1] * length)
        p = pen.px([base, tip])
        W = int(round((w + 2 * grow) * pen.s))
        pen.d.line(p, fill=col, width=W)
        pen.dot(tip, w / 2 + grow, col)

    hc = (c[0] + dx * 22, c[1] + dy * 22)
    ix, iy = nx * side, ny * side   # the thumb / index edge of the hand (faces the body)
    if kind == "point":   # index finger on the thumb edge + thumb out: never a lone middle finger
        finger((hc[0] + ix * 22 + dx * 14, hc[1] + iy * 22 + dy * 14), (dx, dy), 62, 22)
        blob(hc, r)
        finger((hc[0] + ix * 24 - dx * 12, hc[1] + iy * 24 - dy * 12), (ix * 0.98 + dx * 0.12, iy * 0.98 + dy * 0.12), 46, 21)
    elif kind == "thumb":
        blob(hc, r)
        finger((hc[0] + nx * 14 * side, hc[1] + ny * 14 * side), (0, -1), 56, 24)
    elif kind == "open":
        for k, (off, ln) in enumerate(FINGERS):
            b = (hc[0] + nx * off + dx * 18, hc[1] + ny * off + dy * 18)
            fd = (dx + nx * off * 0.006, dy + ny * off * 0.006)
            finger(b, fd, ln, 19)
        blob(hc, r)
        finger((hc[0] - nx * 30 * side, hc[1] - ny * 30 * side), (-nx * side * 0.8 + dx * 0.6, -ny * side * 0.8 + dy * 0.6), 34, 20)
    else:
        blob(hc, r)
    if not black and kind in ("fist", "thumb", "point"):   # curled-finger ticks, away from the index
        offs = (-22, -6) if kind == "point" else (-12, 6)
        for off in offs:
            a = (hc[0] + ix * off + dx * 10, hc[1] + iy * off + dy * 10)
            b = (a[0] + dx * 17, a[1] + dy * 17)
            pen.line([a, b], seed + int(off), LW * 0.55, wob=False)


def ik2(S: Pt, T: Pt, a: float, b: float, prefer: Pt, stretch: float = 1.6) -> Tuple[Pt, Pt]:
    """Two-bone IK with rubber-hose stretch. Returns (elbow, wrist). `prefer` = direction the joint likes to bend toward."""
    dx, dy = T[0] - S[0], T[1] - S[1]
    d = math.hypot(dx, dy) or 1e-6
    reach = a + b
    k = min(stretch, max(1.0, d / (reach * 0.985)))
    a, b = a * k, b * k
    d2 = max(abs(a - b) + 1, min(a + b - 0.5, d))
    ux, uy = dx / d, dy / d
    x = (a * a - b * b + d2 * d2) / (2 * d2)
    h = math.sqrt(max(0.0, a * a - x * x))
    c1 = (S[0] + ux * x - uy * h, S[1] + uy * x + ux * h)
    c2 = (S[0] + ux * x + uy * h, S[1] + uy * x - ux * h)
    sc = lambda c: (c[0] - S[0]) * prefer[0] + (c[1] - S[1]) * prefer[1]
    E = c1 if sc(c1) >= sc(c2) else c2
    return E, (S[0] + ux * d2, S[1] + uy * d2)


def arm_points(st: "State", side: int, C) -> Tuple[Pt, Pt, Pt, Arm]:
    """Shoulder, elbow, wrist in ground space for one arm (pose angles, blended toward an IK hand target)."""
    arm = st.armL if side < 0 else st.armR
    tgt = st.handL if side < 0 else st.handR
    S = ap(C, [(SHOULDER[0] * side, SHOULDER[1])])[0]
    a1, a2 = math.radians(arm.a1 - st.lean * side), math.radians(arm.a2 - st.lean * side)
    E = (S[0] + math.sin(a1) * side * UPPER, S[1] + math.cos(a1) * UPPER)
    W = (E[0] + math.sin(a2) * side * FORE, E[1] + math.cos(a2) * FORE)
    if tgt and tgt[2] > 0.001:
        w = min(1.0, tgt[2])
        T = (W[0] + (tgt[0] - W[0]) * w, W[1] + (tgt[1] - W[1]) * w)
        E, W = ik2(S, T, UPPER, FORE, (side * 0.75, 0.66))
    return S, E, W, arm


def _arm(pen: Pen, st: "State", side: int, seed: int, C):
    S, E, Wr, arm = arm_points(st, side, C)
    lu, lf = math.hypot(E[0] - S[0], E[1] - S[1]) or 1, math.hypot(Wr[0] - E[0], Wr[1] - E[1]) or 1
    ux, uy = (E[0] - S[0]) / lu, (E[1] - S[1]) / lu
    fx, fy = (Wr[0] - E[0]) / lf, (Wr[1] - E[1]) / lf
    bend = math.acos(max(-1, min(1, ux * fx + uy * fy))) / math.pi          # 0 straight .. 1 folded
    bulge = 0.35 + 0.65 * max(arm.flex, bend * 0.9)
    sgn = 1 if (ux * fy - uy * fx) >= 0 else -1                             # bicep sits inside the fold
    nxu, nyu = -uy * sgn, ux * sgn
    bc = (S[0] + ux * lu * 0.56 + nxu * 15 * bulge, S[1] + uy * lu * 0.56 + nyu * 15 * bulge)
    fc = (E[0] + fx * lf * 0.30, E[1] + fy * lf * 0.30)
    a2 = math.atan2(fx * side, fy)
    # three passes: ink, shade, then skin nudged toward the light (up-left) so every limb gets a soft shaded edge
    for layer, (g, col, sh) in enumerate(((2 * LW, INK, 0), (0, SKIN_SH, 0), (-12, SKIN, 1))):
        o = (-4.5 * sh, -5.5 * sh)
        q = lambda p: (p[0] + o[0], p[1] + o[1])
        pen.tube(q(S), q(E), 88 + g, col)
        pen.tube(q(E), q(Wr), 64 + g, col)
        pen.dot(q(S), 58 + g / 2, col)                      # delt
        pen.dot(q(bc), 47 + 11 * bulge + g / 2, col)        # bicep
        pen.dot(q(fc), 41 + g / 2, col)                     # forearm
        if layer != 1:
            _hand(pen, Wr, a2, arm.hand, side, seed + 40, layer == 0)
    # blend the delt into the chest: wipe the ink where the shoulder ball overlaps the torso
    b0, b1 = ap(C, [(SHOULDER[0] * side - side * 4, SHOULDER[1] + 4), (SHOULDER[0] * side - side * 40, SHOULDER[1] - 4)])
    pen.tube(b0, b1, 62, SKIN)
    # muscle definition: delt / bicep split, and the bicep line when it is working
    px_, py_ = -uy, ux
    q = lambda t, o: (S[0] + ux * lu * t + px_ * o, S[1] + uy * lu * t + py_ * o)
    pen.line(bez(q(0.30, -40 * side), q(0.40, -8 * side), q(0.30, 22 * side), 8), seed + 7, LW * 0.5, amp=0.8)
    if bulge > 0.55:
        m0 = (S[0] + ux * lu * 0.40 + nxu * 22, S[1] + uy * lu * 0.40 + nyu * 22)
        m2 = (S[0] + ux * lu * 0.84 + nxu * 18, S[1] + uy * lu * 0.84 + nyu * 18)
        m1 = (bc[0] + nxu * 16, bc[1] + nyu * 16)
        pen.line(bez(m0, m1, m2, 8), seed + 6, LW * 0.55)


def _leg(pen: Pen, st: "State", side: int, seed: int, C, black_pass: bool):
    foot = st.footL if side < 0 else st.footR
    Hj = ap(C, [(HIP_J[0] * side, HIP_J[1])])[0]
    A = (foot[0], -foot[1] - ANKLE_H)
    K, A = ik2(Hj, A, THIGH, SHIN, (side * 0.6, -0.1), 1.25)
    g = 2 * LW if black_pass else 0
    col = INK if black_pass else PAPER
    pen.tube(Hj, K, 80 + g, col)
    pen.tube(K, A, 58 + g, col)
    cx, cy = K[0] + (A[0] - K[0]) * 0.34, K[1] + (A[1] - K[1]) * 0.34
    pen.dot((cx + side * 5, cy), 37 + g / 2, col)   # calf
    return Hj, K, A


def _shoe(pen: Pen, A: Pt, side: int, pitch: float, seed: int):
    M = mul(xf(A[0], A[1], pitch * side), (side, 0, 0, 1, 0, 0))
    sp = pen.at(M)
    shoe = [(-30, -12), (-26, -40), (14, -42), (44, -18), (76, -6), (84, 12), (78, 26), (-30, 26)]
    sp.shape(shoe, seed, (255, 255, 255, 255), amp=1.0)
    sp.line([(-30, 14), (82, 14)], seed + 1, LW * 0.6, amp=0.6)            # sole
    sp.shape([(4, -20), (30, -8), (22, 6), (-4, -6)], seed + 2, TEAL, LW * 0.5, amp=0.5)   # stripe
    sp.line([(-26, -40), (14, -42)], seed + 3, LW * 0.8, amp=0.6)          # sock line


def _shorts(pen: Pen, legs, C, seed: int):
    (HL, KL, _), (HR, KR, _) = legs
    hem = lambda Hj, K: (Hj[0] + (K[0] - Hj[0]) * 0.62, Hj[1] + (K[1] - Hj[1]) * 0.62)
    wl, wr = ap(C, [(-132, 318), (132, 318)])
    for black in (True, False):
        g = 2 * LW if black else 0
        col = INK if black else SHORTS
        pen.tube(HL, hem(HL, KL), 100 + g, col)
        pen.tube(HR, hem(HR, KR), 100 + g, col)
        pen.d.polygon(pen.px([wl, wr, (HR[0] + 50, HR[1] + 8), (HL[0] - 50, HL[1] + 8)]), fill=col)
        pen.tube(wl, wr, 30 + g, col)
    pen.line([(wl[0] + 20, wl[1] - 4), (wr[0] - 20, wr[1] - 4)], seed, LW * 0.5, (255, 255, 255, 255), amp=0.6)   # waistband
    mid = ((HL[0] + HR[0]) / 2, (HL[1] + HR[1]) / 2)
    pen.line([(mid[0] - 10, mid[1] - 20), (mid[0] - 4, mid[1] + 8)], seed + 1, LW * 0.45, (255, 255, 255, 255))     # drawstring
    pen.line([(mid[0] + 10, mid[1] - 20), (mid[0] + 6, mid[1] + 12)], seed + 2, LW * 0.45, (255, 255, 255, 255))


def _torso(pen: Pen, seed: int):
    L = [(-58, -44), (-66, 0), (-112, 8), (-176, 38), (-232, 58), (-246, 116), (-234, 184), (-204, 246), (-160, 296), (-134, 330),
         (-140, 430), (-156, 560), (-160, 800)]
    R = [(-x, y) for x, y in L]
    pen.shape(L + R[::-1], seed, SKIN)
    # collarbones + the dip between them
    pen.line(bez((-86, 30), (-52, 46), (-14, 40), 8), seed + 1, LW * 0.5)
    pen.line(bez((86, 30), (52, 46), (14, 40), 8), seed + 2, LW * 0.5)
    # black tank top: straps, scoop neck, deep arm holes
    scoop = bez((-94, 5), (-78, 116), (0, 122), 10) + bez((0, 122), (78, 116), (94, 5), 10)[1:]
    arm_r = bez((150, 26), (146, 150), (219, 214), 10)
    side_r = [(204, 246), (160, 296), (134, 330), (140, 430), (156, 560), (160, 800)]
    right = [(94, 5)] + arm_r + side_r
    left = [(-x, y) for x, y in right][::-1]
    tank = left + scoop[1:-1] + right
    pen.shape(tank, seed + 3, TANK, amp=1.2)
    # chest definition in a lighter ink so it reads on black
    pen.line(bez((-18, 250), (-104, 290), (-186, 226)), seed + 4, LW * 0.6, TANK_HI)
    pen.line(bez((18, 250), (104, 290), (186, 226)), seed + 5, LW * 0.6, TANK_HI)
    for k, yy in enumerate((330, 372)):
        pen.line(bez((-30, yy), (0, yy + 7), (30, yy), 6), seed + 20 + k, LW * 0.45, TANK_HI)
    pen.line(bez((-90, 14), (-76, 112), (0, 132), 10), seed + 8, LW * 0.45, TANK_HI, amp=0.8)   # neckline trim
    pen.line(bez((90, 14), (76, 112), (0, 132), 10), seed + 9, LW * 0.45, TANK_HI, amp=0.8)


def _head(pen: Pen, st: State, seed: int):
    H = lambda pts: rot(pts, st.head_rot, NECK_PIVOT, st.head_dx, st.head_dy, HEAD_K)
    cx, cy = HEAD_C
    drop = st.mouth.h * 0.20
    # neck, with the shadow the jaw throws on it
    neck = [(-56, -70), (-62, 8), (62, 8), (56, -70)]
    nk = [H([neck[0]])[0], neck[1], neck[2], H([neck[3]])[0]]
    pen.d.polygon(pen.px(nk), fill=SKIN)
    pen.d.polygon(pen.px([nk[0], (-60, -14), (0, 6), (60, -14), nk[3]]), fill=SKIN_SH)
    pen.line([nk[0], nk[1]], seed + 60)
    pen.line([nk[3], nk[2]], seed + 61)
    # cap brim poking out behind, to the screen-right
    brim = [(118, -338), (236, -372), (262, -346), (250, -318), (150, -292)]
    pen.shape(H(brim), seed + 1, CAP_DARK, amp=1.2)
    # ears
    for sd in (-1, 1):
        ear = arc(cx + sd * 150, cy + 8, 26, 36, 90 - sd * 108, 90 + sd * 108, 14)
        pen.shape(H(ear), seed + 2 + sd, SKIN_SH if sd > 0 else SKIN)
        pen.line(H(bez((cx + sd * 156, cy - 6), (cx + sd * 168, cy + 8), (cx + sd * 156, cy + 20), 6)), seed + 4 + sd, LW * 0.55)
    # head: shade colour first, then the lit face scaled toward the top-left, then the ink
    outline = _head_outline(drop)
    lit = [(cx - 16 + (x - cx + 16) * 0.93, cy - 20 + (y - cy + 20) * 0.94) for x, y in outline]
    pen.d.polygon(pen.px(H(outline)), fill=SKIN_SH)
    pen.d.polygon(pen.px(H(lit)), fill=SKIN)
    # short beard: a stubble shadow hugging the jaw, a moustache and the join down to the chin
    low = [(x, y) for x, y in outline if y > cy + 34]
    inner = [(cx + (x - cx) * 0.70, cy + 22 + (y - cy - 22) * 0.74) for x, y in low]
    pen.d.polygon(pen.px(H(low + inner[::-1])), fill=BEARD)
    my = -104
    pen.line(H(bez((-58, my - 20), (4, my - 40), (64, my - 20), 10)), seed + 50, 17, BEARD, wob=False)
    for sd in (-1, 1):
        pen.line(H([(4 + sd * 62, my - 20), (4 + sd * 60, my + 30 + drop)]), seed + 51 + sd, 15, BEARD, wob=False)
    for i, (x, y) in enumerate(_stubble()):
        yy = y + (drop * ((y + 150) / 110) if y > -150 else 0)
        pen.dot(H([(x, yy)])[0], 2.0, HAIR)
    for sd in (-1, 1):   # blush
        pen.d.polygon(pen.px(H(arc(sd * 84 + 2, -166, 24, 13, 0, 360, 16))), fill=BLUSH)
    pen.line(H(outline + [outline[0]]), seed + 6)
    # sideburns
    for sd in (-1, 1):
        sb = [(sd * 147, -275), (sd * 120, -272), (sd * 124, -214), (sd * 138, -180), (sd * 149, -224)]
        pen.shape(H(sb), seed + 8 + sd, HAIR, LW * 0.5, HAIR, amp=1.0)
    # cap dome, panel seams and a highlight
    dome = [(-160, -268)] + arc(0, -272, 160, 150, 180, 360, 30) + [(160, -268)] + bez((160, -268), (0, -292), (-160, -268), 16)
    pen.shape(H(dome), seed + 10, CAP)
    pen.d.polygon(pen.px(H(arc(0, -272, 160, 150, 300, 360, 10) + [(160, -268)] + bez((160, -268), (120, -280), (96, -284), 4) + bez((96, -284), (118, -350), (80, -402), 8))), fill=CAP_DARK)
    pen.line(H(bez((-70, -300), (-84, -372), (-34, -414), 8)), seed + 14, LW * 0.5, (150, 200, 250, 255))
    pen.line(H(bez((96, -284), (118, -350), (80, -402), 8)), seed + 15, LW * 0.45, CAP_DARK)
    pen.line(H(dome + [dome[0]]), seed + 10)
    # snapback opening with hair showing through, strap across
    gap = arc(0, -276, 62, 50, 180, 360, 16)
    pen.shape(H(gap + [(62, -276), (-62, -276)]), seed + 11, HAIR, LW * 0.8)
    pen.shape(H([(-66, -288), (66, -288), (66, -270), (-66, -270)]), seed + 12, CAP, LW * 0.7, amp=0.8)
    for dx in (-30, -10, 10, 30):
        pen.dot(H([(dx, -279)])[0], 3.2, CAP_DARK)
    pen.dot(H([(0, -422)])[0], 9, CAP_DARK)
    # eyes: almond whites, brown iris, heavy upper lid
    ey = cy - 4
    for sd in (-1, 1):
        ex = sd * 62 + 2
        if st.blink > 0.6:
            pen.line(H(bez((ex - 25, ey + 2), (ex, ey + 13), (ex + 25, ey + 2), 8)), seed + 20 + sd, LW * 1.1)
        else:
            rx, ry = 25, 19 * (1 - 0.55 * st.blink)
            eye = arc(ex, ey, rx, ry, 0, 360, 28)
            pen.d.polygon(pen.px(H(eye)), fill=WHITE)
            ix, iy = ex + st.look[0] * 9, ey + st.look[1] * 6 + 2
            pen.dot(H([(ix, iy)])[0], 12.5, IRIS)
            pen.dot(H([(ix, iy)])[0], 6.2, INK)
            pen.dot(H([(ix - 4.5, iy - 5)])[0], 3.0, WHITE)
            lid = max(st.lid, st.blink * 0.9)
            ly = ey - ry + 2 * ry * lid * 0.5
            a0 = math.degrees(math.asin(max(-1, min(1, (ly - ey) / ry))))
            top = arc(ex, ey, rx + 1, ry + 1, 180 - a0, 360 + a0, 14)
            pen.d.polygon(pen.px(H(top)), fill=SKIN)
            half = rx * math.sqrt(max(0.0, 1 - ((ly - ey) / ry) ** 2))
            pen.line(H(arc(ex, ey, rx, ry, 0, 180, 14)), seed + 21 + sd, LW * 0.5, wob=False)                     # lower lid, light
            pen.line(H([(ex - half - 3 , ly + 1), (ex - half * 0.4, ly - 3), (ex + half * 0.4, ly - 3), (ex + half + 3, ly + 1)]), seed + 23 + sd, LW * 1.15, wob=False)
        # brows: thick, dark, set low and angled in
        by = ey - 40 - 13 * st.brow
        tilt = 9 * st.brow_tilt
        inner, outer = (ex - sd * 32, by + tilt), (ex + sd * 34, by - 1 - tilt * 0.3)
        pen.line(H(bez(inner, (ex + sd * 2, by - 12), outer, 8)), seed + 24 + sd, LW * 2.0, HAIR, amp=1.0)
    # nose: the doodle hook, with a touch of shade under it
    pen.line(H(bez((6, -146), (22, -140), (30, -152), 5)), seed + 31, 9, SKIN_SH, wob=False)
    pen.line(H(bez((0, -186), (32, -152), (-2, -146), 10)), seed + 30, LW * 0.9)
    _draw_mouth(pen, st.mouth, H, seed + 40)


BOX = (-800, -1300, 800, 90)   # ground-space extents drawn around the feet (x0, y0, x1, y1)


def chest_matrix(st: State):
    """Chest space (origin = base of the neck) -> ground space: hips over the feet, upper body leaning about the hips."""
    hips = (st.hip_dx, -(HIP_H - st.crouch))
    return mul(xf(hips[0], hips[1], st.lean), xf(0, -TORSO_H))


def joints(st: State) -> dict:
    """Key points in ground space, for anything that needs to line up with the body (props, shadows)."""
    C = chest_matrix(st)
    out = {"hips": (st.hip_dx, -(HIP_H - st.crouch)), "head": ap(C, [(0, -291)])[0], "top": ap(C, [(0, -562)])[0]}
    for side, n in ((-1, "L"), (1, "R")):
        S, E, W, _ = arm_points(st, side, C)
        fx, fy = W[0] - E[0], W[1] - E[1]
        k = math.hypot(fx, fy) or 1
        out["hand" + n] = (W[0] + fx / k * 22, W[1] + fy / k * 22)
        out["shoulder" + n] = S
    return out


_logo_cache = {}


def _logo(im: Image.Image, pen: Pen, lean: float):
    """Optional logo on the tank top (a dark background melts into the black shirt)."""
    if not LOGO:
        return
    size = int(190 * pen.s)
    key = (size, round(lean))
    if key not in _logo_cache:
        if len(_logo_cache) > 60:
            _logo_cache.clear()
        src = Image.open(LOGO).convert("RGB").resize((size, size), Image.LANCZOS)
        a = Image.fromarray(np.asarray(src).max(axis=2)).point(lambda v: min(255, int(v * 1.5)))
        lg = src.convert("RGBA"); lg.putalpha(a)
        _logo_cache[key] = lg.rotate(-lean, expand=True, resample=Image.BICUBIC)
    lg = _logo_cache[key]
    x, y = pen.px([(0, 204)])[0]
    im.alpha_composite(lg, (int(x - lg.width / 2), int(y - lg.height / 2)))


def draw_mascot(st: State, scale: float = 1.0, sticker: bool = True) -> Tuple[Image.Image, Pt]:
    """Returns (RGBA image, origin): origin = the pixel of the ground point under the hips.
    Waist-up character: nothing is drawn below the tank top. `sticker` adds the white die-cut edge + soft shadow."""
    s = scale * SS
    W, Hh = int((BOX[2] - BOX[0]) * s), int((BOX[3] - BOX[1]) * s)
    im = Image.new("RGBA", (W, Hh), (0, 0, 0, 0))
    pen = Pen(ImageDraw.Draw(im), -BOX[0] * s, -BOX[1] * s, s, st.boil)
    C = chest_matrix(st)

    def tucked(side):   # a fist on the hip sits behind the torso
        a, t = (st.armL, st.handL) if side < 0 else (st.armR, st.handR)
        return a.a2 < 0 and a.hand == "fist" and a.a1 > 30 and not (t and t[2] > 0.3)
    for side, sd in ((-1, 500), (1, 600)):
        if tucked(side):
            _arm(pen, st, side, sd, C)
    _torso(pen.at(C), 100)
    _logo(im, pen.at(C), st.lean)
    pen.d = ImageDraw.Draw(im)
    _head(pen.at(C), st, 200)
    for side, sd in ((-1, 500), (1, 600)):
        if not tucked(side):
            _arm(pen, st, side, sd, C)
    out = im.resize((W // SS, Hh // SS), Image.LANCZOS)
    if sticker:   # white die-cut edge + soft shadow, built at quarter size so it stays cheap
        a = out.getchannel("A")
        q = 4
        small = a.resize((out.width // q, out.height // q), Image.BILINEAR)
        k = max(1, int(round(10 * scale / q))) * 2 + 1
        grown = small.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.GaussianBlur(0.8))
        edge = grown.resize(out.size, Image.BICUBIC).point(lambda v: 0 if v < 96 else min(255, (v - 96) * 6))
        soft = grown.filter(ImageFilter.GaussianBlur(3)).resize(out.size, Image.BILINEAR).point(lambda v: int(v * 0.30))
        base = Image.new("RGBA", out.size, (0, 0, 0, 0))
        sh = Image.new("RGBA", out.size, (0, 0, 0, 255)); sh.putalpha(soft)
        base.alpha_composite(sh, (int(8 * scale), int(12 * scale)))
        wh = Image.new("RGBA", out.size, (255, 255, 255, 255)); wh.putalpha(edge)
        base.alpha_composite(wh)
        base.alpha_composite(out)
        out = base
    return out, (-BOX[0] * scale, -BOX[1] * scale)


if __name__ == "__main__":   # model sheet: every mouth shape + every arm pose, full body
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "model_sheet.png"
    k = 0.42
    cells = [State(mouth=VISEMES[n]) for n in VISEMES]
    labels = list(VISEMES)
    for i, p in enumerate(ARM_POSES):
        other = "hips" if p not in ("hips", "up") else p
        cells.append(State(mouth=VISEMES["E" if i % 2 else "rest"], armR=ARM_POSES[p], armL=ARM_POSES[other], boil=i, head_rot=(-4, 0, 4)[i % 3]))
        labels.append(p)
    cells += [State(crouch=110, footL=(-120, 0, 0), footR=(120, 0, 0), armL=ARM_POSES["up"], armR=ARM_POSES["up"], mouth=VISEMES["A"]),
              State(lean=-14, footR=(250, 170, -35), hip_dx=-30, armL=ARM_POSES["open"], armR=ARM_POSES["open_low"]),
              State(handL=(-520, -640, 1), handR=(380, -900, 1), lean=4),
              State(lean=9, hip_dx=18, footL=(-70, 46, 12), mouth=VISEMES["O"])]
    labels += ["crouch", "kick", "IK reach", "step"]
    cols = 6
    w, h = draw_mascot(State(), k)[0].size
    sheet = Image.new("RGBA", (w * cols, h * math.ceil(len(cells) / cols)), (46, 196, 182, 255))
    d = ImageDraw.Draw(sheet)
    for i, (st, lab) in enumerate(zip(cells, labels)):
        im, _ = draw_mascot(st, k)
        x, y = (i % cols) * w, (i // cols) * h
        sheet.alpha_composite(im, (x, y)); d.text((x + 12, y + 8), lab, fill=INK)
    sheet.convert("RGB").save(out)
    print(out)
