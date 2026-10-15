#!/usr/bin/env python3
"""collage.py WORKDIR MODE   (documentary-collage style; render.py hands off here when spec.style == "collage")
MODES: --check | --preview T [T ...] | --run | --finish OUT.mp4

A physical desk ("world", larger than the screen) holds paper props: documents, clippings, graph-paper charts,
sticky notes, title strips, stamps and the user's photos. A camera with handheld drift travels across it.
Marker annotations draw themselves on and 'boil' like hand animation. Sound: paper slaps, stamp thuds,
marker scratches, optional ducked music.
"""
import json, math, os, re, subprocess, sys, time, glob, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

W, H, FPS, SEG_SEC = 1080, 1920, 30, 15
WORK = sys.argv[1]
J = lambda n: os.path.join(WORK, n)
HERE = os.path.dirname(os.path.abspath(__file__))
FD = os.path.join(HERE, '..', 'assets', 'fonts')
info = json.load(open(J('probe.json'))); PHR = json.load(open(J('phrases.json')))
TIM = json.load(open(J('timing.json'))); SPEC = json.load(open(J('spec.json')))
T0 = float(SPEC['trim'][0]) if 'trim' in SPEC else max(0.0, info['speech_start'] - float(SPEC.get('lead_in', 0.3)))
T1 = float(SPEC['trim'][1]) if 'trim' in SPEC else min(info['duration'], info['speech_end'] + float(SPEC.get('tail', 0.8)))
NFR = max(1, int(round((T1 - T0) * FPS)))
RES = 1.6          # sprites are drawn at 1.6x world scale so camera push-ins stay sharp
rng0 = np.random.default_rng(11)

def tref(v, default=None):
    if v is None: return default
    if isinstance(v, (int, float)): return float(v)
    m = re.match(r'^\s*(p(\d+)(\.end)?|start|end)\s*([+-]\s*[\d.]+)?\s*$', str(v))
    if not m: raise ValueError(f'bad time ref {v!r}')
    if m.group(1) == 'start': b = T0
    elif m.group(1) == 'end': b = T1
    else:
        i = int(m.group(2))
        if i >= len(TIM): raise ValueError(f'{v!r}: only p0..p{len(TIM) - 1}')
        b = TIM[i]['end'] if m.group(3) else TIM[i]['start']
    return b + (float(m.group(4).replace(' ', '')) if m.group(4) else 0.0)

clamp = lambda x, a=0.0, b=1.0: max(a, min(b, x))
prog = lambda t, t0, d: clamp((t - t0) / d) if d > 0 else float(t >= t0)
def inout(x): return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2
def outq(x): return 1 - (1 - x) ** 4
def expo(x): return 1.0 if x >= 1 else (0.0 if x <= 0 else 1 - 2 ** (-10 * x))

# ------------------------------------------------------------------ fonts / colours
_fc = {}
FONTS = dict(type='SpecialElite', typebold='CourierPrimeBold', hand='Caveat', title='Anton', cond='Oswald', serif='Newsreader',
             sans='BricolageGrotesque', display='Fraunces')
def font(role, size, wght=None):
    name = FONTS.get(role, role)
    k = (name, int(size), wght)
    if k not in _fc:
        f = ImageFont.truetype(os.path.join(FD, name + '.ttf'), int(size))
        try:
            ax = f.get_variation_axes(); vals = []
            for a in ax:
                nm = a['name'].decode() if isinstance(a['name'], bytes) else a['name']
                if nm == 'Weight': vals.append(clamp(wght or {'hand': 600, 'cond': 600, 'serif': 700, 'sans': 650, 'display': 600}.get(role, 600), a['minimum'], a['maximum']))
                elif nm.lower().startswith('optical'): vals.append(clamp(size / 2, a['minimum'], a['maximum']))
                elif nm == 'Width': vals.append(100)
                else: vals.append(a.get('default', a['minimum']))
            f.set_variation_by_axes(vals)
        except Exception:
            pass
        _fc[k] = f
    return _fc[k]
COL = dict(ink=(32, 30, 28), paper=(240, 233, 216), news=(226, 221, 206), kraft=(196, 164, 120), sticky=(245, 222, 110),
           red=(196, 40, 36), blue=(36, 70, 150), green=(40, 120, 70), graph=(232, 238, 228), grid=(120, 170, 160),
           hilite=(255, 226, 60), white=(250, 248, 242), black=(18, 18, 18), muted=(110, 104, 96))
COL.update({k: tuple(int(v.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)) for k, v in SPEC.get('palette', {}).items()})
def col(c, a=255):
    if isinstance(c, (list, tuple)): return tuple(c[:3]) + (a,)
    if str(c).startswith('#'): return tuple(int(c[1:][i:i + 2], 16) for i in (0, 2, 4)) + (a,)
    return COL[c] + (a,)

