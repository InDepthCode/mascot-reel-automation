#!/usr/bin/env python3
"""render.py WORKDIR MODE
MODES
  --check                 validate spec.json and print the scene timeline
  --preview T [T ...]     render stills at source times -> WORKDIR/preview_sheet.jpg
  --run                   render all pending segments (resumable; safe to re-run). Progress -> WORKDIR/progress.json
  --finish OUT.mp4        build audio (cleanup + loudness + auto SFX) and mux the final reel

Layout: 1080x1920 @30fps. Top 880px = motion graphics from spec.json; bottom 1040px = the
uncropped source video as a rounded card over a blurred fill (done in ffmpeg = fast).
Needs WORKDIR/probe.json, phrases.json, timing.json, spec.json.
"""
import json, math, os, re, subprocess, sys, time, glob
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, TOPH, FPS = 1080, 1920, 880, 30
PANEL_H = H - TOPH
SEG_SEC = 15
SS = 2  # sprite supersampling
WORK = sys.argv[1]
try:   # documentary-collage style has its own engine
    if json.load(open(os.path.join(WORK, 'spec.json'))).get('style') == 'collage':
        os.execv(sys.executable, [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'collage.py')] + sys.argv[1:])
except FileNotFoundError:
    pass
J = lambda n: os.path.join(WORK, n)

# ------------------------------------------------------------------ fonts
def first(*paths):
    for p in paths:
        if os.path.exists(p): return p
    return None
