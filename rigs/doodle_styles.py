"""The doodle rig in different cartoon art styles, all on the same body.

    img, origin = draw(state, scale, "simpsons")        # same contract as mascot3d.render

Styles: wimpy (notebook doodle), simpsons, familyguy, pokemon (90s TV anime cel look), anime (modern shonen).
Each style is a palette + line weight + its own head (shape, eyes, nose, mouth treatment, hair); the body, arms,
tank top, logo, IK and lip-sync mouth shapes are shared. These are original drawings in the manner of each
style: no characters, logos or frames from the shows are used.

The head "turns" the 2D way: features slide and foreshorten across the face with state.yaw / state.pitch.
"""
from __future__ import annotations

import math
import random
from dataclasses import replace
from typing import Callable, Dict, Tuple

from PIL import Image, ImageDraw, ImageFilter

import doodle_rig as M
from doodle_rig import Pen, State, arc, bez

CYAN, CYAN_D = (34, 214, 226, 255), (18, 160, 184, 255)
BLACK, WHITE = (18, 16, 20, 255), (255, 255, 255, 255)


def _turn(st: State, H: Callable, depth: float = 1.0) -> Callable:
    """Feature transform: slide + foreshorten with the head turn, then the usual head transform."""
    yaw, pitch = getattr(st, "yaw", 0.0), getattr(st, "pitch", 0.0)
    fx, fy, c = yaw * 1.55 * depth, pitch * 1.1 * depth, math.cos(math.radians(yaw * 0.9))
    return lambda pts: H([(x * c + fx, y + fy) for x, y in pts])


def _H(st: State) -> Callable:
    return lambda pts: M.rot(pts, st.head_rot, M.NECK_PIVOT, st.head_dx, st.head_dy, M.HEAD_K)


def _neck(pen: Pen, H, skin, shade, w: float = 56, line=True):
    nk = [H([(-w, -70)])[0], (-w - 6, 8), (w + 6, 8), H([(w, -70)])[0]]
    pen.d.polygon(pen.px(nk), fill=skin)
    if shade != skin:
        pen.d.polygon(pen.px([nk[0], (-w - 4, -14), (0, 6), (w + 4, -14), nk[3]]), fill=shade)
    if line:
        pen.line([nk[0], nk[1]], 60); pen.line([nk[3], nk[2]], 61)


def _cap(pen: Pen, H, seed: int, y0: float = -268, rx: float = 160, top: float = 150, brim=True, strap=True, hair=M.HAIR, col=CYAN, dark=CYAN_D):
    """Backwards cap: dome, strap gap with hair showing, brim poking out behind to screen-right."""
    if brim:
        pen.shape(H([(rx * 0.74, y0 - 70), (rx * 1.48, y0 - 104), (rx * 1.64, y0 - 78), (rx * 1.56, y0 - 50), (rx * 0.94, y0 - 24)]), seed + 1, dark, amp=1.0)
    dome = [(-rx, y0)] + arc(0, y0 - 4, rx, top, 180, 360, 30) + [(rx, y0)] + bez((rx, y0), (0, y0 - 24), (-rx, y0), 16)
    pen.shape(H(dome), seed + 2, col)
    if strap:
        gap = arc(0, y0 - 8, 62, 50, 180, 360, 16)
        pen.shape(H(gap + [(62, y0 - 8), (-62, y0 - 8)]), seed + 3, hair, M.LW * 0.8)
        pen.shape(H([(-66, y0 - 20), (66, y0 - 20), (66, y0 - 2), (-66, y0 - 2)]), seed + 4, col, M.LW * 0.7, amp=0.6)
    pen.dot(H([(0, y0 - top - 4)])[0], 9, dark)


def _mouth(pen: Pen, st: State, F, k: float = 1.0, wk: float = 1.0, dy: float = 0.0):
    """Shared lip-sync mouth, scaled about its centre for styles with smaller or wider mouths."""
    cx, cy = 4.0, -104.0
    G = lambda pts: F([(cx + (x - cx) * k * wk, cy + dy + (y - cy) * k) for x, y in pts])
    M._draw_mouth(pen, st.mouth, G, 40)