# ------------------------------------------------------------------ textures
def noise(h, w, scale, seed):
    r = np.random.default_rng(seed)
    small = r.normal(0, 1, (max(2, h // scale + 2), max(2, w // scale + 2))).astype(np.float32)
    im = Image.fromarray(((small - small.min()) / (np.ptp(small) + 1e-6) * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    return np.asarray(im).astype(np.float32) / 255 - 0.5

def paper_tex(w, h, base, seed, fibers=True, edge_dark=0.10):
    b = np.array(base, np.float32)
    a = np.ones((h, w, 3), np.float32) * b
    m = noise(h, w, 60, seed) * 16 + noise(h, w, 12, seed + 1) * 7
    a += m[..., None]
    a += np.random.default_rng(seed + 2).normal(0, 3.2, (h, w))[..., None]
    if fibers:
        fib = np.zeros((h, w), np.float32); r = np.random.default_rng(seed + 3)
        im = Image.fromarray(fib, 'F'); d = ImageDraw.Draw(im)
        for _ in range(int(w * h / 2500)):
            x, y = r.uniform(0, w), r.uniform(0, h); L = r.uniform(4, 18); an = r.uniform(0, math.pi)
            d.line((x, y, x + L * math.cos(an), y + L * math.sin(an)), fill=float(r.uniform(-14, 10)), width=1)
        a += np.asarray(im)[..., None] * 0.6
    yy, xx = np.mgrid[0:h, 0:w]
    e = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy)).astype(np.float32)
    a *= (1 - edge_dark * np.exp(-e / (0.05 * min(w, h) + 1)))[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert('RGBA')

def torn_mask(w, h, sides, seed, amp=7):
    m = Image.new('L', (w, h), 255); d = ImageDraw.Draw(m); r = np.random.default_rng(seed)
    def walk(n):
        v = np.cumsum(r.normal(0, 1.4, n)); v -= np.linspace(v[0], v[-1], n); v = v / (np.abs(v).max() + 1e-6) * amp
        return v + r.uniform(0, amp * 0.5, n) + amp
    if 'top' in sides:
        v = walk(w); d.polygon([(0, 0)] + [(x, v[x]) for x in range(w)] + [(w, 0)], fill=0)
    if 'bottom' in sides:
        v = walk(w); d.polygon([(0, h)] + [(x, h - v[x]) for x in range(w)] + [(w, h)], fill=0)
    if 'left' in sides:
        v = walk(h); d.polygon([(0, 0)] + [(v[y], y) for y in range(h)] + [(0, h)], fill=0)
    if 'right' in sides:
        v = walk(h); d.polygon([(w, 0)] + [(w - v[y], y) for y in range(h)] + [(w, h)], fill=0)
    return m

def desk(wd, ht, kind, seed=5):
    if kind == 'cork':
        base = (150, 112, 76); a = paper_tex(wd, ht, base, seed, fibers=False, edge_dark=0)
        arr = np.asarray(a).astype(np.float32)[..., :3]
        arr += (np.random.default_rng(seed).random((ht, wd)) > 0.985)[..., None] * -40
    else:   # dark walnut planks: long fibres along y, gentle warp, seams
        r = np.random.default_rng(seed)
        def streak(sx, sy, sd):
            sm = r.normal(0, 1, (max(2, ht // sy + 2), max(2, wd // sx + 2))).astype(np.float32)
            im = Image.fromarray(((sm - sm.min()) / (np.ptp(sm) + 1e-6) * 255).astype(np.uint8)).resize((wd, ht), Image.BICUBIC)
            return np.asarray(im).astype(np.float32) / 255 - 0.5
        fib = streak(3, 260, 1) * 0.9 + streak(9, 600, 2) * 0.8 + streak(40, 900, 3) * 0.6
        base = np.array(COL.get('desk', (58, 40, 29)), np.float32)
        arr = base * (1 + fib[..., None] * 0.55) + noise(ht, wd, 70, seed + 4)[..., None] * 14
        pw = int(WORLD.get('plank', 520)); off = r.integers(0, 400, wd // pw + 2)
        for k, x in enumerate(range(pw, wd, pw)):
            arr[:, x - 2:x + 2] *= 0.55; arr[:, x + 2:x + 5] *= 1.08
            for yy in range(int(off[k]), ht, 1300): arr[yy - 2:yy + 2, x - pw + 2:x - 2] *= 0.6
        arr += r.normal(0, 2.0, (ht, wd))[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

# ------------------------------------------------------------------ hand-drawn strokes
def wobble_path(pts, seed, amp=2.2, step=6):
    """resample a polyline, add low-frequency hand wobble."""
    out = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        n = max(2, int(math.dist((x0, y0), (x1, y1)) / step))
        for k in range(n): out.append((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
    out.append(pts[-1])
    r = np.random.default_rng(seed); n = len(out)
    wx = np.convolve(r.normal(0, 1, n + 12), np.ones(12) / 12, 'valid')[:n] * amp * 3
    wy = np.convolve(r.normal(0, 1, n + 12), np.ones(12) / 12, 'valid')[:n] * amp * 3
    return [(x + wx[i], y + wy[i]) for i, (x, y) in enumerate(out)]

def ellipse_pts(cx, cy, rx, ry, seed, turns=1.12):
    r = np.random.default_rng(seed); a0 = r.uniform(0, 2 * math.pi); n = 90
    pts = []
    for k in range(int(n * turns)):
        a = a0 + 2 * math.pi * k / n; g = 1 + 0.05 * math.sin(a * 2 + seed) + 0.04 * (k / n)
        pts.append((cx + rx * g * math.cos(a), cy + ry * g * math.sin(a)))
    return pts

def draw_stroke(d, pts, frac, color, width):
    if frac <= 0 or len(pts) < 2: return
    n = max(2, int(len(pts) * frac))
    d.line(pts[:n], fill=color, width=int(width), joint='curve')
    r = width / 2
    for p in (pts[0], pts[n - 1]): d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=color)

def arrow_pts(x0, y0, x1, y1, bend=0.18):
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2; dx, dy = x1 - x0, y1 - y0
    cx, cy = mx - dy * bend, my + dx * bend
    return [((1 - u) ** 2 * x0 + 2 * (1 - u) * u * cx + u * u * x1, (1 - u) ** 2 * y0 + 2 * (1 - u) * u * cy + u * u * y1) for u in np.linspace(0, 1, 30)]

def arrow_head(pts, size):
    (xa, ya), (xb, yb) = pts[-4], pts[-1]; an = math.atan2(yb - ya, xb - xa)
    return [[(xb - size * math.cos(an - 0.5), yb - size * math.sin(an - 0.5)), (xb, yb)], [(xb, yb), (xb - size * math.cos(an + 0.5), yb - size * math.sin(an + 0.5))]]

# ------------------------------------------------------------------ props
def text_block(lines, role, size, color, gap=1.35, max_w=None, wght=None):
    f = font(role, size, wght); asc, desc = f.getmetrics(); lh = int(size * gap)
    wrapped = []
    for ln in lines:
        if max_w is None: wrapped.append(ln); continue
        cur = ''
        for wd in ln.split(' '):
            tr = (cur + ' ' + wd).strip()
            if f.getlength(tr) > max_w and cur: wrapped.append(cur); cur = wd
            else: cur = tr
        wrapped.append(cur)
    wmax = max([int(f.getlength(l)) for l in wrapped] + [1])
    im = Image.new('RGBA', (wmax + 8, lh * len(wrapped) + desc + 8), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    boxes = []
    for i, l in enumerate(wrapped):
        y = 4 + i * lh
        d.text((4, y), l, font=f, fill=color)
        boxes.append((4, y + int(size * 0.12), 4 + int(f.getlength(l)), y + asc + int(size * 0.1)))
    return im, boxes, wrapped

def ink_bleed(im):
    """typewriter ink: slight blur + uneven density."""
    a = np.asarray(im).astype(np.float32)
    al = a[..., 3] * (0.78 + 0.22 * (noise(im.height, im.width, 3, 7) + 0.5))
    a[..., 3] = al
    return Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.45))

class Prop:
    """one physical object on the desk. Local marks (highlight / circle / underline / cross) live inside it."""
    def __init__(s, e, idx):
        s.e = e; s.idx = idx; s.type = e['type']
        s.x, s.y = float(e['x']), float(e['y']); s.rot = float(e.get('rot', 0)); s.scale = float(e.get('scale', 1))
        s.at = tref(e.get('at'), T0); s.until = tref(e.get('until'))
        s.enter = e.get('enter', {'stamp': 'stamp', 'sticky': 'slap'}.get(s.type, 'slap'))
        s.seed = 100 + idx * 17
        s.marks = [dict(m, at=tref(m['at'])) for m in e.get('marks', [])]
        s.bars = None
        s._base = None; s._cache = {}
        s.boxes = []

    # ---- base artwork (static), in local px at RES
    def base(s):
        if s._base is not None: return s._base
        e, R = s.e, RES; t = s.type
        if t in ('doc', 'clipping', 'sticky', 'strip', 'graph'):
            w = int(e.get('w', 640) * R)
            pad = int(46 * R)
            if t == 'doc':
                title = e.get('title')
                parts = []
                if title: parts.append(text_block([title], 'typebold', 40 * R, col('ink'), max_w=w - 2 * pad))
                body = text_block(e.get('lines', []), 'type', float(e.get('size', 34)) * R, col('ink'), gap=1.55, max_w=w - 2 * pad)
                parts.append(body)
                h = pad * 2 + sum(p[0].height for p in parts) + int(18 * R) * (len(parts) - 1)
                h = max(h, int(e.get('h', 0) * R))
                im = paper_tex(w, h, COL['paper'], s.seed)
                y = pad; boxes = []
                for k, (ti, bx, _) in enumerate(parts):
                    im.alpha_composite(ink_bleed(ti), (pad, y))
                    if k == len(parts) - 1: boxes = [(pad + a, y + b, pad + c, y + dd) for a, b, c, dd in bx]
                    y += ti.height + int(18 * R)
                if title: ImageDraw.Draw(im).line((pad, pad + parts[0][0].height + int(4 * R), w - pad, pad + parts[0][0].height + int(4 * R)), fill=col('ink', 120), width=max(1, int(2 * R)))
                s.boxes = boxes
            elif t == 'clipping':
                hl = text_block([e.get('headline', '')], 'serif', float(e.get('size', 64)) * R, col('ink'), gap=1.05, max_w=w - 2 * pad, wght=750)
                dek = text_block([e['dek']], 'serif', 30 * R, col('ink', 210), gap=1.3, max_w=w - 2 * pad, wght=400) if e.get('dek') else None
                kick = text_block([e['kicker']], 'cond', 24 * R, col('red'), max_w=w - 2 * pad) if e.get('kicker') else None
                h = pad * 2 + hl[0].height + (dek[0].height + int(16 * R) if dek else 0) + (kick[0].height + int(8 * R) if kick else 0)
                im = paper_tex(w, h, COL['news'], s.seed, edge_dark=0.04)
                y = pad
                if kick: im.alpha_composite(kick[0], (pad, y)); y += kick[0].height + int(8 * R)
                im.alpha_composite(hl[0], (pad, y)); s.boxes = [(pad + a, y + b, pad + c, y + dd) for a, b, c, dd in hl[1]]; y += hl[0].height + int(16 * R)
                if dek: im.alpha_composite(dek[0], (pad, y))
            elif t == 'sticky':
                tb = text_block(e.get('text', '').split('\n'), 'hand', float(e.get('size', 58)) * R, col(e.get('ink', 'ink')), gap=1.05, max_w=w - 2 * pad)
                h = max(w, tb[0].height + 2 * pad)
                im = paper_tex(w, h, COL[e.get('color', 'sticky')], s.seed, fibers=False, edge_dark=0.06)
                g = np.linspace(1, 0.9, h)[:, None]   # curl shading at the bottom
                a = np.asarray(im).astype(np.float32); a[..., :3] *= g[..., None]; im = Image.fromarray(a.astype(np.uint8))
                im.alpha_composite(tb[0], ((w - tb[0].width) // 2, (h - tb[0].height) // 2)); s.boxes = []
            elif t == 'strip':
                size = float(e.get('size', 110)) * R
                tb = text_block([e.get('text', '')], e.get('font', 'title'), size, col(e.get('ink', 'ink')), gap=1.08, max_w=int(e.get('w', 900) * R) - 2 * int(30 * R))
                w = tb[0].width + int(60 * R); h = tb[0].height + int(36 * R)
                im = paper_tex(w, h, COL[e.get('color', 'white')], s.seed, edge_dark=0.03)
                im.alpha_composite(tb[0], (int(30 * R), int(16 * R))); s.boxes = [(int(30 * R) + a, int(16 * R) + b, int(30 * R) + c, int(16 * R) + d) for a, b, c, d in tb[1]]
            elif t == 'graph':
                h = int(e.get('h', 900) * R)
                im = paper_tex(w, h, COL['graph'], s.seed, edge_dark=0.05)
                d = ImageDraw.Draw(im, 'RGBA'); gs = int(28 * R)
                for x in range(0, w, gs): d.line((x, 0, x, h), fill=col('grid', 70 if (x // gs) % 5 else 130), width=1)
                for y in range(0, h, gs): d.line((0, y, w, y), fill=col('grid', 70 if (y // gs) % 5 else 130), width=1)
                if e.get('title'):
                    tb = text_block([e['title']], 'hand', 70 * R, col('ink'), max_w=w - 2 * pad)
                    im.alpha_composite(tb[0], (pad, int(26 * R)))
                s.boxes = []
            torn = e.get('torn', {'clipping': ['top', 'bottom', 'left', 'right'], 'strip': ['left', 'right'], 'doc': ['bottom']}.get(t, []))
            if torn:
                m = torn_mask(im.width, im.height, torn, s.seed, amp=6 * R)
                im.putalpha(ImageChops.multiply(im.split()[3], m))
        elif t == 'stamp':
            size = float(e.get('size', 90)) * R
            tb = text_block([e.get('text', '')], 'title', size, col(e.get('color', 'red')), gap=1.0)
            w = tb[0].width + int(70 * R); h = tb[0].height + int(40 * R)
            im = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
            c = col(e.get('color', 'red'))
            for k, ins in enumerate((int(8 * R), int(18 * R))):
                d.rounded_rectangle((ins, ins, w - ins, h - ins), int(10 * R), outline=c, width=int((7 if k == 0 else 3) * R))
            im.alpha_composite(tb[0], ((w - tb[0].width) // 2, (h - tb[0].height) // 2 + int(4 * R)))
            a = np.asarray(im).astype(np.float32)
            holes = (noise(h, w, 4, s.seed) + 0.5) * 0.7 + (noise(h, w, 30, s.seed + 1) + 0.5) * 0.6
            a[..., 3] *= np.clip(holes * 1.25 - 0.1, 0, 1) * 0.92
            im = Image.fromarray(a.astype(np.uint8)); s.boxes = []
        elif t == 'photo':
            src = Image.open(e['path']).convert('RGB')
            tw = int(e.get('w', 620) * R)
            src = src.resize((tw, int(src.height * tw / src.width)), Image.LANCZOS)
            if e.get('crop_h'): ch = int(e['crop_h'] * R); top = max(0, (src.height - ch) // 2); src = src.crop((0, top, tw, top + ch))
            tr = e.get('treatment', 'bw')
            if tr in ('bw', 'duotone'):
                g = np.asarray(src.convert('L')).astype(np.float32) / 255
                g = np.clip((g - 0.5) * 1.15 + 0.5, 0, 1)
                if tr == 'duotone':
                    lo, hi = np.array(col(e.get('shadow', 'ink'))[:3], np.float32), np.array(col(e.get('light', 'paper'))[:3], np.float32)
                    a = lo * (1 - g[..., None]) + hi * g[..., None]
                else:
                    a = np.repeat(g[..., None] * 255, 3, 2)
                a += np.random.default_rng(s.seed).normal(0, 7, a.shape[:2])[..., None]
                src = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
            b = int(e.get('border', 22) * R)
            im = Image.new('RGBA', (src.width + 2 * b, src.height + 2 * b + int(e.get('chin', 0) * R)), col('white'))
            im = paper_tex(im.width, im.height, COL['white'], s.seed, fibers=False, edge_dark=0.03)
            im.paste(src, (b, b))
            if e.get('caption'):
                tb = text_block([e['caption']], 'hand', 50 * R, col('ink'), max_w=im.width - 2 * b)
                im.alpha_composite(tb[0], ((im.width - tb[0].width) // 2, src.height + b + int(4 * R)))
            s.boxes = []
        else:
            raise ValueError(f"unknown collage prop type {t!r}")
        # tape
        if e.get('tape', t in ('photo', 'doc', 'graph', 'clipping')):
            tape = Image.new('RGBA', (int(170 * R), int(54 * R)), (232, 226, 205, 150))
            tm = torn_mask(tape.width, tape.height, ['left', 'right'], s.seed + 9, amp=4 * R)
            tape.putalpha(ImageChops.multiply(tape.split()[3], tm))
            tape = tape.rotate(np.random.default_rng(s.seed).uniform(-8, 8), expand=True, resample=Image.BICUBIC)
            canvas = Image.new('RGBA', (im.width, im.height + tape.height // 2), (0, 0, 0, 0))
            canvas.alpha_composite(im, (0, tape.height // 2)); canvas.alpha_composite(tape, ((im.width - tape.width) // 2, 0))
            s.boxes = [(a, b + tape.height // 2, c, dd + tape.height // 2) for a, b, c, dd in s.boxes]; s.yoff = tape.height // 2
            im = canvas
        s._base = im
        return im

    # ---- dynamic layers: graph bars and local marks
    def bar_state(s, t):
        if s.type != 'graph' or not s.e.get('bars'): return ()
        return tuple(round(outq(prog(t, tref(b['at']), 0.9)), 2) for b in s.e['bars'])
    def mark_state(s, t):
        out = []
        for m in s.marks:
            p = prog(t, m['at'], float(m.get('dur', 0.6)))
            boil = int(t * 8) % 3 if 0 < p < 1 or m.get('boil', True) and p >= 1 and m['type'] != 'highlight' else 0
            out.append((round(p, 2), boil if p > 0 else 0))
        return tuple(out)

    def sprite(s, t):
        bs, ms = s.bar_state(t), s.mark_state(t)
        key = (bs, ms)
        if key in s._cache: return s._cache[key]
        if len(s._cache) > 40: s._cache.clear()
        im = s.base().copy(); R = RES
        if bs:
            d = ImageDraw.Draw(im, 'RGBA'); e = s.e
            w, h = im.width, im.height; yo = getattr(s, 'yoff', 0)
            x0, x1 = int(90 * R), w - int(60 * R); yb = h - int(130 * R); ytop = yo + int(200 * R)
            vmax = float(e.get('max', max(b['value'] for b in e['bars']) * 1.08))
            axis = wobble_path([(x0, ytop - 20 * R), (x0, yb), (x1, yb)], s.seed, amp=1.0 * R)
            draw_stroke(d, axis, 1, col('ink', 230), 4 * R)
            n = len(e['bars']); slot = (x1 - x0) / n
            for i, (b, p) in enumerate(zip(e['bars'], bs)):
                if p <= 0: continue
                cx = x0 + slot * (i + 0.5); bw = slot * 0.56; top = yb - (yb - ytop) * b['value'] / vmax * p
                c = col(b.get('color', 'blue'), 235)
                outline = wobble_path([(cx - bw / 2, yb), (cx - bw / 2, top), (cx + bw / 2, top), (cx + bw / 2, yb)], s.seed + i, amp=0.9 * R)
                draw_stroke(d, outline, 1, c, 4.5 * R)
                k = 0; step = 16 * R
                yy = yb - step
                while yy > top + 4:      # marker hatching
                    hp = wobble_path([(cx - bw / 2 + 4, yy + step * 0.5), (cx + bw / 2 - 4, yy - step * 0.25)], s.seed + i * 31 + k, amp=0.6 * R, step=8)
                    draw_stroke(d, hp, 1, c[:3] + (150,), 3.2 * R); yy -= step; k += 1
                if p > 0.95:
                    lab = text_block([b.get('label', '')], 'hand', float(e.get('label_size', 58)) * R, c, gap=1.0)[0]
                    im.alpha_composite(lab, (int(cx - lab.width / 2), int(top - lab.height - 4 * R)))
                    xl = text_block([b.get('x', '')], 'hand', 44 * R, col('ink', 220), gap=1.0)[0]
                    im.alpha_composite(xl, (int(cx - xl.width / 2), int(yb + 10 * R)))
            for ref in e.get('refs', []):          # dashed reference line (e.g. money invested)
                p = prog(t, tref(ref['at']), 0.8)
                if p <= 0: continue
                y = yb - (yb - ytop) * ref['value'] / vmax; xe = x0 + (x1 - x0) * outq(p)
                c = col(ref.get('color', 'red'), 230); xx = x0
                while xx < xe:
                    d.line((xx, y, min(xe, xx + 22 * R), y), fill=c, width=int(4 * R)); xx += 36 * R
                if p > 0.9 and ref.get('label'):
                    lab = text_block([ref['label']], 'hand', 52 * R, c, gap=1.0)[0]
                    im.alpha_composite(lab, (int(x0 + 14 * R), int(y - lab.height - 2 * R)))
            s._bar_geom = (x0, x1, yb, ytop, vmax, slot)
        if ms:
            layer = Image.new('RGBA', im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer, 'RGBA')
            for m, (p, boil) in zip(s.marks, ms):
                if p <= 0: continue
                if 'line' in m: bx = s.boxes[m['line']]
                elif 'bar' in m and hasattr(s, '_bar_geom'):
                    x0, x1, yb, ytop, vmax, slot = s._bar_geom; i = m['bar']; v = s.e['bars'][i]['value']
                    cx = x0 + slot * (i + 0.5); top = yb - (yb - ytop) * v / vmax
                    bx = (cx - slot * 0.45, top - 80 * R, cx + slot * 0.45, yb)
                else: bx = [v * R for v in m['box']]
                c = col(m.get('color', 'red'), 225); sd = s.seed + 7 * len(str(m)) + boil * 1000
                if m['type'] == 'highlight':
                    hl = Image.new('RGBA', im.size, (0, 0, 0, 0)); hd = ImageDraw.Draw(hl)
                    xe = bx[0] - 6 * R + (bx[2] - bx[0] + 12 * R) * outq(p)
                    hd.rectangle((bx[0] - 6 * R, bx[1] - 2 * R, xe, bx[3] + 4 * R), fill=col(m.get('color', 'hilite'), 140))
                    im = Image.composite(ImageChops.multiply(im, Image.merge('RGBA', (*Image.new('RGB', im.size, col(m.get('color', 'hilite'))[:3]).split(), im.split()[3]))), im, hl.split()[3])
                elif m['type'] == 'circle':
                    cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
                    pts = ellipse_pts(cx, cy, (bx[2] - bx[0]) / 2 + 26 * R, (bx[3] - bx[1]) / 2 + 22 * R, sd)
                    draw_stroke(d, wobble_path(pts, sd, amp=0.8 * R, step=5), outq(p), c, 6 * R)
                elif m['type'] == 'underline':
                    pts = wobble_path([(bx[0] - 4 * R, bx[3] + 10 * R), (bx[2] + 8 * R, bx[3] + 6 * R)], sd, amp=1.2 * R)
                    draw_stroke(d, pts, outq(p), c, 6 * R)
                    if m.get('double'): draw_stroke(d, wobble_path([(bx[0] + 10 * R, bx[3] + 24 * R), (bx[2], bx[3] + 20 * R)], sd + 5, amp=1.2 * R), outq(prog(p, 0.5, 0.5)), c, 5 * R)
                elif m['type'] == 'cross':
                    draw_stroke(d, wobble_path([(bx[0], bx[1]), (bx[2], bx[3])], sd, amp=1 * R), outq(min(1, p * 2)), c, 7 * R)
                    draw_stroke(d, wobble_path([(bx[2], bx[1]), (bx[0], bx[3])], sd + 3, amp=1 * R), outq(max(0, p * 2 - 1)), c, 7 * R)
            im.alpha_composite(layer)
        s._cache[key] = im
        return im

    def lift(s, t):
        """returns (alpha, scale_mult, lift 0..1, dx, dy) for the entrance."""
        out_a = 1 - prog(t, s.until, 0.35) if s.until is not None else 1
        if t < s.at: return 0, 1, 0, 0, 0
        if s.enter == 'slap':
            p = prog(t, s.at, 0.42); q = outq(p)
            return min(1, p * 5) * out_a, 1 + 0.10 * (1 - q), 1 - q, 0, -40 * (1 - q)
        if s.enter == 'stamp':
            p = prog(t, s.at, 0.18); q = p ** 2
            return min(1, p * 4) * out_a, 1 + 0.6 * (1 - q), 1 - q, 0, 0
        if s.enter == 'slide':
            p = outq(prog(t, s.at, 0.7)); return out_a, 1, 0.3 * (1 - p), 900 * (1 - p) * float(s.e.get('from_x', 1)), 0
        p = prog(t, s.at, 0.5); return p * out_a, 1, 0, 0, 0

# ------------------------------------------------------------------ world & camera
WORLD = SPEC.get('world', {}); WW, WH = int(WORLD.get('w', 2400)), int(WORLD.get('h', 3600))
PROPS = [Prop(e, i) for i, e in enumerate(SPEC.get('props', []))]
CAM = sorted([dict(c, at=tref(c['at'])) for c in SPEC['camera']], key=lambda c: c['at'])
ARROWS = [dict(a, at=tref(a['at']), until=tref(a.get('until'))) for a in SPEC.get('arrows', [])]

def camera(t):
    c = CAM[0]; x, y, z, r = c['x'], c['y'], c.get('zoom', 1), c.get('rot', 0)
    for a, b in zip(CAM[:-1], CAM[1:]):
        if t >= b['at']:
            f = inout(prog(t, b['at'], float(b.get('dur', 0.9))))
            x, y = a['x'] + (b['x'] - a['x']) * f, a['y'] + (b['y'] - a['y']) * f
            z = a.get('zoom', 1) * (b.get('zoom', 1) / a.get('zoom', 1)) ** f
            r = a.get('rot', 0) + (b.get('rot', 0) - a.get('rot', 0)) * f
    # slow push while holding + handheld drift
    z *= 1 + float(SPEC.get('push', 0.012)) * math.sin(min(1, (t - T0) / 600) * 0)  # (kept simple)
    hh = float(SPEC.get('handheld', 1.0))
    x += hh * (6 * math.sin(t * 0.7) + 3 * math.sin(t * 1.9 + 1)); y += hh * (5 * math.sin(t * 0.55 + 2) + 2.5 * math.sin(t * 2.3))
    r += hh * (0.25 * math.sin(t * 0.45 + 0.5))
    return x, y, z, r

def w2s(px, py, cam):
    x, y, z, r = cam; a = math.radians(-r)
    dx, dy = (px - x) * z, (py - y) * z
    return W / 2 + dx * math.cos(a) - dy * math.sin(a), H / 2 + dx * math.sin(a) + dy * math.cos(a)

DESK = None
PAD = 900   # desk extends beyond the world so the camera never sees an edge
def desk_img():
    global DESK
    if DESK is None:
        p = J('_desk.png')
        if os.path.exists(p): DESK = Image.open(p).convert('RGB')
        else: DESK = desk(WW + 2 * PAD, WH + 2 * PAD, WORLD.get('surface', 'walnut')); DESK.save(p)
    return DESK

def bg_frame(cam):
    x, y, z, r = cam; a = math.radians(r)
    # inverse map: screen -> world
    ca, sa = math.cos(a), math.sin(a)
    A = ca / z; B = -sa / z; Cc = x + PAD - (A * W / 2 + B * H / 2)
    D = sa / z; E = ca / z; F = y + PAD - (D * W / 2 + E * H / 2)
    return desk_img().transform((W, H), Image.AFFINE, (A, B, Cc, D, E, F), resample=Image.BILINEAR)

_vig = None
def vignette():
    global _vig
    if _vig is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        v = 1 - float(SPEC.get('vignette', 0.42)) * np.clip(((xx - W / 2) / (W * 0.72)) ** 2 + ((yy - H * 0.46) / (H * 0.62)) ** 2, 0, 1.3)
        warm = np.array(SPEC.get('grade', [1.04, 1.0, 0.93]), np.float32)
        _vig = (v[..., None] * warm).astype(np.float32)
    return _vig

_tx = {}
def place(frame, prop, t, cam):
    al, sm, lift, dx, dy = prop.lift(t)
    if al <= 0.01: return
    spr = prop.sprite(t)
    z = cam[2]; sc = prop.scale * z * sm / RES
    rot = prop.rot - cam[3]
    k = (id(spr), round(sc, 3), round(rot, 2))
    im = _tx.get(k)
    if im is None:
        im = spr.resize((max(1, int(spr.width * sc)), max(1, int(spr.height * sc))), Image.BILINEAR)
        if abs(rot) > 0.05: im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
        if len(_tx) > 300: _tx.clear()
        _tx[k] = im
    sx, sy = w2s(prop.x + dx, prop.y + dy, cam)
    # contact shadow: offset grows while lifted
    sk = ('sh', k)
    sh = _tx.get(sk)
    if sh is None:
        a = im.split()[3].filter(ImageFilter.GaussianBlur(max(2, 10 * z)))
        sh = Image.merge('RGBA', (Image.new('L', im.size, 0),) * 3 + (a.point(lambda v: int(v * 0.55)),)); _tx[sk] = sh
    off = (6 + 34 * lift) * z
    shp = sh if al >= 0.99 else _fade(sh, al)
    frame.alpha_composite(shp, (int(sx - im.width / 2 + off * 0.6), int(sy - im.height / 2 + off)))
    frame.alpha_composite(im if al >= 0.99 else _fade(im, al), (int(sx - im.width / 2), int(sy - im.height / 2)))

def _fade(im, a):
    im = im.copy(); im.putalpha(im.split()[3].point(lambda v: int(v * a))); return im

def draw_arrows(frame, t, cam):
    if not ARROWS: return
    d = ImageDraw.Draw(frame, 'RGBA')
    for k, a in enumerate(ARROWS):
        p = outq(prog(t, a['at'], float(a.get('dur', 0.6))))
        if p <= 0: continue
        if a['until'] is not None and t > a['until'] + 0.3: continue
        al = 1 - prog(t, a['until'], 0.3) if a['until'] is not None else 1
        boil = int(t * 8) % 3
        (x0, y0), (x1, y1) = w2s(*a['from'], cam), w2s(*a['to'], cam)
        pts = wobble_path(arrow_pts(x0, y0, x1, y1, float(a.get('bend', 0.18))), 900 + k + boil * 50, amp=1.2 * cam[2], step=7)
        c = col(a.get('color', 'red'), int(230 * al)); wd = 7 * cam[2]
        draw_stroke(d, pts, p, c, wd)
        if p >= 0.98:
            for seg in arrow_head(pts, 30 * cam[2]): draw_stroke(d, seg, 1, c, wd)

# ------------------------------------------------------------------ captions (clean documentary subtitles)
_cap = {}
CAP_Y = int(SPEC.get('caption_y', 1480))
def caption_img(i):
    if i in _cap: return _cap[i]
    sz = int(SPEC.get('caption_size', 48)); f = font('sans', sz, 620)
    txt = PHR[i]['text']; tw = int(f.getlength(txt))
    w_, h_ = tw + 56, int(sz * 1.75)
    strip = paper_tex(w_, h_, (24, 23, 22), 500 + i, fibers=False, edge_dark=0)
    strip.putalpha(torn_mask(w_, h_, ['left', 'right', 'top', 'bottom'], 600 + i, amp=4))
    ImageDraw.Draw(strip).text((28, int(sz * 0.28)), txt, font=f, fill=(246, 240, 226, 255))
    rot = float(np.random.default_rng(700 + i).uniform(-1.2, 1.2))
    strip = strip.rotate(rot, resample=Image.BICUBIC, expand=True)
    sh = Image.merge('RGBA', (Image.new('L', strip.size, 0),) * 3 + (strip.split()[3].filter(ImageFilter.GaussianBlur(6)).point(lambda v: int(v * 0.5)),))
    im = Image.new('RGBA', (strip.width + 16, strip.height + 16), (0, 0, 0, 0)); im.alpha_composite(sh, (8, 14)); im.alpha_composite(strip, (4, 4))
    _cap[i] = im
    return im
_cap = {}
CAPW = []
for i, o in enumerate(TIM):
    nxt = TIM[i + 1]['start'] if i + 1 < len(TIM) else o['end'] + 0.6
    CAPW.append((o['start'] - 0.04, nxt if nxt - o['end'] < 1.2 else o['end'] + 0.4))

def frame_at(t):
    cam = camera(t)
    fr = bg_frame(cam).convert('RGBA')
    for p in PROPS:
        if t >= p.at and (p.until is None or t < p.until + 0.4): place(fr, p, t, cam)
    draw_arrows(fr, t, cam)
    a = np.asarray(fr.convert('RGB')).astype(np.float32) * vignette()
    out = np.clip(a, 0, 255).astype(np.uint8)
    if SPEC.get('captions', True):
        for i, (a0, a1) in enumerate(CAPW):
            if a0 <= t < a1:
                im = caption_img(i); al = prog(t, a0, 0.1)
                x = (W - im.width) // 2; y = CAP_Y - im.height // 2
                arr = np.asarray(im).astype(np.float32); A = arr[..., 3:] / 255 * al
                reg = out[y:y + im.height, x:x + im.width].astype(np.float32)
                out[y:y + im.height, x:x + im.width] = (reg * (1 - A) + arr[..., :3] * A).astype(np.uint8)
                break
    return out

# ------------------------------------------------------------------ modes
def segments():
    per = SEG_SEC * FPS
    return [(i, i * per, min(NFR, (i + 1) * per)) for i in range((NFR + per - 1) // per)]

def run():
    os.makedirs(J('segs'), exist_ok=True); desk_img()
    lock = J('render.lock'); open(lock, 'w').write(str(os.getpid())); t_start = time.time(); done_fr = 0
    try:
        for i, f0, f1 in segments():
            outp = J(f'segs/seg_{i:04d}.mp4')
            if os.path.exists(outp): continue
            tmp = outp + '.part.mp4'
            enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                                    '-c:v', 'libx264', '-preset', 'superfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-g', '60', tmp], stdin=subprocess.PIPE)
            for k in range(f0, f1): enc.stdin.write(frame_at(T0 + k / FPS).tobytes())
            enc.stdin.close(); enc.wait(); os.replace(tmp, outp)
            done_fr += f1 - f0; fps = done_fr / (time.time() - t_start)
            rem = sum(b - a for j, a, b in segments() if not os.path.exists(J(f'segs/seg_{j:04d}.mp4')))
            pr = dict(done=len(glob.glob(J('segs/seg_*[0-9].mp4'))), total=len(segments()), fps=round(fps, 1), eta_s=int(rem / max(fps, 0.1)))
            json.dump(pr, open(J('progress.json'), 'w')); print('progress', pr, flush=True)
    finally:
        if os.path.exists(lock): os.remove(lock)
    print('RENDER COMPLETE', flush=True)

def sfx():
    SR = 48000; n = int(NFR / FPS * SR); out = np.zeros(n); r = np.random.default_rng(3)
    def add(sig, t, g):
        i = int((t - T0) * SR)
        if 0 <= i < n: j = min(n, i + len(sig)); out[i:j] += sig[:j - i] * g
    def band(x, lo, hi):
        X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR); X[(f < lo) | (f > hi)] = 0; return np.fft.irfft(X, len(x))
    tt = np.arange(int(0.16 * SR)) / SR
    slap = band(r.standard_normal(len(tt)), 300, 5000) * np.exp(-tt * 38); slap /= np.abs(slap).max()
    th = np.arange(int(0.3 * SR)) / SR
    thud = np.sin(2 * np.pi * (70 * th - 40 * th * th)) * np.exp(-th * 16) + band(r.standard_normal(len(th)), 200, 2000) * np.exp(-th * 60) * 0.5
    tm = np.arange(int(0.6 * SR)) / SR
    scratch = band(r.standard_normal(len(tm)), 2500, 9000) * (0.6 + 0.4 * np.sin(2 * np.pi * 7 * tm) ** 2); scratch /= np.abs(scratch).max()
    tw = np.arange(int(0.7 * SR)) / SR
    swoosh = band(r.standard_normal(len(tw)), 150, 1200) * np.sin(np.pi * tw / 0.7) ** 2; swoosh /= np.abs(swoosh).max()
    for p in PROPS:
        if p.enter == 'stamp': add(thud, p.at + 0.17, 0.55); add(slap, p.at + 0.17, 0.25)
        elif p.enter in ('slap', 'slide'): add(slap, p.at + (0.3 if p.enter == 'slap' else 0.5), 0.32); add(thud, p.at + 0.3, 0.12)
        for m in p.marks:
            if m['type'] != 'highlight': add(scratch[:int(SR * float(m.get('dur', 0.6)))], m['at'], 0.05)
            else: add(scratch[:int(SR * 0.5)], m['at'], 0.035)
    for a in ARROWS: add(scratch, a['at'], 0.05)
    for c in CAM[1:]:
        if float(c.get('dur', 0.9)) <= 1.4: add(swoosh, c['at'], 0.10)
    return np.clip(out, -1, 1)

def finish(outp):
    miss = [i for i, _, _ in segments() if not os.path.exists(J(f'segs/seg_{i:04d}.mp4'))]
    if miss: sys.exit(f'missing segments {miss}')
    with open(J('segs/list.txt'), 'w') as f:
        for i, _, _ in segments(): f.write(f"file 'seg_{i:04d}.mp4'\n")
    dur = NFR / FPS; SR = 48000
    s = sfx()
    with wave.open(J('_sfx.wav'), 'wb') as w_:
        w_.setnchannels(1); w_.setsampwidth(2); w_.setframerate(SR); w_.writeframes((s * 32767).astype(np.int16).tobytes())
    ins = ['-ss', f'{T0:.3f}', '-t', f'{dur:.3f}', '-i', info['video'], '-i', J('_sfx.wav')]
    voice = (f"[0:a]highpass=f=70,acompressor=threshold=-20dB:ratio=2.5:attack=5:release=150,loudnorm=I=-15:TP=-1.5:LRA=8,"
             f"afade=t=in:d=0.08,afade=t=out:st={max(0, dur - 0.5):.2f}:d=0.5,aresample={SR},asplit=2[v][vk];[1:a]aresample={SR}[s];")
    if SPEC.get('music'):
        ins += ['-stream_loop', '-1', '-i', SPEC['music']]
        fc = voice + (f"[2:a]aresample={SR},volume={SPEC.get('music_gain', 0.22)},afade=t=out:st={max(0, dur - 1.5):.2f}:d=1.5[m0];"
                      f"[m0][vk]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[m];"
                      f"[v][s][m]amix=inputs=3:weights=1 0.9 1:normalize=0,alimiter=limit=0.93[a]")
    else:
        fc = voice + "[vk]anullsink;[v][s]amix=inputs=2:weights=1 0.9:normalize=0,alimiter=limit=0.93[a]"
    subprocess.run(['ffmpeg', '-v', 'error', '-y'] + ins + ['-filter_complex', fc, '-map', '[a]', '-t', f'{dur:.3f}', '-ac', '2', J('_audio.wav')], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', J('segs/list.txt'), '-i', J('_audio.wav'), '-map', '0:v', '-map', '1:a',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', str(SPEC.get('crf', 24)), '-tune', 'film', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', outp], check=True)   # textured desk + camera motion: re-encode keeps files ~15-25 MB/30 s
    print('FINAL', outp, f'{dur:.1f}s', f'{os.path.getsize(outp) / 1e6:.1f} MB')

def check():
    print(f'COLLAGE  trim {T0:.2f}-{T1:.2f}s  world {WW}x{WH}  {len(PROPS)} props  {len(CAM)} camera keys  {len(ARROWS)} arrows')
    for p in PROPS:
        b = p.base()
        print(f'  {p.type:9s} at {p.at:6.2f}  pos ({p.x:.0f},{p.y:.0f})  size {b.width / RES:.0f}x{b.height / RES:.0f}  marks {len(p.marks)}')
    for c in CAM: print(f'  cam {c["at"]:6.2f}  ({c["x"]},{c["y"]}) zoom {c.get("zoom", 1)}')
    print('OK')

def preview(ts):
    ims = [Image.fromarray(frame_at(t)).resize((360, 640)) for t in ts]
    cols = min(4, len(ims)); rows = (len(ims) + cols - 1) // cols
    sh = Image.new('RGB', (360 * cols, 640 * rows))
    for k, im in enumerate(ims): sh.paste(im, ((k % cols) * 360, (k // cols) * 640))
    sh.save(J('preview_sheet.jpg'), quality=85); print('preview ->', J('preview_sheet.jpg'))

if __name__ == '__main__':
    mode = sys.argv[2] if len(sys.argv) > 2 else '--check'
    if mode == '--check': check()
    elif mode == '--preview': preview([float(x) for x in sys.argv[3:]])
    elif mode == '--run': run()
    elif mode == '--finish': finish(sys.argv[3])