FONT_BOLD = first('/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
FONT_MED = first('/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
FONT_SYM = first('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
FONT_EMOJI = first('/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf')
_fc = {}
FDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts')
AXK = {'Weight': 'wght', 'Optical Size': 'opsz', 'Optical size': 'opsz', 'Width': 'wdth', 'Softness': 'SOFT', 'Wonky': 'WONK'}
def fpath_of(spec):
    return os.path.join(FDIR, spec[0] + '.ttf') if isinstance(spec, tuple) else spec
def font(spec, size):
    """spec = a .ttf path, or ('Fraunces', {'wght': 600, 'opsz': 'auto'}) for bundled variable fonts."""
    k = (spec if not isinstance(spec, tuple) else (spec[0], tuple(sorted(spec[1].items()))), int(size))
    if k in _fc: return _fc[k]
    f = ImageFont.truetype(fpath_of(spec), int(size))
    if isinstance(spec, tuple):
        try:
            vals = []
            for a in f.get_variation_axes():
                nm = a['name'].decode() if isinstance(a['name'], bytes) else a['name']
                v = spec[1].get(AXK.get(nm, nm), a.get('default', a['minimum']))
                if v == 'auto': v = size / SS
                vals.append(max(a['minimum'], min(a['maximum'], v)))
            f.set_variation_by_axes(vals)
        except Exception as e:
            print('font axes warning', spec, e)
    _fc[k] = f
    return f
_cm = {}
def cmap_of(spec):
    p = fpath_of(spec)
    if p not in _cm:
        try:
            from fontTools.ttLib import TTFont
            _cm[p] = set(TTFont(p).getBestCmap())
        except Exception:
            _cm[p] = None
    return _cm[p]

def is_emoji(ch):
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF or o in (0x203C, 0x2049, 0x2122, 0x2139, 0x231A, 0x231B, 0x23F0, 0x23F3, 0x24C2)
def is_sym(ch, spec=None):
    """characters the main font can't draw -> DejaVu fallback (arrows, maths, etc.)"""
    if is_emoji(ch) or ch == ' ': return False
    cm = cmap_of(spec or FONT_BOLD)
    if cm is not None: return ord(ch) not in cm
    o = ord(ch)
    return o > 0x24F and not (0x2000 <= o <= 0x206F)

# ------------------------------------------------------------------ colours / theme
COL = dict(paper=(238, 228, 205), ink=(35, 30, 28), blood=(190, 20, 30), white=(245, 247, 255), muted=(150, 160, 195), yellow=(255, 210, 63), cyan=(79, 209, 255), red=(255, 77, 77),
           green=(60, 220, 140), orange=(255, 150, 50), purple=(170, 120, 255), pink=(255, 105, 180), blue=(90, 120, 200),
           redis=(220, 56, 45), dark=(12, 16, 32), black=(0, 0, 0), gray=(110, 115, 135))
THEMES = dict(navy=((9, 13, 28), (20, 28, 58), (20, 30, 70)), black=((6, 6, 8), (22, 22, 28), (30, 30, 40)),
              purple=((16, 8, 30), (40, 18, 70), (60, 30, 90)), green=((5, 18, 14), (12, 40, 30), (20, 60, 40)),
              mystery=((6, 5, 6), (14, 10, 12), (55, 8, 12)))
def col(c, alpha=255):
    if c is None: return None
    if isinstance(c, (list, tuple)): return tuple(c[:3]) + ((c[3],) if len(c) > 3 else (alpha,))
    c = str(c)
    if c.startswith('#'):
        h = c[1:]
        v = tuple(int(h[i:i + 2], 16) for i in range(0, len(h), 2))
        return v[:3] + ((v[3],) if len(v) > 3 else (alpha,))
    m = re.match(r'^(\w+)/(\d+)$', c)  # "white/40" = white at 40% opacity
    if m: return COL[m.group(1)] + (int(255 * int(m.group(2)) / 100),)
    return COL[c] + (alpha,)

# ------------------------------------------------------------------ easing
clamp = lambda x, a=0.0, b=1.0: max(a, min(b, x))
prog = lambda t, t0, d: clamp((t - t0) / d) if d > 0 else (1.0 if t >= t0 else 0.0)
ease = lambda x: 1 - (1 - x) ** 3
expo = lambda x: 1.0 if x >= 1 else (0.0 if x <= 0 else 1 - 2 ** (-10 * x))
inout = lambda x: 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2
OFFY = [0.0]
def back(x):
    if x <= 0: return 0.0
    return 1 + 2.9 * (x - 1) ** 3 + 1.9 * (x - 1) ** 2

# ------------------------------------------------------------------ text sprites (mixed fonts + inline emoji)
_ec = {}
def emoji_sprite(e, size):
    k = (e, int(size))
    if k in _ec: return _ec[k]
    if not FONT_EMOJI: return Image.new('RGBA', (1, 1))
    im = Image.new('RGBA', (220, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), e, font=font(FONT_EMOJI, 109), embedded_color=True)
    bb = im.getbbox()
    im = im.crop(bb) if bb else Image.new('RGBA', (1, 1))
    r = size / max(im.size)
    im = im.resize((max(1, round(im.width * r)), max(1, round(im.height * r))), Image.LANCZOS)
    _ec[k] = im
    return im

def runs(s, spec=None):
    out = []
    for ch in s:
        k = 'e' if is_emoji(ch) or ch in '\ufe0f\u200d' else ('s' if is_sym(ch, spec) else 'm')
        if ch in '\ufe0f\u200d' and out: out[-1][1] += ch; continue
        if out and out[-1][0] == k and k != 'e': out[-1][1] += ch
        else: out.append([k, ch])
    return out

def word_img(s, size, color, fpath):
    """one word/run group at scale; returns RGBA with baseline-aligned height."""
    f = font(fpath, size)
    asc, desc = f.getmetrics()
    pieces = []
    for k, chunk in runs(s, fpath):
        if k == 'e':
            pieces.append(emoji_sprite(chunk, size * 0.95)); continue
        ff = font(FONT_SYM, size) if k == 's' and FONT_SYM else f
        w_ = max(1, int(ff.getlength(chunk)) + 2)
        im = Image.new('RGBA', (w_, asc + desc), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((0, 0), chunk, font=ff, fill=color)
        pieces.append(im)
    hgt = asc + desc
    wsum = sum(p.width for p in pieces)
    out = Image.new('RGBA', (max(1, wsum), hgt), (0, 0, 0, 0))
    x = 0
    for p in pieces:
        out.alpha_composite(p, (x, max(0, (hgt - p.height) // 2 + (int(size * 0.06) if p.height < hgt else 0))))
        x += p.width
    return out

def rich_sprite(parts, size, fpath=None, line_gap=1.15, max_w=None, align='center'):
    """parts: [(text, rgba)]. Words wrap at max_w. Drawn at SS then downscaled."""
    fpath = fpath or FONT_BOLD
    S = SS; sz = size * S
    words = []
    for txt, c in parts:
        for wd in str(txt).split(' '):
            if wd: words.append(word_img(wd, sz, c, fpath))
    if not words: return Image.new('RGBA', (1, 1))
    sp = int(sz * 0.27)
    lines, cur, cw = [], [], 0
    for wi in words:
        if cur and max_w and cw + sp + wi.width > max_w * S:
            lines.append(cur); cur, cw = [], 0
        cw += (sp if cur else 0) + wi.width; cur.append(wi)
    lines.append(cur)
    lh = int(max(w.height for w in words) * line_gap)
    lw = [sum(w.width for w in l) + sp * (len(l) - 1) for l in lines]
    im = Image.new('RGBA', (max(lw) + 4, lh * len(lines) + 4), (0, 0, 0, 0))
    y = 2; boxes = []
    for l, wl in zip(lines, lw):
        x = 2 if align == 'left' else (im.width - wl) // 2
        boxes.append((x // S, y // S, (x + wl) // S, (y + lh) // S))
        for w in l:
            im.alpha_composite(w, (x, y)); x += w.width + sp
        y += lh
    out = im.resize((max(1, im.width // S), max(1, im.height // S)), Image.LANCZOS)
    out.lines = boxes
    return out

def parts_of(e, default='white'):
    if 'parts' in e: return [(p[0], col(p[1] if len(p) > 1 else default)) for p in e['parts']]
    return [(e.get('text', ''), col(e.get('color', default)))]

# ------------------------------------------------------------------ load inputs
def load():
    info = json.load(open(J('probe.json')))
    P = json.load(open(J('phrases.json')))
    TIM = json.load(open(J('timing.json')))
    spec = json.load(open(J('spec.json')))
    return info, P, TIM, spec

info, PHR, TIM, SPEC = load()
AUDIO_ONLY = not info.get('has_video', True)
PRO = SPEC.get('style', 'classic') == 'pro'
if PRO:
    _fn = SPEC.get('fonts', {})
    FONT_DISPLAY = (_fn.get('display', 'Fraunces'), {'wght': _fn.get('display_weight', 560), 'opsz': 'auto', 'SOFT': 60, 'WONK': 0})
    FONT_BOLD = (_fn.get('text', 'BricolageGrotesque'), {'wght': _fn.get('text_weight', 600), 'opsz': 'auto', 'wdth': 92})
    FONT_MED = (_fn.get('text', 'BricolageGrotesque'), {'wght': 450, 'opsz': 'auto', 'wdth': 92})
else:
    FONT_DISPLAY = FONT_BOLD
_PAL = dict(bg='#0F2A22', bg2='#163A2F', ink='#EFE6D2', muted='#7E9A8C', dim='#48655A', accent='#D9A441', accent2='#7FA08C')
if PRO: _PAL.update(SPEC.get('palette', {}))
for _k, _v in _PAL.items():
    COL[_k] = tuple(int(_v.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
if AUDIO_ONLY:            # whole 1080x1920 canvas is the graphics panel
    TOPH, PANEL_H = H, 0
lead = float(SPEC.get('lead_in', 0.3)); tail = float(SPEC.get('tail', 0.6))
T0 = float(SPEC['trim'][0]) if 'trim' in SPEC else max(0.0, info['speech_start'] - lead)
T1 = float(SPEC['trim'][1]) if 'trim' in SPEC else min(info['duration'], info['speech_end'] + tail)
NFR = max(1, int(round((T1 - T0) * FPS)))
BG1, BG2, GLOW = THEMES.get(SPEC.get('theme', 'navy'), THEMES['navy'])
HL = col(SPEC.get('caption_highlight', 'yellow'))

def tref(v, default=None):
    if v is None: return default
    if isinstance(v, (int, float)): return float(v)
    m = re.match(r'^\s*(p(\d+)(\.end)?|start|end)\s*([+-]\s*[\d.]+)?\s*$', str(v))
    if not m: raise ValueError(f'bad time ref {v!r} (use p12, p12.end, p12+0.3, start, end-2, or seconds)')
    if m.group(1) == 'start': base = T0
    elif m.group(1) == 'end': base = T1
    else:
        i = int(m.group(2))
        if i >= len(TIM): raise ValueError(f'{v!r}: only p0..p{len(TIM) - 1} exist')
        base = TIM[i]['end'] if m.group(3) else TIM[i]['start']
    return base + (float(m.group(4).replace(' ', '')) if m.group(4) else 0.0)

# ------------------------------------------------------------------ transform cache
_tx = {}
def tx(sprite, sid, scale, alpha):
    sq, aq = round(scale, 2), round(alpha, 2)
    k = (sid, sq, aq)
    r = _tx.get(k)
    if r is not None: return r
    im = sprite
    if abs(sq - 1) > 0.005:
        im = im.resize((max(1, int(im.width * sq)), max(1, int(im.height * sq))), Image.BILINEAR)
    if aq < 0.995:
        im = im.copy(); a = np.asarray(im)[..., 3] * aq
        im.putalpha(Image.fromarray(a.astype(np.uint8)))
    if len(_tx) > 4000: _tx.clear()
    _tx[k] = im
    return im

def put(canvas, sprite, sid, cx, cy, scale=1.0, alpha=1.0, anchor='center'):
    if scale <= 0.02 or alpha <= 0.02: return
    im = tx(sprite, sid, scale, alpha)
    x = cx - im.width / 2 if anchor == 'center' else cx
    _safe(canvas, im, int(x), int(cy - im.height / 2 + OFFY[0]))

def _safe(canvas, im, x, y):
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(canvas.width, x + im.width), min(canvas.height, y + im.height)
    if x1 <= x0 or y1 <= y0: return
    if x0 != x or y0 != y or x1 != x + im.width or y1 != y + im.height: im = im.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    if canvas.mode == 'RGB': canvas.paste(im, (x0, y0), im)
    else: canvas.alpha_composite(im, (x0, y0))

# ------------------------------------------------------------------ elements
class El:
    pop_from = 0.0
    def __init__(s, e, scene_start):
        s.e = e; s.type = e['type']
        s.at = tref(e.get('at'), scene_start)
        s.until = tref(e.get('until'))
        s.x, s.y = float(e.get('x', 540)), float(e.get('y', 440))
        s.anim = e.get('anim', 'pop')
        s.anchor = e.get('anchor', 'center')
        s.states = sorted([dict(st, at=tref(st['at'])) for st in e.get('states', [])], key=lambda d: d['at'])
        s.sprites = {}
    def props(s, t):
        p = dict(s.e); idx = -1
        for k, st in enumerate(s.states):
            if t >= st['at']: p.update({kk: vv for kk, vv in st.items() if kk != 'at'}); idx = k
        return p, idx
    def visible(s, t): return t >= s.at and (s.until is None or t < s.until + 0.2)
    def enter(s, t):
        """returns (scale, alpha, dy, animating)"""
        out_a = 1.0 - prog(t, s.until, 0.2) if s.until is not None else 1.0
        if s.anim == 'none': return 1, out_a, 0, (s.until is not None and t >= s.until)
        if PRO and s.anim in ('pop', 'rise'):
            p = expo(prog(t, s.at, 0.8)); return 1, min(1, p * 1.4) * out_a, 34 * (1 - p), p < 0.999 or out_a < 1
        if s.anim == 'fade':
            p = prog(t, s.at, 0.3); return 1, p * out_a, 0, p < 1 or out_a < 1
        if s.anim == 'slide':
            p = ease(prog(t, s.at, 0.3)); return 1, p * out_a, 30 * (1 - p), p < 1 or out_a < 1
        p = prog(t, s.at, 0.35)
        return s.pop_from + (1 - s.pop_from) * back(p), min(1, p * 4) * out_a, 0, p < 1 or out_a < 1
    def shake(s, t):
        for st in s.states:
            if st.get('shake') and st['at'] <= t < st['at'] + 0.6:
                return 7 * math.sin(t * 60) * (1 - (t - st['at']) / 0.6)
        return 0
    def sprite(s, p, idx):
        k = idx
        if k not in s.sprites: s.sprites[k] = s.make(p)
        return s.sprites[k], (id(s), k)
    def key(s, t, sa):
        sc, a, dy, anim = s.enter(t)
        p, idx = s.props(t)
        dyn = s.dynamic(t, p)
        sh = s.shake(t)
        return (idx, round(sc, 2), round(a * sa, 2), round(dy), round(sh), dyn)
    def dynamic(s, t, p): return None
    def draw(s, cv, t, sa):
        sc, a, dy, _ = s.enter(t)
        p, idx = s.props(t)
        spr, sid = s.sprite(p, idx)
        put(cv, spr, sid, s.x + s.shake(t), s.y + dy, sc, a * sa, s.anchor)

class Text(El):
    pop_from = 0.6
    def tdur(s):
        n = sum(len(str(x[0])) for x in s.e.get('parts', [[s.e.get('text', '')]]))
        return float(s.e.get('type_dur', min(2.5, 0.045 * n)))
    def enter(s, t):
        if s.anim != 'type': return El.enter(s, t)
        out_a = 1.0 - prog(t, s.until, 0.2) if s.until is not None else 1.0
        return 1, out_a, 0, t < s.at + s.tdur() + 0.8 or out_a < 1
    def dynamic(s, t, p):
        if s.anim != 'type': return None
        q = prog(t, s.at, s.tdur())
        return (round(q, 2), q < 1 or int((t - s.at) * 2.5) % 2 == 0) if t < s.at + s.tdur() + 0.8 else 'done'
    def draw(s, cv, t, sa):
        if s.anim != 'type': return El.draw(s, cv, t, sa)
        _, a, _, _ = s.enter(t)
        p, idx = s.props(t)
        spr, sid = s.sprite(p, idx)
        q = round(prog(t, s.at, s.tdur()), 2)
        cursor = t < s.at + s.tdur() + 0.8 and (q < 1 or int((t - s.at) * 2.5) % 2 == 0)
        k = ('type', idx, q, cursor)
        if k not in s.sprites:
            boxes = getattr(spr, 'lines', [(0, 0, spr.width, spr.height)])
            total = sum(b[2] - b[0] for b in boxes); rem = total * q
            m = np.zeros((spr.height, spr.width), np.float32); cur_xy = None
            for (x0, y0, x1, y1) in boxes:
                wv = min(x1 - x0, rem); rem -= wv
                if wv > 0: m[y0:y1, x0:int(x0 + wv)] = 1; cur_xy = (int(x0 + wv), y0, y1)
                if rem <= 0: break
            im = spr.copy(); al = np.asarray(im)[..., 3] * m
            im.putalpha(Image.fromarray(al.astype(np.uint8)))
            if cursor:
                cx, y0, y1 = cur_xy or (boxes[0][0], boxes[0][1], boxes[0][3])
                ImageDraw.Draw(im).rectangle((cx + 2, y0 + (y1 - y0) * 0.18, cx + 6, y1 - (y1 - y0) * 0.12), fill=col(p.get('cursor', 'white')))
            s.sprites[k] = im
        put(cv, s.sprites[k], (id(s), k), s.x, s.y, 1, a * sa, s.anchor)
    def make(s, p):
        fp = FONT_DISPLAY if p.get('font') == 'display' else (FONT_MED if p.get('weight') == 'medium' else FONT_BOLD)
        return rich_sprite(parts_of(p), float(p.get('size', 64)), fp,
                           max_w=p.get('max_w', 980), align='left' if s.anchor == 'left' else 'center')

class Emoji(El):
    def make(s, p): return emoji_sprite(p['e'], float(p.get('size', 90)))
    def dynamic(s, t, p):
        if p.get('bob'): return round(10 * math.sin((t - s.at) * 5))
        if p.get('float'): return round(((t - s.at) * 0.8) % 1, 2)
        return None
    def draw(s, cv, t, sa):
        sc, a, dy, _ = s.enter(t)
        p, idx = s.props(t)
        spr, sid = s.sprite(p, idx)
        if p.get('bob'): dy += 10 * math.sin((t - s.at) * 5)
        if p.get('float'):
            f = ((t - s.at) * 0.8) % 1; dy -= f * 90; a *= 1 - 0.6 * f
        put(cv, spr, sid, s.x + s.shake(t), s.y + dy, sc, a * sa)

class Pill(El):
    pop_from = 0.6
    def make(s, p):
        size = float(p.get('size', 30))
        t_ = rich_sprite([(p.get('label', ''), col(p.get('fg', 'white')))], size, max_w=2000)
        pw, ph = t_.width + int(size * 0.9), int(size * 1.6)
        im = Image.new('RGBA', (pw * SS, ph * SS), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle((0, 0, pw * SS - 1, ph * SS - 1), ph * SS // 2, fill=col(p.get('bg', 'white/15')),
                                             outline=col(p['outline']) if p.get('outline') else None, width=2 * SS)
        im = im.resize((pw, ph), Image.LANCZOS)
        im.alpha_composite(t_, ((pw - t_.width) // 2, (ph - t_.height) // 2))
        return im
    def dynamic(s, t, p): return round(math.sin((t - s.at) * 9), 1) if p.get('pulse') else None
    def draw(s, cv, t, sa):
        sc, a, dy, _ = s.enter(t)
        p, idx = s.props(t)
        if p.get('pulse'): sc *= 1 + 0.05 * math.sin((t - s.at) * 9)
        spr, sid = s.sprite(p, idx)
        put(cv, spr, sid, s.x + s.shake(t), s.y + dy, sc, a * sa)

class DB(El):
    def make(s, p):
        w, h = float(p.get('w', 160)) * SS, float(p.get('h', 190)) * SS
        c = col(p.get('color', 'blue'))[:3]
        im = Image.new('RGBA', (int(w) + 4, int(h) + 4), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        eh = w * 0.28; x0, x1, top, bot = 2, w + 2, 2, h + 2
        dark = tuple(int(v * 0.6) for v in c); light = tuple(min(255, int(v * 1.25)) for v in c)
        d.rectangle((x0, top + eh / 2, x1, bot - eh / 2), fill=c)
        d.ellipse((x0, bot - eh, x1, bot), fill=c)
        for k in (1, 2):
            yy = top + (bot - top) * k / 3
            d.arc((x0, yy - eh, x1, yy), 0, 180, fill=dark, width=int(4 * SS))
        d.ellipse((x0, top, x1, top + eh), fill=light)
        im = im.resize((im.width // SS, im.height // SS), Image.LANCZOS)
        if p.get('emoji'):
            em = emoji_sprite(p['emoji'], min(im.width, im.height) * 0.5)
            im.alpha_composite(em, ((im.width - em.width) // 2, (im.height - em.height) // 2 + int(im.height * 0.06)))
        if p.get('label'):
            lab = rich_sprite([(p['label'], col('white'))], 24)
            out = Image.new('RGBA', (max(im.width, lab.width), im.height + lab.height + 8), (0, 0, 0, 0))
            out.alpha_composite(im, ((out.width - im.width) // 2, 0)); out.alpha_composite(lab, ((out.width - lab.width) // 2, im.height + 8))
            return out
        return im

class Box(El):
    def make(s, p):
        w, h = int(p.get('w', 340)), int(p.get('h', 125))
        im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), int(p.get('radius', 24)) * SS, fill=col(p.get('color', 'white/10')),
                            outline=col(p['outline']) if p.get('outline') else None, width=3 * SS)
        im = im.resize((w, h), Image.LANCZOS)
        x = 22
        if p.get('emoji'):
            em = emoji_sprite(p['emoji'], h * 0.42); im.alpha_composite(em, (x, (h - em.height) // 2)); x += em.width + 16
        tl = rich_sprite([(p.get('title', ''), col(p.get('fg', 'white')))], float(p.get('size', 42)), max_w=w - x - 10, align='left')
        if p.get('sub'):
            sb = rich_sprite([(p['sub'], col(p.get('sub_color', 'white/75')))], float(p.get('sub_size', 20)), FONT_MED, max_w=w - x - 10, align='left')
            y0 = (h - tl.height - sb.height + 4) // 2
            im.alpha_composite(tl, (x, y0)); im.alpha_composite(sb, (x, y0 + tl.height - 4))
        else:
            im.alpha_composite(tl, (x if p.get('emoji') else (w - tl.width) // 2, (h - tl.height) // 2))
        return im

class Card(El):
    def make(s, p):
        w, h = int(p.get('w', 880)), int(p.get('h', 170))
        c = p.get('color', 'cyan')
        im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), 30 * SS, fill=col('white/7'), outline=col(c, 200), width=3 * SS)
        im = im.resize((w, h), Image.LANCZOS)
        x = 36
        if p.get('emoji'):
            em = emoji_sprite(p['emoji'], h * 0.46); im.alpha_composite(em, (x, (h - em.height) // 2)); x += em.width + 26
        size = float(p.get('size', 50))
        parts = [(p.get('key', ''), col('white'))]
        if p.get('value') and p.get('_show_value', True):
            parts += [('→', col('muted')), (p['value'], col(c))]
        ts = rich_sprite(parts, size, max_w=w - x - 20, align='left')
        im.alpha_composite(ts, (x, (h - ts.height) // 2))
        return im
    def props(s, t):
        p, idx = El.props(s, t)
        va = tref(s.e.get('value_at'), s.at)
        show = t >= va
        p['_show_value'] = show
        return p, (idx, show)

class Image_(El):
    def make(s, p):
        im = Image.open(p['path']).convert('RGBA')
        w, h = p.get('w'), p.get('h')
        r = (float(w) / im.width) if w else (float(h) / im.height if h else min(900 / im.width, 560 / im.height))
        im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)
        rad = int(p.get('radius', 24))
        m = Image.new('L', im.size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), rad, fill=255)
        im.putalpha(Image.fromarray(np.minimum(np.asarray(im)[..., 3], np.asarray(m))))
        return im

class Counter(El):
    pop_from = 0.6
    def value(s, t, p):
        dur = float(p.get('dur', 1.6)); f = ease(prog(t, s.at + 0.2, dur))
        v = float(p.get('from', 0)) + (float(p['to']) - float(p.get('from', 0))) * f
        dec = int(p.get('decimals', 0))
        return f"{p.get('prefix', '')}{v:,.{dec}f}{p.get('suffix', '')}"
    def dynamic(s, t, p): return s.value(t, p)
    def draw(s, cv, t, sa):
        sc, a, dy, _ = s.enter(t)
        p, idx = s.props(t)
        txt = s.value(t, p)
        k = (idx, txt)
        if k not in s.sprites:
            parts = [(txt, col(p.get('color', 'yellow')))] + [(x[0], col(x[1] if len(x) > 1 else 'white')) for x in p.get('after', [])]
            s.sprites[k] = rich_sprite(parts, float(p.get('size', 96)), max_w=1000)
        put(cv, s.sprites[k], (id(s), k), s.x, s.y + dy, sc, a * sa)

class Flow(El):
    def visible(s, t): return t >= s.at and (s.until is None or t < s.until + 0.2)
    def dynamic(s, t, p): return int(t * FPS)
    def key(s, t, sa): return (int(t * FPS), round(sa, 2), s.props(t)[1])
    def draw(s, cv, t, sa):
        p, _ = s.props(t)
        (ax, ay), (bx, by) = p['from'], p['to']
        c = col(p.get('color', 'cyan'))[:3]
        out_a = 1.0 - prog(t, s.until, 0.2) if s.until is not None else 1.0
        A = sa * out_a
        d = ImageDraw.Draw(cv, 'RGBA')
        ap = ease(prog(t, s.at, 0.4))
        ex, ey = ax + (bx - ax) * ap, ay + (by - ay) * ap
        d.line((ax, ay, ex, ey), fill=c + (int(70 * A),), width=3)
        if ap < 1: return
        n, rate, r = int(p.get('n', 5)), float(p.get('rate', 1)), float(p.get('dot', 7))
        for k in range(n):
            f = ((t - s.at) * rate * 0.5 + k / n) % 1
            x, y = ax + (bx - ax) * f, ay + (by - ay) * f
            if p.get('square'): d.rounded_rectangle((x - r, y - r, x + r, y + r), 3, fill=c + (int(255 * A),))
            else: d.ellipse((x - r, y - r, x + r, y + r), fill=c + (int(255 * A),))

class Gauge(El):
    def dynamic(s, t, p): return round(ease(prog(t, s.at + 0.2, float(p.get('dur', 1.3)))), 2)
    def draw(s, cv, t, sa):
        sc, a, dy, _ = s.enter(t)
        p, idx = s.props(t)
        f = ease(prog(t, s.at + 0.2, float(p.get('dur', 1.3)))) * float(p.get('to', 100)) / 100
        w = float(p.get('w', 560)); x0 = s.x - w / 2; y = s.y + dy; hh = float(p.get('h', 38))
        c0, c1 = col(p.get('color_from', 'cyan'))[:3], col(p.get('color_to', 'red'))[:3]
        gc = tuple(int(c0[i] * (1 - f) + c1[i] * f) for i in range(3))
        d = ImageDraw.Draw(cv, 'RGBA')
        d.rounded_rectangle((x0, y - hh / 2, x0 + w, y + hh / 2), hh / 2, fill=(255, 255, 255, int(30 * a * sa)))
        if f > 0.02: d.rounded_rectangle((x0, y - hh / 2, x0 + max(hh, w * f), y + hh / 2), hh / 2, fill=gc + (int(255 * a * sa),))
        if p.get('label'):
            k = ('lab', idx)
            if k not in s.sprites: s.sprites[k] = rich_sprite([(p['label'], col('white'))], float(p.get('size', 34)), max_w=600)
            spr = s.sprites[k]; put(cv, spr, (id(s), k), x0 - 20 - spr.width, y, 1, a * sa, anchor='left')
        if p.get('show_pct', True):
            txt = f'{int(round(f * 100))}%'
            spr = rich_sprite([(txt, gc + (255,))], float(p.get('size', 34)))
            put(cv, spr, ('pct', txt, gc), x0 + w + 20, y, 1, a * sa, anchor='left')

class Strike(El):
    def dynamic(s, t, p): return round(ease(prog(t, s.at, 0.25)), 2)
    def draw(s, cv, t, sa):
        p, _ = s.props(t)
        (ax, ay), (bx, by) = p['from'], p['to']
        f = ease(prog(t, s.at, 0.25))
        out_a = 1.0 - prog(t, s.until, 0.2) if s.until is not None else 1.0
        ImageDraw.Draw(cv, 'RGBA').line((ax, ay, ax + (bx - ax) * f, ay + (by - ay) * f), fill=col(p.get('color', 'red'))[:3] + (int(235 * sa * out_a),), width=int(p.get('width', 12)))

_WORLD = None
def world():
    global _WORLD
    if _WORLD is None:
        _WORLD = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'world_110m.json')))
    return _WORLD

def country_bbox(isos, pad=6):
    xs, ys = [], []
    for iso in isos:
        for r in world()[iso]['rings']:
            for x, y in r: xs.append(x); ys.append(y)
    return [min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad]

class Map(El):
    """world map: highlights countries, zooms (focus), drops pins."""
    pop_from = 0.9
    def __init__(s, e, st):
        El.__init__(s, e, st)
        s.w, s.h = int(e.get('w', 1000)), int(e.get('h', 560))
        s.hl = [dict(h, at=tref(h.get('at'), s.at)) for h in e.get('highlight', [])]
        s.pins = [dict(p, at=tref(p.get('at'), s.at)) for p in e.get('pins', [])]
        fo = [dict(f, at=tref(f.get('at'), s.at)) for f in e.get('focus', [])]
        s.views = [(s.at - 9, s.fit([-170, -57, 190, 80]))]
        for f in sorted(fo, key=lambda d: d['at']):
            bb = f['bbox'] if 'bbox' in f else country_bbox(f['iso'] if isinstance(f['iso'], list) else [f['iso']], f.get('pad', 6))
            s.views.append((f['at'], s.fit(bb)))
    def fit(s, bb):   # grow bbox to panel aspect
        x0, y0, x1, y1 = bb; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w, h = x1 - x0, y1 - y0; asp = s.w / s.h
        if w / h < asp: w = h * asp
        else: h = w / asp
        return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
    def view(s, t):
        v = s.views[0][1]
        for (ta, vb), (_, va) in zip(s.views[1:], s.views[:-1]):
            if t >= ta:
                f = ease(prog(t, ta, 0.9)); v = [a + (b - a) * f for a, b in zip(va, vb)]
        return v
    def hstate(s, t): return tuple(round(prog(t, h['at'], 0.3), 1) for h in s.hl)
    def dynamic(s, t, p):
        return (tuple(round(x, 2) for x in s.view(t)), s.hstate(t), tuple(round(back(prog(t, q['at'], 0.35)), 2) for q in s.pins))
    def draw(s, cv, t, sa):
        sc, a, dy, _ = s.enter(t)
        k = ('map',) + s.dynamic(t, None)[:2]
        if k not in s.sprites:
            if len(s.sprites) > 60: s.sprites.clear()
            v = s.view(t); S2 = 2
            im = Image.new('RGBA', (s.w * S2, s.h * S2), (0, 0, 0, 0)); d = ImageDraw.Draw(im, 'RGBA')
            fx = s.w * S2 / (v[2] - v[0]); fy = s.h * S2 / (v[3] - v[1])
            P = lambda x, y: ((x - v[0]) * fx, (v[3] - y) * fy)
            land, border = col(s.e.get('land', 'white/16')), col(s.e.get('border', 'white/35'))
            hcol = {}
            for h, pr in zip(s.hl, s.hstate(t)):
                if pr > 0:
                    for iso in (h['iso'] if isinstance(h['iso'], list) else [h['iso']]):
                        c = col(h.get('color', 'yellow'))[:3]; base = land[:3]
                        hcol[iso] = tuple(int(base[i] + (c[i] - base[i]) * pr) for i in range(3)) + (255,)
            for iso, cdat in world().items():
                if iso == 'ATA' and 'ATA' not in hcol: continue
                for r in cdat['rings']:
                    xs = [q[0] for q in r]
                    if max(xs) < v[0] - 5 or min(xs) > v[2] + 5: continue
                    d.polygon([P(x, y) for x, y in r], fill=hcol.get(iso, land), outline=border)
            s.sprites[k] = im.resize((s.w, s.h), Image.LANCZOS)
        spr = s.sprites[k]
        lay = spr
        if s.pins:
            lay = spr.copy(); v = s.view(t)
            for q in s.pins:
                ps = back(prog(t, q['at'], 0.35))
                if ps <= 0: continue
                x = (q['lon'] - v[0]) / (v[2] - v[0]) * s.w; y = (v[3] - q['lat']) / (v[3] - v[1]) * s.h
                r = 11 * ps; c = col(q.get('color', 'red'))
                dd = ImageDraw.Draw(lay, 'RGBA')
                dd.ellipse((x - r * 2.2, y - r * 2.2, x + r * 2.2, y + r * 2.2), fill=c[:3] + (60,))
                dd.ellipse((x - r, y - r, x + r, y + r), fill=c, outline=(255, 255, 255, 255), width=3)
                if q.get('label') and ps > 0.5:
                    lab = rich_sprite([(q['label'], col('white'))], float(q.get('size', 30)), max_w=600)
                    bx = int(min(max(4, x - lab.width / 2), s.w - lab.width - 4)); by = int(y - 26 - lab.height)
                    bg = Image.new('RGBA', (lab.width + 24, lab.height + 8), (0, 0, 0, 0))
                    ImageDraw.Draw(bg).rounded_rectangle((0, 0, bg.width - 1, bg.height - 1), 14, fill=(10, 12, 24, 210))
                    bg.alpha_composite(lab, (12, 4)); _safe(lay, bg, bx - 12, max(0, by))
        put(cv, lay, ('mapf', id(s), k, t) if s.pins else (id(s), k), s.x, s.y + dy, sc, a * sa)

class Chart(El):
    """bar / line chart that grows in. labels, values, prefix/suffix, per-bar colours.
    bar_at: optional list of time refs, one per bar (each bar grows when its value is spoken).
    value_text: optional final labels per bar (e.g. "₹1 Cr")."""
    def __init__(s, e, st):
        El.__init__(s, e, st)
        s.bar_at = [tref(x) for x in e['bar_at']] if e.get('bar_at') else None
    def t_of(s, i): return s.bar_at[i] if s.bar_at else s.at + 0.12 * i
    def dynamic(s, t, p): return tuple(round(prog(t, s.t_of(i), float(p.get('dur', 1.2 if s.bar_at else 1.5))), 2) for i in range(len(p['values'])))
    def draw(s, cv, t, sa):
        sc, a, dy, _ = s.enter(t)
        p, idx = s.props(t)
        A = a * sa
        w, h = float(p.get('w', 900)), float(p.get('h', 520)); x0 = s.x - w / 2; yb = s.y + h / 2 + dy - 50
        vals = [float(v) for v in p['values']]; labels = p.get('labels', [''] * len(vals))
        vmax = float(p.get('max', max(vals) * 1.1 or 1)); n = len(vals); dur = float(p.get('dur', 1.2 if s.bar_at else 1.5))
        d = ImageDraw.Draw(cv, 'RGBA'); base_c = col(p.get('color', 'cyan'))[:3]
        cols = p.get('colors', {})
        d.line((x0, yb, x0 + w, yb), fill=(255, 255, 255, int(90 * A)), width=3)
        fmt = lambda v: f"{p.get('prefix', '')}{v:,.{int(p.get('decimals', 0))}f}{p.get('suffix', '')}"
        slot = w / n
        pts = []
        for i, v in enumerate(vals):
            f = ease(prog(t, s.t_of(i), dur)) if p.get('kind', 'bar') == 'bar' else 1
            c = col(cols.get(str(i), base_c) if isinstance(cols, dict) else base_c)[:3]
            cx = x0 + slot * (i + 0.5); top = yb - (h - 110) * (v / vmax) * f
            if p.get('kind', 'bar') == 'bar':
                bw = slot * 0.62
                if f > 0.01 and yb - 2 - top >= 2: d.rounded_rectangle((cx - bw / 2, top, cx + bw / 2, yb - 2), max(0, min(14, bw / 4, (yb - 2 - top) / 2 - 0.5)), fill=c + (int(255 * A),))
                if f > 0.05 and p.get('value_labels', True):
                    vt = p['value_text'][i] if p.get('value_text') and f >= 0.999 else fmt(v * f)
                    spr = rich_sprite([(vt, c + (255,))], float(p.get('value_size', 32)))
                    put(cv, spr, ('cv', vt, c, p.get('value_size', 32)), cx, top - 30, 1, A * min(1, f * 3))
            pts.append((cx, yb - (h - 110) * (v / vmax)))
            if labels[i] and (not s.bar_at or t >= s.t_of(i) - 0.6 or p.get('labels_first')):
                ls = rich_sprite([(str(labels[i]), col('muted'))], float(p.get('label_size', 28)), max_w=slot * 1.1)
                put(cv, ls, ('cl', str(labels[i]), int(slot)), cx, yb + 32, 1, A)
        if p.get('kind') == 'line':
            f = ease(prog(t, s.at, dur)); total = f * (n - 1)
            path = [pts[0]]
            for i in range(1, n):
                if total >= i: path.append(pts[i])
                elif total > i - 1:
                    r = total - (i - 1); path.append((pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * r, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * r)); break
            if len(path) > 1:
                fillc = base_c + (int(40 * A),)
                d.polygon(path + [(path[-1][0], yb), (path[0][0], yb)], fill=fillc)
                d.line(path, fill=base_c + (int(255 * A),), width=7, joint='curve')
            for i, q in enumerate(pts):
                if total >= i - 0.001:
                    d.ellipse((q[0] - 9, q[1] - 9, q[0] + 9, q[1] + 9), fill=(255, 255, 255, int(255 * A)))
            if f >= 1 and p.get('value_labels', True):
                spr = rich_sprite([(fmt(vals[-1]), col(p.get('end_color', 'yellow')))], float(p.get('value_size', 40)))
                put(cv, spr, ('cle', fmt(vals[-1])), pts[-1][0] - spr.width / 2 + 10, pts[-1][1] - 40, 1, A)

class Timeline(El):
    """vertical (default) or horizontal timeline; each item appears at its own time."""
    def __init__(s, e, st):
        El.__init__(s, e, st)
        s.items = [dict(i, at=tref(i.get('at'), s.at)) for i in e['items']]
    def dynamic(s, t, p): return tuple(round(prog(t, i['at'], 0.4), 2) for i in s.items)
    def draw(s, cv, t, sa):
        _, a, _, _ = s.enter(t); A = a * sa
        p, _ = s.props(t)
        n = len(s.items); L = float(p.get('length', 760)); vert = p.get('orient', 'vertical') == 'vertical'
        c = col(p.get('color', 'cyan'))[:3]
        d = ImageDraw.Draw(cv, 'RGBA')
        pos = lambda i: (s.x, s.y + L * i / max(1, n - 1)) if vert else (s.x - L / 2 + L * i / max(1, n - 1), s.y)
        shown = [prog(t, it['at'], 0.4) for it in s.items]
        last = max([i for i, v in enumerate(shown) if v > 0], default=-1)
        if last >= 0:
            (ax, ay), (bx, by) = pos(0), pos(last)
            f = ease(shown[last]); prev = pos(max(0, last - 1))
            ex, ey = prev[0] + (bx - prev[0]) * f, prev[1] + (by - prev[1]) * f
            d.line((ax, ay, ex, ey), fill=c + (int(200 * A),), width=6)
        for i, it in enumerate(s.items):
            v = shown[i]
            if v <= 0: continue
            x, y = pos(i); ic = col(it.get('color', p.get('color', 'cyan')))[:3]; r = 14 * back(v)
            d.ellipse((x - r, y - r, x + r, y + r), fill=ic + (int(255 * A),), outline=(255, 255, 255, int(255 * A)), width=3)
            k = ('tl', i)
            if k not in s.sprites:
                parts = [(str(it.get('date', '')), col(it.get('color', 'yellow')))]
                ds = rich_sprite(parts, float(p.get('date_size', 40)), max_w=500, align='left')
                ts = rich_sprite([(it.get('text', ''), col('white'))], float(p.get('size', 34)), FONT_MED, max_w=float(p.get('text_w', 700)), align='left' if vert else 'center')
                im = Image.new('RGBA', (max(ds.width, ts.width), ds.height + ts.height), (0, 0, 0, 0))
                im.alpha_composite(ds, (0 if vert else (im.width - ds.width) // 2, 0)); im.alpha_composite(ts, (0 if vert else (im.width - ts.width) // 2, ds.height - 6))
                s.sprites[k] = im
            spr = s.sprites[k]; e_ = ease(v)
            if vert: put(cv, spr, (id(s), k), x + 40 + 20 * (1 - e_), y + 4, 1, A * e_, anchor='left')
            else: put(cv, spr, (id(s), k), x, y + (-1 if i % 2 == 0 else 1) * (spr.height / 2 + 34), 1, A * e_)

class Note(El):
    """pinned paper note (evidence board)."""
    pop_from = 0.4
    def make(s, p):
        w = int(p.get('w', 420)); pad = 28
        ts = rich_sprite([(p.get('text', ''), col(p.get('fg', 'ink')))], float(p.get('size', 36)), FONT_BOLD, max_w=w - 2 * pad)
        h = ts.height + 2 * pad + 10
        im = Image.new('RGBA', (w + 40, h + 50), (0, 0, 0, 0))
        sh = Image.new('RGBA', im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rectangle((24, 34, w + 24, h + 34), fill=(0, 0, 0, 140))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
        ImageDraw.Draw(im).rectangle((16, 22, w + 16, h + 22), fill=col(p.get('bg', 'paper')))
        im.alpha_composite(ts, (16 + (w - ts.width) // 2, 22 + pad + 4))
        if p.get('emoji'):
            em = emoji_sprite(p['emoji'], 54); im.alpha_composite(em, (w + 16 - em.width - 6, h + 22 - em.height - 4))
        d = ImageDraw.Draw(im); px = 16 + w // 2
        d.ellipse((px - 13, 9, px + 13, 35), fill=col(p.get('pin', 'blood')), outline=(255, 255, 255, 120), width=2)
        return im.rotate(float(p.get('rotate', -3)), resample=Image.BICUBIC, expand=True)

class String(El):
    """red string between board points, drawn progressively, with pins."""
    def dynamic(s, t, p): return round(ease(prog(t, s.at, float(p.get('dur', 0.8)))), 2)
    def draw(s, cv, t, sa):
        p, _ = s.props(t); pts = p['points']; f = ease(prog(t, s.at, float(p.get('dur', 0.8))))
        out_a = 1.0 - prog(t, s.until, 0.2) if s.until is not None else 1.0
        A = sa * out_a; c = col(p.get('color', 'blood'))[:3]
        segl = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]; rem = sum(segl) * f
        d = ImageDraw.Draw(cv, 'RGBA'); path = [tuple(pts[0])]
        for i, L in enumerate(segl):
            if rem <= 0: break
            r = min(1, rem / L); rem -= L
            path.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * r, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * r))
        if len(path) > 1: d.line(path, fill=c + (int(235 * A),), width=int(p.get('width', 5)), joint='curve')
        for q in pts[:max(1, len(path))]:
            d.ellipse((q[0] - 10, q[1] - 10, q[0] + 10, q[1] + 10), fill=c + (int(255 * A),), outline=(255, 255, 255, int(150 * A)), width=2)


def indian(n, dec=0):
    """1234567 -> 12,34,567 (Indian digit grouping)."""
    neg = n < 0; n = abs(n)
    whole = int(round(n)) if dec == 0 else int(n)
    st_ = str(whole)
    if len(st_) > 3:
        head, tail = st_[:-3], st_[-3:]
        parts = []
        while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
        if head: parts.insert(0, head)
        st_ = ','.join(parts + [tail])
    if dec: st_ += f'{n - whole:.{dec}f}'[1:]
    return ('-' if neg else '') + st_

class Headline(El):
    """multi-line headline; each line slides up out of its own mask (expo), staggered."""
    def __init__(s, e, st):
        El.__init__(s, e, st)
        s.lines = e['lines']
        la = e.get('line_at')
        s.lat = [tref(la[i]) if la and i < len(la) else s.at + i * float(e.get('stagger', 0.09)) for i in range(len(s.lines))]
    def line_sprite(s, i):
        k = ('ln', i)
        if k not in s.sprites:
            ln = s.lines[i]
            parts = [(ln, col(s.e.get('color', 'ink')))] if isinstance(ln, str) else [(q[0], col(q[1] if len(q) > 1 else s.e.get('color', 'ink'))) for q in ln]
            fp = FONT_DISPLAY if s.e.get('font', 'display') == 'display' else FONT_BOLD
            s.sprites[k] = rich_sprite(parts, float(s.e.get('size', 96)), fp, line_gap=1.0, max_w=2000, align='left')
        return s.sprites[k]
    def dynamic(s, t, p): return tuple(round(expo(prog(t, a, 0.85)), 2) for a in s.lat)
    def enter(s, t):
        out_a = 1.0 - prog(t, s.until, 0.3) if s.until is not None else 1.0
        return 1, out_a, 0, True
    def draw(s, cv, t, sa):
        _, oa, _, _ = s.enter(t)
        lh = float(s.e.get('size', 96)) * float(s.e.get('leading', 1.12))
        for i in range(len(s.lines)):
            p = expo(prog(t, s.lat[i], 0.85))
            if p <= 0: continue
            spr = s.line_sprite(i)
            d = int(spr.height * 0.95 * (1 - p))
            vis = spr.height - d
            if vis <= 1: continue
            crop = spr.crop((0, 0, spr.width, vis))
            al = min(1.0, p * 1.6) * sa * oa
            x = s.x if s.e.get('align', 'left') == 'left' else (s.x - spr.width / 2 if s.e.get('align') == 'center' else s.x - spr.width)
            ytop = s.y + i * lh
            put(cv, crop, (id(s), 'c', i, vis), x, ytop + d + vis / 2, 1, al, anchor='left')

class Number(El):
    """big display number that counts; Indian grouping by default (1,00,000)."""
    def val(s, t, p):
        f = inout(prog(t, s.at + 0.05, float(p.get('dur', 1.3))))
        v = float(p.get('from', 0)) + (float(p['value']) - float(p.get('from', 0))) * f
        dec = int(p.get('decimals', 0))
        body = indian(v, dec) if p.get('grouping', 'indian') == 'indian' else f'{v:,.{dec}f}'
        return p.get('prefix', '') + body + p.get('suffix', '')
    def dynamic(s, t, p): return s.val(t, p)
    def draw(s, cv, t, sa):
        _, a, dy, _ = s.enter(t)
        p, idx = s.props(t)
        txt = s.val(t, p); k = ('n', idx, txt)
        if k not in s.sprites:
            if len(s.sprites) > 200: s.sprites.clear()
            s.sprites[k] = rich_sprite([(txt, col(p.get('color', 'ink')))], float(p.get('size', 200)),
                                       FONT_DISPLAY if p.get('font', 'display') == 'display' else FONT_BOLD, max_w=3000, align='left')
        spr = s.sprites[k]
        x = s.x if p.get('align', 'left') == 'left' else s.x - spr.width / 2
        put(cv, spr, (id(s), k), x, s.y + dy, 1, a * sa, anchor='left')

class Rings(El):
    """growth rings: ring i has area proportional to values[i]. Reveal groups of rings over time,
    tint bands, show an inner disc (e.g. money invested) and leader-line callouts."""
    def __init__(s, e, st):
        El.__init__(s, e, st)
        s.vals = [float(v) for v in e['values']]; s.R = float(e.get('radius', 330))
        s.vmax = float(e.get('max', max(s.vals)))
        s.rev = [dict(r, at=tref(r['at'])) for r in e.get('reveal', [{'upto': len(s.vals), 'at': s.at}])]
        s.bands = [dict(b, at=tref(b['at'])) for b in e.get('bands', [])]
        s.inner = dict(e['inner'], at=tref(e['inner']['at'])) if e.get('inner') else None
        s.calls = [dict(c, at=tref(c['at']), until=tref(c.get('until'))) for c in e.get('callouts', [])]
        s.ghost = tref(e.get('ghost_at'))
    def radius(s, i): return s.R * math.sqrt(max(0, s.vals[i]) / s.vmax)
    def shown(s, t):
        n, prev = 0.0, 0
        for r in s.rev:
            cnt = r['upto'] - prev
            n += cnt * inout(prog(t, r['at'], float(r.get('dur', 0.35 + 0.12 * cnt))))
            prev = r['upto']
        return n
    def dynamic(s, t, p):
        return (round(s.shown(t), 2) + (round(prog(t, s.ghost, 1.2), 2) * 0.001 if s.ghost is not None else 0), tuple(round(prog(t, b['at'], 0.6), 2) for b in s.bands),
                round(prog(t, s.inner['at'], 0.9), 2) if s.inner else 0,
                tuple(round(prog(t, c['at'], 0.5), 2) - (round(prog(t, c['until'], 0.3), 2) if c['until'] else 0) for c in s.calls))
    def draw(s, cv, t, sa):
        _, a, dy, _ = s.enter(t); A = a * sa
        k = ('r',) + s.dynamic(t, None)[:3] + (round(A, 2),)
        R = s.R; S2 = 2; size = int(2 * R + 8)
        if k not in s.sprites:
            if len(s.sprites) > 80: s.sprites.clear()
            im = Image.new('RGBA', (size * S2, size * S2), (0, 0, 0, 0)); d = ImageDraw.Draw(im, 'RGBA')
            c0 = size * S2 / 2
            n = s.shown(t); full = int(n); frac = n - full
            stroke = col(s.e.get('stroke', 'ink'))[:3]; fillc = col(s.e.get('fill', 'bg2'))[:3]
            def circ(r, **kw): d.ellipse((c0 - r * S2, c0 - r * S2, c0 + r * S2, c0 + r * S2), **kw)
            radii = [s.radius(i) for i in range(len(s.vals))]
            if s.ghost is not None and t >= s.ghost:   # faint outlines of every ring, before they fill in
                g = inout(prog(t, s.ghost, 1.2))
                for i, r in enumerate(radii):
                    if g * len(radii) > i: circ(r, outline=stroke + (int(38 * A),), width=S2)
            outer = 0
            if full > 0: outer = radii[full - 1]
            if full < len(radii) and frac > 0: outer = (radii[full - 1] if full else 0) + (radii[full] - (radii[full - 1] if full else 0)) * frac
            if outer > 0: circ(outer, fill=fillc + (int(255 * A),))
            for b in s.bands:      # tinted bands (drawn outer->inner so annulus shows)
                pb = inout(prog(t, b['at'], 0.6))
                if pb <= 0: continue
                hi_i = min(b['to'], full + (1 if frac > 0 else 0)) - 1; lo_i = b['from'] - 1
                if hi_i < b['from'] - 1 + 1 - 1 or hi_i < 0: continue
                r_hi = min(outer, radii[hi_i]); r_lo = radii[lo_i] if lo_i >= 0 else 0
                if r_hi <= r_lo: continue
                bc = col(b.get('color', 'accent'))[:3]
                d.ellipse((c0 - r_hi * S2, c0 - r_hi * S2, c0 + r_hi * S2, c0 + r_hi * S2), outline=bc + (int(255 * A * pb * float(b.get('opacity', 0.9))),),
                          width=max(1, int((r_hi - r_lo) * S2)))
            if s.inner:
                pi = inout(prog(t, s.inner['at'], 0.9))
                if pi > 0:
                    ri = s.R * math.sqrt(float(s.inner['value']) / s.vmax) * (0.6 + 0.4 * pi)
                    circ(ri, fill=col(s.inner.get('color', 'accent2'))[:3] + (int(235 * A * pi),))
            for i in range(full + (1 if frac > 0 else 0)):
                r = radii[i] if i < full else outer
                w = 3 if (i + 1) % int(s.e.get('major_every', 5)) == 0 else 1
                circ(r, outline=stroke + (int((150 if w > 1 else 60) * A),), width=w * S2)
            s.sprites[k] = im.resize((size, size), Image.LANCZOS)
        put(cv, s.sprites[k], (id(s), k), s.x, s.y + dy, 1, 1)
        # callouts: hairline from ring edge to a label
        dr = ImageDraw.Draw(cv, 'RGBA')
        for c in s.calls:
            pc = expo(prog(t, c['at'], 0.5)) * (1 - (prog(t, c['until'], 0.3) if c['until'] else 0))
            if pc <= 0.01: continue
            r = s.radius(int(c['ring']) - 1) if c.get('ring') else s.R * math.sqrt(float(c['value']) / s.vmax)
            ang = math.radians(float(c.get('angle', -35)))
            ex, ey = s.x + r * math.cos(ang), s.y + dy + r * math.sin(ang)
            side = 1 if math.cos(ang) >= 0 else -1
            tx_ = float(c.get('x', s.x + side * (s.R + 40)))
            ty_ = ey if c.get('y') is None else float(c['y'])
            mx = ex + (tx_ - ex) * pc
            cc = col(c.get('color', 'ink'))[:3]
            dr.ellipse((ex - 6, ey - 6, ex + 6, ey + 6), fill=cc + (int(255 * A * pc),))
            dr.line((ex, ey, ex + (tx_ - ex) * 0.25 * pc, ty_ if pc > 0.25 else ey + (ty_ - ey) * pc * 4), fill=cc + (int(160 * A * pc),), width=2)
            dr.line((ex + (tx_ - ex) * 0.25 * pc, ty_, mx, ty_), fill=cc + (int(160 * A * pc),), width=2)
            kk = ('cl', id(c) if False else c.get('text'))
            if kk not in s.sprites:
                parts = [(c['text'], col(c.get('color', 'ink')))]
                sz = float(c.get('size', 44))
                main = rich_sprite(parts, sz, FONT_DISPLAY, max_w=600, align='left' if side > 0 else 'left')
                if c.get('sub'):
                    sub = rich_sprite([(c['sub'], col('muted'))], sz * 0.5, FONT_MED, max_w=600, align='left')
                    im = Image.new('RGBA', (max(main.width, sub.width), main.height + sub.height - 6), (0, 0, 0, 0))
                    im.alpha_composite(main, (0 if side > 0 else im.width - main.width, 0)); im.alpha_composite(sub, (0 if side > 0 else im.width - sub.width, main.height - 6))
                    main = im
                s.sprites[kk] = main
            spr = s.sprites[kk]
            lx = tx_ + 14 if side > 0 else tx_ - 14 - spr.width
            put(cv, spr, (id(s), kk), lx, ty_ + spr.height * 0.32, 1, A * pc, anchor='left')

TYPES = dict(headline=Headline, number=Number, rings=Rings, map=Map, chart=Chart, timeline=Timeline, note=Note, string=String, text=Text, emoji=Emoji, pill=Pill, db=DB, box=Box, card=Card, image=Image_, counter=Counter, flow=Flow, gauge=Gauge, strike=Strike)

def expand(e):
    """bullets -> one left-anchored text per item."""
    if e['type'] != 'bullets': return [e]
    out, y = [], float(e.get('y', 300)); gap = float(e.get('gap', 90)); size = e.get('size', 48)
    for it in e['items']:
        txt = ((it.get('emoji', e.get('bullet', '•')) + ' ') if it.get('emoji', e.get('bullet', '•')) else '') + it['text']
        out.append(dict(type='text', anchor='left', x=e.get('x', 90), y=y, size=size, at=it.get('at', e.get('at')), anim=e.get('anim', 'slide'),
                        parts=[[txt, it.get('color', e.get('color', 'white'))]], max_w=e.get('max_w', 900)))
        y += gap
    return out

class Scene:
    def __init__(s, sc, start, end):
        s.start, s.end = start, end
        s.els = []
        for e in sc.get('elements', []):
            for ee in expand(e):
                if ee['type'] not in TYPES: raise ValueError(f"unknown element type {ee['type']!r}; allowed: {sorted(TYPES) + ['bullets']}")
                s.els.append(TYPES[ee['type']](ee, start))
    def alpha(s, t):
        # old scene clears out in ~0.15s around the cut; the new one's elements pop in on their own
        a_in = 1.0 if s.start <= T0 + 0.01 else clamp((t - s.start + 0.02) / 0.1)
        if PRO: return a_in * (1 - inout(clamp((t - s.end + 0.38) / 0.4)))
        return a_in * (1 - clamp((t - s.end + 0.1) / 0.15))

def build_scenes():
    raw = sorted(SPEC.get('scenes', []), key=lambda sc: tref(sc.get('start'), T0))
    starts = [tref(sc.get('start'), T0) for sc in raw]
    return [Scene(sc, st, starts[i + 1] if i + 1 < len(raw) else T1 + 5) for i, (sc, st) in enumerate(zip(raw, starts))]

SCENES = build_scenes()
STAGE = []
for _e in SPEC.get('stage', []):
    for _ee in expand(_e):
        STAGE.append(TYPES[_ee['type']](_ee, T0))
_ACC = SPEC.get('accent', 'blood' if SPEC.get('theme') == 'mystery' else 'cyan')
if PRO: SPEC.setdefault('cta', None); SPEC.pop('chip', None); SPEC.setdefault('visualizer', False); SPEC['face_emoji'] = []
CHIP = Pill(dict(type='pill', label=SPEC['chip'], x=540, y=200, size=26, fg='red' if _ACC == 'blood' else _ACC, bg=f'{_ACC}/16', at=T0, anim='none'), T0) if SPEC.get('chip') else None
cta = SPEC.get('cta', {'text': '+  FOLLOW for more', 'last': 1.8})
CTA = Pill(dict(type='pill', label=cta['text'], x=540, y=cta.get('y', 1130 if AUDIO_ONLY else 815), size=cta.get('size', 34), fg='dark', bg='white', pulse=True,
                at=T1 - float(cta.get('last', 1.8))), T0) if cta else None

# ------------------------------------------------------------------ top panel
def make_bg():
    g = np.linspace(0, 1, TOPH)[:, None, None]
    arr = (np.array(BG1) * (1 - g) + np.array(BG2) * g) * np.ones((1, W, 1))
    yy, xx = np.mgrid[0:TOPH, 0:W]
    gy = 700 if AUDIO_ONLY else TOPH * 0.55; gr = 650 if AUDIO_ONLY else TOPH * 0.45
    glow = np.exp(-(((xx - W * 0.5) / (W * 0.45)) ** 2 + ((yy - gy) / gr) ** 2))
    arr += glow[..., None] * np.array(GLOW)
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert('RGB')
    if SPEC.get('theme') == 'mystery':   # vignette + static film grain + faint red glow
        a = np.asarray(im).astype(np.float32)
        yy, xx = np.mgrid[0:TOPH, 0:W]
        vig = 1 - 0.55 * np.clip((((xx - W / 2) / (W * 0.7)) ** 2 + ((yy - TOPH * 0.45) / (TOPH * 0.75)) ** 2), 0, 1)
        a = a * vig[..., None] + np.random.default_rng(7).normal(0, 7, a.shape[:2])[..., None]
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if SPEC.get('grid', SPEC.get('theme') != 'mystery'):
        d = ImageDraw.Draw(im, 'RGBA')  # blend mode
        for x in range(0, W, 60): d.line((x, 0, x, TOPH), fill=(255, 255, 255, 10))
        for y in range(0, TOPH, 60): d.line((0, y, W, y), fill=(255, 255, 255, 10))
    im = im.convert('RGB')
    if not AUDIO_ONLY: ImageDraw.Draw(im).rectangle((0, TOPH - 3, W, TOPH), fill=col(SPEC.get('accent', 'cyan')))
    return im
def make_bg_pro():
    yy, xx = np.mgrid[0:TOPH, 0:W].astype(np.float32)
    b1, b2 = np.array(COL['bg'], np.float32), np.array(COL['bg2'], np.float32)
    lift = np.exp(-(((xx - W * 0.62) / (W * 0.8)) ** 2 + ((yy - TOPH * 0.32) / (TOPH * 0.55)) ** 2))
    a = b1 * (1 - lift[..., None]) + b2 * lift[..., None]
    vig = 1 - 0.35 * np.clip(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - TOPH / 2) / (TOPH * 0.7)) ** 2, 0, 1)
    a = a * vig[..., None] + np.random.default_rng(3).normal(0, 2.2, a.shape[:2])[..., None]   # anti-banding dither
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
BG = make_bg_pro() if PRO else make_bg()

def top_key(t):
    k = []
    for i, sc in enumerate(SCENES):
        a = sc.alpha(t)
        if a <= 0.001 or t < sc.start: continue
        k.append((i, round(a, 2), tuple((j, e.key(t, a)) for j, e in enumerate(sc.els) if e.visible(t))))
    if CTA and CTA.visible(t): k.append(('cta', CTA.key(t, 1)))
    k.append(tuple(e.key(t, 1) for e in STAGE if e.visible(t)))
    return tuple(k)

def top_panel(t):
    cv = BG.copy()
    if CHIP: CHIP.draw(cv, t, 1)
    for e in STAGE:
        if e.visible(t): e.draw(cv, t, 1)
    for sc in SCENES:
        a = sc.alpha(t)
        if a <= 0.001 or t < sc.start: continue
        OFFY[0] = -30 * (1 - a) if (PRO and t > sc.end - 0.5) else 0.0
        for e in sc.els:
            if e.visible(t): e.draw(cv, t, a)
        OFFY[0] = 0.0
    if CTA and CTA.visible(t): CTA.draw(cv, t, 1)
    return np.asarray(cv)

# ------------------------------------------------------------------ captions + face emojis (numpy overlays)
CAP_Y = int(SPEC.get('caption_y', 1470 if PRO else 1390)) if AUDIO_ONLY else (TOPH + 62 if SPEC.get('caption_pos', 'seam') == 'seam' else int(SPEC.get('caption_y', 1480)))
def word_times(i):
    o = TIM[i]; ws = PHR[i]['text'].split()
    L = [len(w) + 2 for w in ws]; tot = sum(L); t = o['start']; out = []
    for l in L: out.append(t); t += (o['end'] - o['start']) * l / tot
    return out
def caption_sprite_pro(i, k):
    key = ('pro', i, k)
    if key in _cap: return _cap[key]
    p = PHR[i]; size = float(SPEC.get('caption_size', 50))
    hl = col(SPEC.get('caption_highlight', 'accent'))
    parts = []
    for j, w in enumerate(p['text'].split()):
        c = (hl if j in p['hl'] else col('ink')) if j < k else col('ink', 80)
        parts.append((w, c))
    ts = rich_sprite(parts, size, FONT_BOLD, max_w=900)
    sh = Image.new('RGBA', (ts.width + 60, ts.height + 60), (0, 0, 0, 0))
    m = Image.new('L', sh.size, 0); m.paste(ts.split()[3].point(lambda v: int(v * 0.75)), (30, 30))
    sh.putalpha(m.filter(ImageFilter.GaussianBlur(12)))
    sh = Image.composite(Image.new('RGBA', sh.size, col('bg')[:3] + (255,)), sh, Image.new('L', sh.size, 0)) if False else Image.merge('RGBA', (*Image.new('RGB', sh.size, tuple(int(c * 0.4) for c in col('bg')[:3])).split(), sh.split()[3]))
    sh.alpha_composite(ts, (30, 30))
    _cap[key] = sh
    return sh
_cap = {}
def caption_sprite(i):
    if i in _cap: return _cap[i]
    p = PHR[i]
    size = float(SPEC.get('caption_size', 60))
    parts = [(w, HL if j in p['hl'] else col('white')) for j, w in enumerate(p['text'].split())]
    ts = rich_sprite(parts, size, max_w=880)
    pw, ph = ts.width + 64, ts.height + 26
    im = Image.new('RGBA', (pw, ph), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, pw - 1, ph - 1), 26, fill=(8, 10, 20, 205))
    im.alpha_composite(ts, (32, 13))
    _cap[i] = im
    return im

CAP_WIN = []
for i, o in enumerate(TIM):
    nxt = TIM[i + 1]['start'] if i + 1 < len(TIM) else o['end'] + 0.6
    end = nxt if nxt - o['end'] < 1.2 else o['end'] + 0.4
    CAP_WIN.append((o['start'] - 0.05, end))
def caption_at(t):
    import bisect
    k = bisect.bisect_right([a for a, _ in CAP_WIN], t) - 1
    if k >= 0 and t < CAP_WIN[k][1]: return k, CAP_WIN[k][0]
    return None, None

FACE_EMO = [(tref(fe['at']), fe['e']) for fe in SPEC.get('face_emoji', [])]

_np_cache = {}
def blend(out, im, sid, cx, cy):
    k = sid
    if k not in _np_cache:
        a = np.asarray(im).astype(np.float32)
        _np_cache[k] = (a[..., :3] * (a[..., 3:] / 255), 1 - a[..., 3:] / 255)
        if len(_np_cache) > 3000: _np_cache.clear()
    pre, inv = _np_cache[k]
    h, w = inv.shape[:2]
    x, y = int(cx - w / 2), int(cy - h / 2)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0: return
    reg = out[y0:y1, x0:x1].astype(np.float32)
    out[y0:y1, x0:x1] = (reg * inv[y0 - y:y1 - y, x0 - x:x1 - x] + pre[y0 - y:y1 - y, x0 - x:x1 - x]).astype(np.uint8)

def overlays(out, t):
    for t0, e in FACE_EMO:
        if t0 <= t <= t0 + 1.4:
            sc = back(prog(t, t0, 0.4)); a = 1 - prog(t, t0 + 1.1, 0.3)
            if sc > 0.02 and a > 0.02:
                spr = emoji_sprite(e, 120)
                blend(out, tx(spr, ('fe', e), sc, a), ('fe', e, round(sc, 2), round(a, 2)), 150, (VIS_Y if AUDIO_ONLY else TOPH + 210) - 30 * prog(t, t0, 1.4))
    i, t0 = caption_at(t)
    if i is not None and PRO:
        wt = word_times(i); k = sum(1 for x in wt if t >= x - 0.03)
        a = prog(t, t0, 0.12)
        blend(out, tx(caption_sprite_pro(i, k), ('capp', i, k), 1, a), ('capp', i, k, round(a, 2)), W / 2, CAP_Y)
    elif i is not None:
        sc = 0.85 + 0.15 * back(prog(t, t0, 0.22)); a = prog(t, t0, 0.08)
        blend(out, tx(caption_sprite(i), ('cap', i), sc, a), ('cap', i, round(sc, 2), round(a, 2)), W / 2, CAP_Y)

# ------------------------------------------------------------------ face panel via ffmpeg
dw, dh = info['width'], info['height']
s_ = min((W - 120) / dw, (PANEL_H - 50) / dh)
CW, CH = int(dw * s_ / 2) * 2, int(dh * s_ / 2) * 2
CX = (W - CW) // 2
CY = 30 if CH > PANEL_H - 120 else (PANEL_H - CH) // 2
PUNCH = [(tref(p[0]), tref(p[1])) for p in SPEC.get('punch', [])]
ZAMP = float(SPEC.get('punch_amount', 0.08))

def ensure_assets():
    load_vis()
    if AUDIO_ONLY or os.path.exists(J('_mask.png')): return
    m = Image.new('L', (CW, CH), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, CW - 1, CH - 1), 34, fill=255); m.save(J('_mask.png'))
    sh = Image.new('RGBA', (W, PANEL_H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((CX, CY + 10, CX + CW, CY + CH + 10), 40, fill=(0, 0, 0, 150))
    sh = sh.filter(ImageFilter.GaussianBlur(22))
    ImageDraw.Draw(sh).rounded_rectangle((CX - 1, CY - 1, CX + CW, CY + CH), 35, outline=(255, 255, 255, 60), width=2)
    sh.save(J('_frame.png'))

PREROLL = 0.5  # decode a little earlier and drop it: the first frames out of a seek can be blank
def face_cmd(start, dur):
    pre = min(PREROLL, start)
    off = f'(t+{start - pre:.4f})'
    terms = [f'clip(({off}-{a:.3f})/0.18,0,1)*clip(({b + 0.2:.3f}-{off})/0.2,0,1)' for a, b in PUNCH if b + 0.3 >= start and a <= start + dur]
    Z = f'(1+{ZAMP}*min(1,{"+".join(terms)}))' if terms else '1'
    fast = ['-skip_loop_filter', 'all'] if info['codec'] in ('hevc', 'h264') else []
    grade = SPEC.get('grade', 'eq=contrast=1.06:saturation=1.15:gamma=0.97')
    # blurred fill is recomputed at 5 fps (invisible difference, ~3x cheaper); card path runs at full fps
    fg = (f"[0:v]scale={CW}:{CH}:flags=fast_bilinear,fps={FPS},{grade},split=2[a][b];"
          f"[a]fps=5,scale=108:104:force_original_aspect_ratio=increase,crop=108:104,boxblur=4:1,scale={W}:{PANEL_H}:flags=bilinear,"
          f"colorchannelmixer=rr=0.45:gg=0.45:bb=0.5,format=rgba[bgs];[bgs][2:v]overlay=0:0:shortest=1:format=rgb,fps={FPS}[bg2];"
          f"[b]scale=w='2*trunc({CW}*{Z}/2)':h='2*trunc({CH}*{Z}/2)':eval=frame:flags=bilinear,crop={CW}:{CH}:(iw-{CW})/2:(ih-{CH})*0.42,format=rgba[c0];"
          f"[1:v]format=gray[m];[c0][m]alphamerge[c];[bg2][c]overlay={CX}:{CY}:shortest=1:format=rgb,format=rgb24")
    return ['ffmpeg', '-v', 'error'] + fast + ['-ss', f'{start - pre:.4f}', '-t', f'{dur + pre + 0.5:.4f}', '-i', info['video'],
            '-loop', '1', '-i', J('_mask.png'), '-loop', '1', '-i', J('_frame.png'), '-filter_complex', fg,
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']

def face_frames(start, dur, n, quiet=False):
    if AUDIO_ONLY:
        for _ in range(n): yield None
        return
    p = subprocess.Popen(face_cmd(start, dur), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL if quiet else None)
    size = W * PANEL_H * 3; last = None
    skip = int(round(min(PREROLL, start) * FPS))
    for _ in range(skip): p.stdout.read(size)
    for _ in range(n):
        b = p.stdout.read(size)
        if len(b) == size: last = np.frombuffer(b, np.uint8).reshape(PANEL_H, W, 3)
        yield last if last is not None else np.zeros((PANEL_H, W, 3), np.uint8)
    p.stdout.close(); p.kill(); p.wait()

# ---- audio visualizer (audio mode): bars driven by the voice, precomputed per frame
vis = SPEC.get('visualizer', AUDIO_ONLY)
VIS = None
VIS_ON = bool(vis) and info.get('has_audio', True)
if VIS_ON:
    vis = vis if isinstance(vis, dict) else {}
    VIS_Y = int(vis.get('y', 1235)); VIS_N = int(vis.get('bars', 26)); VIS_C = np.array(col(vis.get('color', 'cyan'))[:3], np.float32)
    VIS_H = int(vis.get('height', 90))
else:
    VIS_Y = 1235
def load_vis():
    global VIS
    if not VIS_ON or VIS is not None: return
    SR = 16000; hop = SR // FPS
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', info['video'], '-vn', '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'], capture_output=True).stdout
    y = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    nf = len(y) // hop + 1
    y = np.pad(y, (0, nf * hop + 1024 - len(y)))
    fr = np.lib.stride_tricks.sliding_window_view(y, 1024)[::hop][:nf] * np.hanning(1024)
    mag = np.abs(np.fft.rfft(fr, axis=1))
    edges = np.geomspace(4, 300, VIS_N + 1).astype(int)       # ~60 Hz .. 4.7 kHz, log spaced
    bands = np.stack([mag[:, a:max(a + 1, b)].mean(1) for a, b in zip(edges[:-1], edges[1:])], 1)
    bands = np.log1p(bands * 20); bands /= (np.percentile(bands, 97) + 1e-6)
    sm = np.zeros_like(bands)
    for i in range(1, len(bands)):                               # fast attack, slow release
        sm[i] = np.maximum(bands[i], sm[i - 1] * 0.82)
    order = np.argsort(np.abs(np.arange(VIS_N) - (VIS_N - 1) / 2))  # loudest bands in the middle
    VIS = np.clip(sm[:, np.argsort(order)], 0, 1.2)

def draw_vis(out, t):
    fi = min(len(VIS) - 1, max(0, int(t * FPS)))
    bw, gap = 12, 9
    x0 = (W - (VIS_N * (bw + gap) - gap)) // 2
    for k, v in enumerate(VIS[fi]):
        hh = int(6 + VIS_H * v)
        x = x0 + k * (bw + gap)
        reg = out[VIS_Y - hh // 2:VIS_Y + hh // 2, x:x + bw]
        out[VIS_Y - hh // 2:VIS_Y + hh // 2, x:x + bw] = (reg * 0.15 + VIS_C * 0.85).astype(np.uint8)

def zoom_at(t):
    z = 0.0
    for a, b in PUNCH:
        if a <= t <= b + 0.2: z = max(z, ease(prog(t, a, 0.18)) * (1 - ease(prog(t, b, 0.2))))
    return 1 + ZAMP * 0.6 * z

def compose(face, t, state):
    k = top_key(t)
    if k != state.get('k'):
        state['k'] = k; state['top'] = top_panel(t); state['renders'] = state.get('renders', 0) + 1
    out = np.empty((H, W, 3), np.uint8)
    if AUDIO_ONLY and PRO:
        z = 1 + float(SPEC.get('drift', 0.035)) * (t - T0) / max(1, T1 - T0) + 0.02 * (zoom_at(t) - 1) / max(1e-6, ZAMP * 0.6)
        cw, ch = W / z, H / z; cx, cy = 540, 820
        x0 = clamp(cx - cw / 2, 0, W - cw); y0 = clamp(cy - ch / 2, 0, H - ch)
        im = Image.fromarray(state['top']).resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
        out[:] = np.asarray(im)
    elif AUDIO_ONLY:
        z = zoom_at(t)
        if z > 1.002:   # punch-in = gentle zoom of the whole scene around its centre
            cw, ch = W / z, 1180 / z; cx, cy = 540, 640
            im = Image.fromarray(state['top']).crop((int(cx - cw / 2), int(cy - ch / 2) + 0, int(cx + cw / 2), int(cy + ch / 2)))
            out[:] = state['top']
            out[50:1230] = np.asarray(im.resize((W, 1180), Image.BILINEAR))
        else:
            out[:] = state['top']
    else:
        out[:TOPH] = state['top']
        out[TOPH:] = face
    if VIS is not None: draw_vis(out, t)
    overlays(out, t)
    return out

# ------------------------------------------------------------------ modes
def segments():
    per = SEG_SEC * FPS
    return [(i, i * per, min(NFR, (i + 1) * per)) for i in range((NFR + per - 1) // per)]

def run():
    ensure_assets()
    os.makedirs(J('segs'), exist_ok=True)
    segs = segments(); t_start = time.time(); frames_done = 0
    lock = J('render.lock')
    open(lock, 'w').write(str(os.getpid()))
    try:
        for i, f0, f1 in segs:
            outp = J(f'segs/seg_{i:04d}.mp4')
            if os.path.exists(outp): continue
            tmp = outp + '.part.mp4'
            enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                                    ] + (['-vf', f"noise=alls={SPEC.get('grain', 0)}:allf=t"] if PRO and SPEC.get('grain', 0) else []) + [
                                    '-c:v', 'libx264', '-preset', SPEC.get('x264_preset', 'superfast'), '-crf', str(SPEC.get('crf', 21)),
                                    '-pix_fmt', 'yuv420p', '-g', '60', tmp], stdin=subprocess.PIPE)
            state = {}
            ts = T0 + f0 / FPS
            for k, face in enumerate(face_frames(ts, (f1 - f0) / FPS, f1 - f0)):
                enc.stdin.write(compose(face, T0 + (f0 + k) / FPS, state).tobytes())
            enc.stdin.close(); enc.wait()
            os.replace(tmp, outp)
            frames_done += f1 - f0
            done = len(glob.glob(J('segs/seg_*.mp4'))) - len(glob.glob(J('segs/*.part.mp4')))
            el = time.time() - t_start; fps = frames_done / el
            remaining = sum(b - a for j, a, b in segs if not os.path.exists(J(f'segs/seg_{j:04d}.mp4')))
            pr = dict(done=done, total=len(segs), fps=round(fps, 1), eta_s=int(remaining / max(fps, 0.1)), graphics_redraws=state.get('renders'))
            json.dump(pr, open(J('progress.json'), 'w'))
            print('progress', pr, flush=True)
    finally:
        if os.path.exists(lock): os.remove(lock)
    print('RENDER COMPLETE', flush=True)

def sfx_track(n):
    SR = 48000; out = np.zeros(n)
    rng = np.random.default_rng(1)
    def add(sig, t, g):
        i = int((t - T0) * SR)
        if i < 0 or i >= n: return
        j = min(n, i + len(sig)); out[i:j] += sig[:j - i] * g
    tp = np.arange(int(0.09 * SR)) / SR
    pop = np.sin(2 * np.pi * np.cumsum(500 + 700 * tp / 0.09) / SR) * np.exp(-tp * 45)
    tw = np.arange(int(0.45 * SR)) / SR
    x = rng.standard_normal(len(tw)); X = np.fft.rfft(x); fr = np.fft.rfftfreq(len(x), 1 / SR)
    whoosh = np.fft.irfft(X * np.exp(-((fr - 1200) / 900) ** 2), len(x)); whoosh = whoosh / (np.abs(whoosh).max() + 1e-9) * np.sin(np.pi * tw / 0.45) ** 2
    th = np.arange(int(0.25 * SR)) / SR
    thud = np.sin(2 * np.pi * (90 * th - 60 * th * th)) * np.exp(-th * 18)
    if PRO:
        tw2 = np.arange(int(0.9 * SR)) / SR
        x2 = rng.standard_normal(len(tw2)); X2 = np.fft.rfft(x2); f2 = np.fft.rfftfreq(len(x2), 1 / SR)
        swell = np.fft.irfft(X2 * np.exp(-((f2 - 500) / 450) ** 2), len(x2)); swell /= np.abs(swell).max() + 1e-9
        swell *= (tw2 / 0.9) ** 2 * np.exp(-np.maximum(0, tw2 - 0.75) * 30)
        th2 = np.arange(int(0.7 * SR)) / SR
        tone = (np.sin(2 * np.pi * 110 * th2) + 0.4 * np.sin(2 * np.pi * 220 * th2)) * np.exp(-th2 * 5) * np.minimum(1, th2 / 0.01)
        for sc in SCENES[1:]: add(swell, sc.start - 0.8, 0.10)
        for sc in SCENES:
            for e in sc.els:
                if e.type == 'number': add(tone, e.at, 0.16)
        for e in STAGE:
            if e.type == 'rings':
                for r in e.rev: add(tone, r['at'], 0.10)
        return np.clip(out, -1, 1)
    for sc in SCENES[1:]: add(whoosh, sc.start - 0.15, 0.3)
    last = -9
    pops = sorted([e.at for sc in SCENES for e in sc.els if e.type in ('emoji', 'pill', 'box', 'card', 'db', 'image', 'note')]
                  + [i['at'] for sc in SCENES for e in sc.els if e.type == 'timeline' for i in e.items]
                  + [q['at'] for sc in SCENES for e in sc.els if e.type == 'map' for q in e.pins])
    tc = np.arange(int(0.025 * SR)) / SR
    click = rng.standard_normal(len(tc)) * np.exp(-tc * 260)
    for sc in SCENES:
        for e in sc.els:
            if e.type == 'text' and e.anim == 'type':
                n = int(e.tdur() / 0.055)
                for k in range(n): add(click * (0.6 + 0.4 * rng.random()), e.at + k * 0.055, 0.12)
    for t in pops:
        if t - last >= 0.2: add(pop, t, 0.2); last = t
    for sc in SCENES:
        for e in sc.els:
            for st in e.states:
                if st.get('shake'): add(thud, st['at'], 0.5)
            if e.type == 'strike': add(thud, e.at, 0.5)
    if CTA: add(pop, CTA.at, 0.2)
    return np.clip(out, -1, 1)

def finish(outp):
    segs = segments()
    miss = [i for i, _, _ in segs if not os.path.exists(J(f'segs/seg_{i:04d}.mp4'))]
    if miss: sys.exit(f'missing segments {miss}: run --run first')
    with open(J('segs/list.txt'), 'w') as f:
        for i, _, _ in segs: f.write(f"file 'seg_{i:04d}.mp4'\n")
    dur = NFR / FPS; SR = 48000; n = int(dur * SR)
    import wave
    sfx = sfx_track(n) if SPEC.get('sfx', True) else np.zeros(n)
    with wave.open(J('_sfx.wav'), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((sfx * 32767).astype(np.int16).tobytes())
    if info['has_audio']:
        chain = (f"[0:a]highpass=f=80,afftdn=nf=-25,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,"
                 f"loudnorm=I=-14:TP=-1.5:LRA=7,afade=t=in:d=0.12,afade=t=out:st={max(0, dur - 0.5):.2f}:d=0.5,aresample={SR}[v];"
                 f"[1:a]aresample={SR}[s];[v][s]amix=inputs=2:weights=1 0.9:normalize=0,alimiter=limit=0.93[a]")
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{T0:.4f}', '-t', f'{dur:.4f}', '-i', info['video'], '-i', J('_sfx.wav'),
                        '-filter_complex', chain, '-map', '[a]', '-ac', '2', '-ar', str(SR), J('_audio.wav')], check=True)
    else:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', J('_sfx.wav'), '-ac', '2', J('_audio.wav')], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', J('segs/list.txt'), '-i', J('_audio.wav'),
                    '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', outp], check=True)
    print('FINAL', outp, f'{dur:.1f}s')

def check():
    print(f"mode: {'AUDIO -> full 1080x1920 animation' if AUDIO_ONLY else 'VIDEO -> graphics top + face card bottom'}")
    print(f'trim {T0:.2f}-{T1:.2f}s ({T1 - T0:.1f}s, {NFR} frames, {len(segments())} segments)')
    print(f'card {CW}x{CH} at ({CX},{CY}); {len(PUNCH)} punch-ins; {len(FACE_EMO)} face emojis')
    for i, sc in enumerate(SCENES):
        print(f'scene {i}: {sc.start:6.2f}-{min(sc.end, T1):6.2f}  ' + ', '.join(f"{e.type}@{e.at:.1f}" for e in sc.els))
    for sc in SCENES:
        for e in sc.els:
            if e.at > sc.end + 0.01: print(f'  WARNING {e.type} at {e.at:.2f} appears after its scene ended ({sc.end:.2f})')
            lo_, hi_ = (220, 1160) if AUDIO_ONLY else (150, 860)
            if hasattr(e, 'y') and e.type not in ('flow', 'strike') and not (lo_ <= e.y <= hi_): print(f'  WARNING {e.type} y={e.y} outside safe zone {lo_}-{hi_}')
    print('OK')

def preview(times):
    ensure_assets()
    ims = []
    for t in times:
        face = next(face_frames(t, 0.2, 1, quiet=True))
        im = Image.fromarray(compose(face, t, {}))
        ims.append(im.resize((360, 640)))
    cols = min(4, len(ims)); rows = (len(ims) + cols - 1) // cols
    sheet = Image.new('RGB', (360 * cols, 640 * rows))
    for k, im in enumerate(ims): sheet.paste(im, ((k % cols) * 360, (k // cols) * 640))
    sheet.save(J('preview_sheet.jpg'), quality=85)
    print('preview ->', J('preview_sheet.jpg'))

if __name__ == '__main__':
    mode = sys.argv[2] if len(sys.argv) > 2 else '--check'
    if mode == '--check': check()
    elif mode == '--preview': preview([float(x) for x in sys.argv[3:]])
    elif mode == '--run': run()
    elif mode == '--finish': finish(sys.argv[3])
    else: print(__doc__)