def _stache_dots(pen: Pen, F, n: int = 40, y: float = -128, w: float = 58, col=M.HAIR, r: float = 1.9, arch: float = 16):
    rr = random.Random(5)
    for _ in range(n):
        t = rr.uniform(0, 1)
        pen.dot(F([(-w + 4 + 2 * w * t, y - arch * (1 - (2 * t - 1) ** 2) + rr.uniform(-7, 7))])[0], r, col)


# ───────────────────────────── heads ─────────────────────────────

def head_wimpy(pen: Pen, st: State):
    """Notebook doodle: wobbly black line, paper-white fill, ring eyes with dot pupils, hook nose."""
    H = _H(st); F = _turn(st, H)
    cx, cy = M.HEAD_C
    _neck(pen, H, M.SKIN, M.SKIN)
    for sd in (-1, 1):
        pen.shape(H(arc(cx + sd * 150, cy + 8, 26, 36, 90 - sd * 108, 90 + sd * 108, 14)), 2 + sd, M.SKIN)
    pen.shape(H(M._head_outline(st.mouth.h * 0.2)), 6, M.SKIN)
    for sd in (-1, 1):
        pen.shape(H([(sd * 147, -275), (sd * 122, -272), (sd * 126, -220), (sd * 146, -232)]), 8 + sd, BLACK, M.LW * 0.5, BLACK)
    _cap(pen, H, 10, hair=BLACK)
    ey = cy - 2
    for sd in (-1, 1):
        ex = sd * 60 + 2
        if st.blink > 0.6:
            pen.line(F(bez((ex - 25, ey + 2), (ex, ey + 14), (ex + 25, ey + 2), 8)), 20 + sd)
        else:
            pen.shape(F(arc(ex, ey, 25, 27 * (1 - 0.55 * st.blink), 0, 360, 24)), 20 + sd, WHITE, M.LW * 0.85, amp=0.9)
            pen.dot(F([(ex + st.look[0] * 10, ey + st.look[1] * 9 + 2)])[0], 8.5, BLACK)
        by = ey - 46 - 13 * st.brow
        pen.line(F(bez((ex - sd * 30, by + 6), (ex, by - 9), (ex + sd * 32, by - 2), 8)), 24 + sd, M.LW * 1.3, BLACK)
    pen.line(F(bez((0, -182), (30, -150), (-2, -146), 10)), 30, M.LW * 0.9)
    for i in range(7):   # a few scratchy moustache strokes
        x = -42 + i * 14
        pen.line(F([(x, -132 - 5 * (1 - abs(i - 3) / 3)), (x + 3, -122)]), 50 + i, M.LW * 0.5)
    _mouth(pen, st, F)


def head_simpsons(pen: Pen, st: State):
    """Springfield look: yellow skin, big round white eyes with dot pupils, no chin, the stubble muzzle, thin black line."""
    H = _H(st); F = _turn(st, H)
    skin = M.SKIN
    _neck(pen, H, skin, skin, w=44)
    for sd in (-1, 1):   # ears: a simple C with the inner squiggle
        pen.shape(H(arc(sd * 146, -196, 24, 30, 90 - sd * 110, 90 + sd * 110, 12)), 2 + sd, skin)
        pen.line(H(bez((sd * 150, -206), (sd * 164, -196), (sd * 150, -186), 6)), 4 + sd, M.LW * 0.7)
    # head: tall rounded cylinder that runs straight into the jaw (no chin)
    drop = st.mouth.h * 0.25
    out = [(-142, -300)] + bez((-142, -300), (-150, -150), (-112, -70 + drop), 12) + bez((-112, -70 + drop), (0, -22 + drop), (112, -70 + drop), 14) \
        + bez((112, -70 + drop), (150, -150), (142, -300), 12)
    pen.shape(H(out), 6, skin)
    for sd in (-1, 1):
        pen.shape(H([(sd * 144, -292), (sd * 126, -292), (sd * 120, -250), (sd * 134, -262), (sd * 128, -232), (sd * 145, -246)]), 8 + sd, M.HAIR, M.LW * 0.6)
    _cap(pen, H, 10, y0=-284, rx=154, top=128)
    # muzzle: the five-o'clock-shadow shape around the mouth
    muz = arc(4, -108 + drop * 0.4, 100, 62 + drop * 0.5, 0, 360, 40)
    pen.shape(F(muz), 12, (214, 182, 112, 255), M.LW * 0.8)
    _mouth(pen, st, F, k=0.92, wk=1.1, dy=4)
    # nose: a rounded sausage hanging between the eyes, over the muzzle
    pen.shape(F(arc(8, -168, 30, 22, 0, 360, 22)), 14, skin)
    ey = -226
    for sd in (1, -1):   # eyes: big, round, touching; tiny pupils
        ex = sd * 44 + 4
        if st.blink > 0.6:
            pen.shape(F(arc(ex, ey, 46, 44, 0, 360, 30)), 20 + sd, skin)
            pen.line(F(bez((ex - 44, ey + 4), (ex, ey + 20), (ex + 44, ey + 4), 8)), 22 + sd)
        else:
            pen.shape(F(arc(ex, ey, 46, 46 * (1 - 0.5 * st.blink), 0, 360, 30)), 20 + sd, WHITE)
            pen.dot(F([(ex - sd * 8 + st.look[0] * 16, ey + 4 + st.look[1] * 14)])[0], 6.5, BLACK)
            lid = max(0.0, st.lid - 0.15) * 0.8 + st.blink * 0.5
            if lid > 0.05:
                top = arc(ex, ey, 46, 46, 215 - 60 * lid, 325 + 60 * lid, 12)
                pen.shape(F(top), 24 + sd, skin)
        by = ey - 60 - 12 * st.brow
        pen.line(F(bez((ex - sd * 34, by + 10 * st.brow_tilt), (ex, by - 8), (ex + sd * 36, by + 2), 8)), 26 + sd, M.LW * 1.5, M.HAIR)


def head_familyguy(pen: Pen, st: State):
    """Quahog look: flat peach skin, bold black line, egg eyes set close, U nose, a big round chin with the cleft."""
    H = _H(st); F = _turn(st, H)
    skin = M.SKIN
    _neck(pen, H, skin, skin, w=60)
    for sd in (-1, 1):
        pen.shape(H(arc(sd * 152, -200, 22, 30, 90 - sd * 110, 90 + sd * 110, 12)), 2 + sd, skin)
    drop = st.mouth.h * 0.3
    out = [(-146, -300)] + bez((-146, -300), (-166, -160), (-150, -92), 10) + bez((-150, -92), (-140, -18 + drop), (0, -10 + drop), 12) \
        + bez((0, -10 + drop), (140, -18 + drop), (150, -92), 12) + bez((150, -92), (166, -160), (146, -300), 10)
    pen.shape(H(out), 6, skin)
    pen.line(F([(-12, -30 + drop), (0, -22 + drop), (12, -30 + drop)]), 7, M.LW * 0.8)        # chin cleft
    for sd in (-1, 1):
        pen.shape(H([(sd * 148, -294), (sd * 128, -292), (sd * 132, -236), (sd * 150, -246)]), 8 + sd, M.HAIR, M.LW * 0.6)
    _cap(pen, H, 10, y0=-282, rx=158, top=132)
    ey = -216
    for sd in (-1, 1):
        ex = sd * 32 + 3
        if st.blink > 0.6:
            pen.line(F(bez((ex - 28, ey), (ex, ey + 14), (ex + 28, ey), 8)), 20 + sd)
        else:
            pen.shape(F(arc(ex, ey, 30, 38 * (1 - 0.5 * st.blink), 0, 360, 28)), 20 + sd, WHITE)
            pen.dot(F([(ex + st.look[0] * 12, ey + 4 + st.look[1] * 12)])[0], 6.5, BLACK)
        by = ey - 52 - 12 * st.brow
        pen.line(F(bez((ex - sd * 22, by + 10 * st.brow_tilt + 4), (ex + sd * 6, by - 8), (ex + sd * 40, by + 4), 8)), 24 + sd, M.LW * 1.25, M.HAIR)
    pen.line(F(bez((-26, -180), (-30, -140), (4, -138), 8) + bez((4, -138), (38, -140), (34, -180), 8)[1:]), 30)       # U nose
    _stache_dots(pen, F, 46, y=-122, w=64, r=2.2, arch=10)
    _mouth(pen, st, F, k=1.0, wk=1.25, dy=10)


def _anime_head(pen: Pen, st: State, sharp: float, eye_h: float, detail: bool):
    """Shared anime construction; `sharp` pulls the chin to a point, `detail` adds the modern eye and hair work."""
    H = _H(st); F = _turn(st, H)
    skin, shade, line = M.SKIN, M.SKIN_SH, M.INK
    _neck(pen, H, skin, shade, w=46)
    for sd in (-1, 1):
        pen.shape(H(arc(sd * 150, -196, 20, 34, 90 - sd * 110, 90 + sd * 110, 12)), 2 + sd, skin)
    drop = st.mouth.h * 0.22
    cy = -34 + drop
    jaw = 150 - 34 * sharp
    out = [(-150, -300)] + bez((-150, -300), (-158, -190), (-jaw, -120), 10) + bez((-jaw, -120), (-70, cy - 8), (0, cy), 10) \
        + bez((0, cy), (70, cy - 8), (jaw, -120), 10) + bez((jaw, -120), (158, -190), (150, -300), 10)
    pen.shape(H(out), 6, skin)
    # cel shadow: under the cap across the forehead, and down the screen-right cheek
    pen.d.polygon(pen.px(H(bez((-150, -292), (0, -250), (150, -292), 12) + [(150, -262), (-150, -262)])), fill=shade)
    pen.d.polygon(pen.px(H(bez((jaw + 2, -122), (96, -70), (30, cy - 2), 8) + bez((30, cy - 2), (110, -92), (150, -210), 8))), fill=shade)
    pen.line(H(out + [out[0]]), 6)
    # spiky hair bursting out from under the cap
    spikes = [(-176, -214), (-150, -252), (-190, -262), (-152, -288)]
    for sd in (-1, 1):
        pts = [(sd * 150, -300)] + [(sd * abs(x), y) for x, y in spikes[::-1]] + [(sd * 140, -206), (sd * 128, -250)]
        pen.shape(H(pts), 8 + sd, M.HAIR, M.LW * 0.8)
    _cap(pen, H, 10, y0=-284, rx=158, top=134, hair=M.HAIR)
    if detail:   # bangs through the strap opening, with a highlight streak
        bang = [(-58, -282), (-40, -236), (-22, -272), (-4, -226), (16, -272), (34, -236), (56, -282)]
        pen.shape(F(bang), 14, M.HAIR, M.LW * 0.8)
        pen.line(F([(-20, -262), (-6, -244)]), 15, M.LW * 0.6, (120, 96, 96, 255), wob=False)
    ey = -196
    for sd in (-1, 1):
        ex = sd * 66 + 2
        w, h = 34, eye_h * (1 - 0.6 * st.blink)
        if st.blink > 0.6:
            pen.line(F(bez((ex - w, ey + 4), (ex, ey + 14), (ex + w, ey + 4), 8)), 20 + sd, M.LW * 1.3)
        else:
            eye = [(ex - w, ey - h * 0.55), (ex + w, ey - h * 0.62), (ex + w * 0.94, ey + h * 0.5), (ex - w * 0.9, ey + h * 0.55)]
            pen.d.polygon(pen.px(F(eye)), fill=WHITE)
            ix, iy = ex + st.look[0] * 8, ey + st.look[1] * 6
            iris = arc(ix, iy, w * 0.66, h * 0.62, 0, 360, 24)
            pen.d.polygon(pen.px(F(iris)), fill=(96, 58, 36, 255))
            if detail:
                pen.d.polygon(pen.px(F(arc(ix, iy + h * 0.22, w * 0.56, h * 0.36, 0, 360, 20))), fill=(176, 112, 62, 255))
            pen.dot(F([(ix, iy)])[0], w * 0.26, (20, 12, 12, 255))
            pen.dot(F([(ix - w * 0.26, iy - h * 0.30)])[0], w * 0.20, WHITE)
            if detail:
                pen.dot(F([(ix + w * 0.24, iy + h * 0.26)])[0], w * 0.10, WHITE)
            pen.line(F([(ex - w - 6 * sd * 0, ey - h * 0.55), (ex + w, ey - h * 0.62)]), 22 + sd, M.LW * 1.9, line, wob=False)          # lash line
            pen.line(F([(ex + sd * w, ey - h * 0.6), (ex + sd * (w + 9), ey - h * 0.78)]), 23 + sd, M.LW * 1.2, line, wob=False)        # outer flick
            if detail:
                pen.line(F(bez((ex - w * 0.8, ey - h * 0.86), (ex, ey - h * 0.98), (ex + w * 0.8, ey - h * 0.9), 6)), 28 + sd, M.LW * 0.5, wob=False)
                pen.line(F([(ex - w * 0.5, ey + h * 0.58), (ex + w * 0.6, ey + h * 0.55)]), 29 + sd, M.LW * 0.5, wob=False)
        by = ey - h * 0.62 - 26 - 12 * st.brow
        pen.line(F(bez((ex - sd * 30, by + 10 * st.brow_tilt + 6), (ex, by - 4), (ex + sd * 36, by - 2), 8)), 24 + sd, M.LW * (1.5 if not detail else 1.2), M.HAIR)
    if detail:
        pen.d.polygon(pen.px(F([(2, -150), (14, -132), (0, -130)])), fill=shade)          # nose shadow
        for sd in (-1, 1):
            for i in range(3):
                x = sd * (86 + i * 10)
                pen.line(F([(x, -150), (x - 6, -138)]), 34 + i + sd, M.LW * 0.4, (224, 132, 124, 255), wob=False)
    else:
        pen.line(F([(2, -150), (10, -136), (0, -134)]), 30, M.LW * 0.7)
    _stache_dots(pen, F, 26 if detail else 22, y=-116, w=40, r=1.7, arch=8)
    _mouth(pen, st, F, k=0.78, wk=0.9, dy=10)


def head_pokemon(pen: Pen, st: State):
    """90s TV-anime cel look: round face, big simple brown eyes with one highlight, hard two-tone shading."""
    _anime_head(pen, st, sharp=0.35, eye_h=40, detail=False)


def head_anime(pen: Pen, st: State):
    """Modern shonen look: pointed chin, tall detailed eyes, bangs with a highlight, blush hatching, finer line."""
    _anime_head(pen, st, sharp=1.0, eye_h=50, detail=True)


# ───────────────────────────── style table ─────────────────────────────

STYLES: Dict[str, dict] = {
    "wimpy": dict(head=head_wimpy, LW=6.5, wob=1.25, boil=True, edge=True, page=(214, 196, 150),
                  pal=dict(SKIN=(252, 250, 244, 255), SKIN_SH=(252, 250, 244, 255), INK=BLACK, HAIR=BLACK, TANK=(26, 26, 30, 255), TANK_HI=(90, 90, 96, 255))),
    "simpsons": dict(head=head_simpsons, LW=4.6, wob=0.35, boil=False, edge=False, page=(118, 196, 240), fingers=3,
                     pal=dict(SKIN=(255, 217, 15, 255), SKIN_SH=(255, 217, 15, 255), INK=BLACK, HAIR=(70, 52, 30, 255), TANK=(30, 30, 36, 255), TANK_HI=(84, 86, 98, 255))),
    "familyguy": dict(head=head_familyguy, LW=5.6, wob=0.35, boil=False, edge=False, page=(150, 190, 120),
                      pal=dict(SKIN=(250, 206, 168, 255), SKIN_SH=(250, 206, 168, 255), INK=BLACK, HAIR=(64, 44, 30, 255), TANK=(28, 28, 34, 255), TANK_HI=(84, 86, 98, 255))),
    "pokemon": dict(head=head_pokemon, LW=4.4, wob=0.25, boil=False, edge=False, page=(88, 170, 230),
                    pal=dict(SKIN=(253, 222, 190, 255), SKIN_SH=(238, 184, 150, 255), INK=(44, 30, 40, 255), HAIR=(34, 28, 36, 255), TANK=(34, 34, 44, 255), TANK_HI=(92, 94, 112, 255))),
    "anime": dict(head=head_anime, LW=3.6, wob=0.25, boil=False, edge=False, page=(70, 60, 120),
                  pal=dict(SKIN=(255, 228, 206, 255), SKIN_SH=(240, 188, 170, 255), INK=(52, 36, 50, 255), HAIR=(40, 30, 44, 255), TANK=(30, 30, 40, 255), TANK_HI=(98, 100, 124, 255))),
}
FINGERS4 = [(-27, 44), (-9, 54), (9, 52), (27, 42)]
FINGERS3 = [(-20, 46), (0, 55), (20, 46)]


def draw(st: State, scale: float = 1.0, style: str = "wimpy", sticker: bool = True, y_max: float = None) -> Tuple[Image.Image, Tuple[float, float]]:
    """RGBA sprite + origin for one frame of the mascot in `style`."""
    S = STYLES[style]
    saved = {k: getattr(M, k) for k in list(S["pal"]) + ["LW", "FINGERS"]}
    old_amp = Pen.AMP
    try:
        for k, v in S["pal"].items():
            setattr(M, k, v)
        M.LW = S["LW"]
        M.FINGERS = FINGERS3 if S.get("fingers") == 3 else FINGERS4
        Pen.AMP = S["wob"]
        st = replace(st, lean=0.0, hip_dx=0.0, boil=st.boil if S["boil"] else 0)
        s = scale * M.SS
        BOX = M.BOX
        W, Hh = int((BOX[2] - BOX[0]) * s), int((BOX[3] - BOX[1]) * s)
        im = Image.new("RGBA", (W, Hh), (0, 0, 0, 0))
        pen = Pen(ImageDraw.Draw(im), -BOX[0] * s, -BOX[1] * s, s, st.boil)
        C = M.chest_matrix(st)

        def tucked(side):
            a, t = (st.armL, st.handL) if side < 0 else (st.armR, st.handR)
            return a.a2 < 0 and a.hand == "fist" and a.a1 > 30 and not (t and t[2] > 0.3)
        for side, sd in ((-1, 500), (1, 600)):
            if tucked(side):
                M._arm(pen, st, side, sd, C)
        M._torso(pen.at(C), 100)
        M._logo(im, pen.at(C), 0.0)
        pen.d = ImageDraw.Draw(im)
        S["head"](pen.at(C), st)
        for side, sd in ((-1, 500), (1, 600)):
            if not tucked(side):
                M._arm(pen, st, side, sd, C)
        out = im.resize((W // M.SS, Hh // M.SS), Image.LANCZOS)
    finally:
        for k, v in saved.items():
            setattr(M, k, v)
        Pen.AMP = old_amp
    if sticker:
        a = out.getchannel("A")
        q = 4
        small = a.resize((out.width // q, out.height // q), Image.BILINEAR)
        base = Image.new("RGBA", out.size, (0, 0, 0, 0))
        soft = small.filter(ImageFilter.GaussianBlur(6 * scale)).resize(out.size, Image.BILINEAR).point(lambda v: int(v * 0.34))
        sh = Image.new("RGBA", out.size, (8, 12, 24, 255)); sh.putalpha(soft)
        base.alpha_composite(sh, (int(10 * scale), int(14 * scale)))
        if S["edge"]:   # paper-cutout edge for the notebook doodle
            k = max(1, int(round(9 * scale / q))) * 2 + 1
            grown = small.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.GaussianBlur(0.8))
            edge = grown.resize(out.size, Image.BICUBIC).point(lambda v: 0 if v < 96 else min(255, (v - 96) * 6))
            wh = Image.new("RGBA", out.size, (255, 255, 255, 255)); wh.putalpha(edge)
            base.alpha_composite(wh)
        base.alpha_composite(out)
        out = base
    return out, (-M.BOX[0] * scale, -M.BOX[1] * scale)


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "styles.png"
    P = M.ARM_POSES
    a = State(armR=P["open"], armL=P["hips"], mouth=M.VISEMES["A"], brow=0.4)
    b = State(armR=P["point_up"], mouth=M.VISEMES["rest"]); b.yaw = -22
    names = list(STYLES)
    cells = []
    for n in names:
        for s_ in (a, b):
            im = draw(s_, 0.9, n)[0].crop((330, 60, 1110, 1150))
            bg = Image.new("RGBA", im.size, tuple(STYLES[n]["page"]) + (255,))
            bg.alpha_composite(im)
            cells.append(bg)
    w, h = cells[0].size
    sheet = Image.new("RGB", (w * len(names), h * 2))
    for i, c in enumerate(cells):
        sheet.paste(c.convert("RGB"), ((i // 2) * w, (i % 2) * h))
    sheet.resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS).save(out)
    print(out)
