"""Look A: black terminal reels. Big Anton headline, a real terminal / code panel revealed on the spoken words, a floating
mascot tile, karaoke captions, light SFX. Everything is drawn per frame with PIL and piped to ffmpeg.

    python make.py look NAME TAKE_DIR spec.json --stills 3 9 15     # preview frames, no render
    python make.py look NAME TAKE_DIR spec.json                     # render + mix + loudness

spec.json = {"keywords": ["npm", ...], "beats": [beat, ...]}; a beat starts on a spoken word (or seconds):
  {"at": "Dockerfile", "tile": "tr|tl", "head": [line, ...], "panel": {"title": "docker build", "lines": [pline, ...]}}
  line  = "TEXT" | {"text": "TEXT", "tone": "accent|ok|bad|ink", "size": 170} | {"count": [0, 6.4, 1, "s"], "tone": "bad", "size": 230}
  pline = {"t": "cmd|step|dim|result|code", "at": "word" | seconds-after-beat-start, ...}
    cmd    text                      typed after a prompt
    step   n, text, status, tone     "[3/4]  COPY . .            0.1s"   (tone ok|warn|bad|dim)
    dim    text
    result label, value, tone
    code   n, kw, rest, hl, note, states=[{"at":..., "hl":..., "note":...}]    hl = bad|ok|warn|None
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import wave
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import animate

W, H = 1080, 1920
FONTS = animate.FONTS
INK, ACCENT, OK, WARN, BAD, DIM = "#F2F4F8", "#FF5A1F", "#3FD27A", "#FFB020", "#FF5A1F", "#7C8594"
TONES = dict(ink=INK, accent=ACCENT, ok=OK, warn=WARN, bad=BAD, dim=DIM)
HL = dict(bad="#3B1D18", ok="#10301F", warn="#33280F")
HL_BAR = dict(bad=BAD, ok=OK, warn=WARN)
PANEL = (50, 720, 1030, 1400)
TILE = 310
SPOTS = dict(tr=(700, 200), tl=(70, 200), br=(700, 980))
_fonts = {}


def font(name, size):
    k = (name, int(size))
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(os.path.join(FONTS, name), int(size))
    return _fonts[k]


ANTON, MONO, MONOB = "Anton-Regular.ttf", "DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf"


def ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 4


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def text_alpha(im, xy, text, fnt, fill, alpha=1.0, anchor="la"):
    """Draws text with an opacity (PIL's own text has none)."""
    if alpha <= 0.01:
        return
    if alpha >= 0.99:
        ImageDraw.Draw(im).text(xy, text, font=fnt, fill=fill, anchor=anchor)
        return
    lay = Image.new("L", im.size, 0)
    ImageDraw.Draw(lay).text(xy, text, font=fnt, fill=int(255 * alpha), anchor=anchor)
    im.paste(Image.new("RGB", im.size, fill), (0, 0), lay)


class Look:
    def __init__(self, mascot, take_dir, spec):
        self.s = animate.Scene(mascot, take_dir)
        ms = spec.get("mascot_style")
        if ms:
            self.s.m.style = {**self.s.m.style, **ms}
        self.words, self.dur = self.s.words, self.s.dur
        self.crop = animate.tile_crop(mascot, take_dir, TILE)
        self.keywords = {norm(k) for k in spec.get("keywords", [])}
        self.bg = Image.new("RGB", (W, H), "#0B0B0D")
        self.beats, cursor = [], 0.0
        for b in spec["beats"]:
            t0 = self.at(b["at"], cursor)
            cursor = t0 + 0.4   # the next beat can reuse the same word later in the script
            self.beats.append(self.resolve(b, t0))
        for b, nxt in zip(self.beats, self.beats[1:] + [None]):
            b["t1"] = nxt["t0"] if nxt else self.dur + 1
        self._static()
        self.groups = self.s._groups(3)

    # ── timing ──────────────────────────────────────────────────────────────

    def at(self, ref, base):
        """A time: seconds after `base`, a spoken word ("Dockerfile"), or [word, nth] for its nth occurrence after `base`."""
        if isinstance(ref, (int, float)):
            return base + float(ref)
        word, nth = (ref, 1) if isinstance(ref, str) else ref
        for w in self.words:
            if w["start"] >= base - 0.06 and norm(w["word"]) == norm(word):
                nth -= 1
                if nth == 0:
                    return max(0.0, w["start"] - 0.05)
        print(f"  look: the word '{word}' was not found after {base:.1f}s: placed at that time instead")
        return base

    def resolve(self, b, t0):
        beat = dict(t0=t0, tile=b.get("tile", "tr"), head=[], lines=[], title=(b.get("panel") or {}).get("title", "docker build"), panel=bool(b.get("panel")))
        right = beat["tile"] == "tl"
        avail = W - 70 - 70 - (TILE + 40 if b.get("tile_beside", True) else 0)
        lines = [l if isinstance(l, dict) else {"text": l} for l in b["head"]]
        size = b.get("head_size", 170)
        while size > 60 and (sum(self._lh(l, size) for l in lines) > b.get("head_h", 500) or any(self._w(l, size) > avail for l in lines)):
            size -= 4
        y = 190
        for i, l in enumerate(lines):
            sz = l.get("size", size)
            beat["head"].append(dict(l, sz=sz, y=l.get("y", y), t=self.at(l["at"], t0) if "at" in l else t0 + 0.14 * i, right=right))
            y += self._lh(l, sz)
        if beat["panel"]:
            y = PANEL[1] + 100
            for ln in b["panel"]["lines"]:
                pitch = 76 if ln["t"] == "code" else 58
                if ln["t"] in ("dim", "result"):
                    y += 18
                st = [dict(s2, t=self.at(s2["at"], t0)) for s2 in ln.get("states", [])]
                beat["lines"].append(dict(ln, y=y, ts=self.at(ln.get("at", 0), t0), states=st))
                y += pitch + (18 if ln["t"] in ("dim", "result") else 0) + (20 if ln["t"] == "cmd" else 0)
        return beat

    def _lh(self, l, size):
        return int(l.get("size", size)) + 10

    def _w(self, l, size):
        t = l.get("text") or f"{l['count'][1]:.{l['count'][2]}f}{l['count'][3]}"
        return ImageDraw.Draw(self.bg).textlength(t, font=font(ANTON, l.get("size", size)))

    # ── static pieces ───────────────────────────────────────────────────────

    def _static(self):
        x0, y0, x1, y1 = PANEL
        card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((x0, y0 + 18, x1, y1 + 18), 30, fill=(0, 0, 0, 200))
        card.alpha_composite(sh.filter(ImageFilter.GaussianBlur(26)))
        ImageDraw.Draw(card).rounded_rectangle((x0, y0, x1, y1), 30, fill="#14161A", outline="#2A2E36", width=2)
        self.card = card
        m = Image.new("L", (TILE, TILE), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, TILE - 1, TILE - 1), 44, fill=255)
        self.tmask = m
        t = Image.new("RGBA", (TILE + 120, TILE + 120), (0, 0, 0, 0))
        ImageDraw.Draw(t).rounded_rectangle((60, 60 + 16, 60 + TILE, 60 + TILE + 16), 44, fill=(0, 0, 0, 170))
        self.tshadow = t.filter(ImageFilter.GaussianBlur(22))
        r = Image.new("RGBA", (TILE * 3, TILE * 3), (0, 0, 0, 0))
        ImageDraw.Draw(r).rounded_rectangle((0, 0, TILE * 3 - 1, TILE * 3 - 1), 44 * 3, outline="#FFFFFF", width=18)
        self.tring = r.resize((TILE, TILE), Image.LANCZOS)

    def beat_at(self, t):
        cur = self.beats[0]
        for b in self.beats:
            if b["t0"] <= t:
                cur = b
        return cur

    # ── one frame ───────────────────────────────────────────────────────────

    def frame(self, t, overlays=True):
        im = self.bg.copy()
        b = self.beat_at(t)
        self.headline(im, b, t)
        if b["panel"]:
            self.panel(im, b, t)
        self.tile(im, b, t)
        if overlays:
            self.caption(im, t)
        return im

    def headline(self, im, b, t):
        for l in b["head"]:
            a = ease_out((t - l["t"]) / 0.22)
            if a <= 0:
                continue
            col = TONES.get(l.get("tone", "ink"), INK)
            if l.get("count"):
                f0, f1, dec, suf = l["count"]
                k = smooth((t - l["t"] - 0.1) / l.get("dur", 1.5))
                txt = f"{f0 + (f1 - f0) * k:.{dec}f}{suf}"
                fixed = f"{f1:.{dec}f}{suf}"
            else:
                txt = fixed = l["text"]
            fnt = font(ANTON, l["sz"])
            wd = ImageDraw.Draw(im).textlength(fixed, font=fnt)
            x = (W - 70 - wd) if l["right"] else 70
            text_alpha(im, (x, l["y"] + (1 - a) * 50), txt, fnt, col, a)

    def tile(self, im, b, t):
        i = self.beats.index(b)
        prev = self.beats[i - 1] if i else b
        x0, y0 = SPOTS[prev["tile"]]
        x1, y1 = SPOTS[b["tile"]]
        k = smooth((t - b["t0"]) / 0.6) if i else 1.0
        x = x0 + (x1 - x0) * k + 6 * math.sin(2 * math.pi * t / 3.7)
        y = y0 + (y1 - y0) * k + 8 * math.sin(2 * math.pi * t / 2.9 + 1)
        fr = self.s.frame(t, overlays=False).crop((self.crop[0], self.crop[1], self.crop[0] + self.crop[2], self.crop[1] + self.crop[2]))
        fr = fr.resize((TILE, TILE), Image.LANCZOS)
        x, y = int(x), int(y)
        im.paste(self.tshadow, (x - 60, y - 60), self.tshadow)
        im.paste(fr, (x, y), self.tmask)
        im.paste(self.tring, (x, y), self.tring)

    def panel(self, im, b, t):
        im.paste(self.card, (0, 0), self.card)
        x0, y0, x1, _ = PANEL
        d = ImageDraw.Draw(im)
        for i, c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            d.ellipse((x0 + 34 + i * 40, y0 + 30, x0 + 58 + i * 40, y0 + 54), fill=c)
        d.text((x0 + 170, y0 + 28), b["title"], font=font(MONO, 26), fill=DIM)
        fm, fb, fc = font(MONO, 33), font(MONOB, 33), font(MONO, 38)
        for ln in b["lines"]:
            a = ease_out((t - ln["ts"]) / 0.18)
            if a <= 0:
                continue
            y = ln["y"] + (1 - a) * 12
            kind = ln["t"]
            if kind == "cmd":
                n = int(max(0, t - ln["ts"]) / 0.035)
                text_alpha(im, (x0 + 40, y), "$ ", fb, ACCENT)
                text_alpha(im, (x0 + 40 + d.textlength("$ ", font=fb), y), ln["text"][:n] + ("_" if n < len(ln["text"]) else ""), fb, INK)
            elif kind == "step":
                text_alpha(im, (x0 + 40, y), ln["n"] + " ", fm, DIM, a)
                text_alpha(im, (x0 + 40 + d.textlength(ln["n"] + " ", font=fm), y), ln["text"], fm, INK, a)
                st = ln.get("status", "")
                text_alpha(im, (x1 - 40 - d.textlength(st, font=fb), y), st, fb, TONES.get(ln.get("tone", "dim"), DIM), a)
            elif kind == "dim":
                text_alpha(im, (x0 + 40, y), ln["text"], fm, DIM, a)
            elif kind == "result":
                text_alpha(im, (x0 + 40, y), ln["label"] + " ", fb, DIM, a)
                text_alpha(im, (x0 + 40 + d.textlength(ln["label"] + " ", font=fb), y), ln["value"], fb, TONES.get(ln.get("tone", "bad"), BAD), a)
            elif kind == "code":
                hl, note = ln.get("hl"), ln.get("note")
                for s in ln["states"]:
                    if t >= s["t"]:
                        hl, note = s.get("hl", hl), s.get("note", note)
                if hl:
                    d.rectangle((x0 + 2, ln["y"] - 8, x1 - 2, ln["y"] + 54), fill=HL[hl])
                    d.rectangle((x0 + 2, ln["y"] - 8, x0 + 10, ln["y"] + 54), fill=HL_BAR[hl])
                text_alpha(im, (x0 + 40, y), str(ln["n"]), fc, "#6E7681", a)
                kw = ln["kw"] + " "
                text_alpha(im, (x0 + 110, y), kw, font(MONOB, 38), "#FF7B72", a)
                text_alpha(im, (x0 + 110 + d.textlength(kw, font=font(MONOB, 38)), y), ln.get("rest", ""), font(MONOB, 38), "#A5D6FF", a)
                if note:
                    col = HL_BAR.get(hl, DIM)
                    text_alpha(im, (x1 - 40 - d.textlength(note, font=font(MONO, 28)), y + 6), note, font(MONO, 28), col, a)

    def caption(self, im, t):
        g = next((g for g in self.groups if g[0]["start"] - 0.02 <= t < g[-1]["end"] + 0.12), None)
        if not g:
            return
        fnt = font(ANTON, 84)
        d = ImageDraw.Draw(im)
        words = [w["word"].strip(",.\"!?").upper() + " " for w in g]
        x = W / 2 - sum(d.textlength(w, font=fnt) for w in words) / 2
        for w, meta in zip(words, g):
            on = meta["start"] <= t
            col = ACCENT if norm(w) in self.keywords else INK
            text_alpha(im, (x, 1480 - (10 * max(0.0, 1 - (t - meta["start"]) / 0.12) if on else 0)), w, fnt, col, 1.0 if on else 0.45)
            x += d.textlength(w, font=fnt)

    # ── sound ───────────────────────────────────────────────────────────────

    def sfx(self):
        sr = 44100
        out = np.zeros(int((self.dur + 1) * sr), dtype=np.float32)
        rng = np.random.default_rng(3)

        def put(t, y):
            i = int(t * sr)
            out[i:i + len(y)] += y[: max(0, len(out) - i)]
        for b in self.beats:
            for l in b["head"]:
                n = int(0.28 * sr); k = np.arange(n) / sr
                noise = rng.standard_normal(n); lp = np.convolve(noise, np.ones(40) / 40, mode="same")
                put(l["t"], (lp * np.sin(np.pi * np.minimum(k / 0.28, 1)) * 0.5).astype(np.float32))
                if l.get("count"):
                    k2 = np.arange(int(0.35 * sr)) / sr
                    put(l["t"] + 0.1 + l.get("dur", 1.5), (np.sin(2 * np.pi * 70 * k2) * np.exp(-k2 / 0.1) * 0.9).astype(np.float32))
            for ln in b["lines"]:
                k = np.arange(int(0.03 * sr)) / sr
                put(ln["ts"], (np.sin(2 * np.pi * 1700 * k) * np.exp(-k / 0.007) * 0.35).astype(np.float32))
        return out * 0.5


# ── rendering ───────────────────────────────────────────────────────────────

_L = {}


def _init(mascot, take_dir, spec):
    _L["l"] = Look(mascot, take_dir, spec)


def _one(i):
    return _L["l"].frame(i / animate.FPS).tobytes()


def stills(mascot, take_dir, spec, times, out):
    lk = Look(mascot, take_dir, spec)
    tiles = [lk.frame(t) for t in times]
    sheet = Image.new("RGB", (540 * len(tiles), 960), "#222")
    for i, im in enumerate(tiles):
        sheet.paste(im.resize((540, 960), Image.LANCZOS), (i * 540, 0))
    sheet.save(out)
    return out


def render(mascot, take_dir, spec, out):
    lk = Look(mascot, take_dir, spec)
    n = int(lk.dur * animate.FPS)
    voice = os.path.join(take_dir, "voice.wav")
    mix = os.path.join(take_dir, "mix.wav")
    with wave.open(voice) as w:   # voice + soft SFX
        sr, ch = w.getframerate(), w.getnchannels()
        v = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32).reshape(-1, ch).mean(axis=1) / 32768
    fx = lk.sfx()
    if sr != 44100:
        v = np.interp(np.arange(int(len(v) * 44100 / sr)) / 44100 * sr, np.arange(len(v)), v)
    m = np.zeros(max(len(v), len(fx)), dtype=np.float32)
    m[: len(v)] += v
    m[: len(fx)] += fx * 0.35
    m = np.clip(m[: int(n / animate.FPS * 44100)], -1, 1)   # exactly the video's length: no silent tail
    with wave.open(mix, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes((m * 32767).astype(np.int16).tobytes())
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(animate.FPS), "-i", "-",
           "-i", mix, "-map", "0:v", "-map", "1:a", "-af", animate.loudnorm(mix), "-ar", "44100", "-c:a", "aac", "-b:a", "192k",
           "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-threads", "2", "-pix_fmt", "yuv420p", "-shortest", "-movflags", "+faststart", out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    workers = max(1, min(int(os.environ.get("WORKERS", "0")) or 3, 8))
    with Pool(workers, initializer=_init, initargs=(mascot, take_dir, spec)) as pool:
        for k, buf in enumerate(pool.imap(_one, range(n), chunksize=8)):
            ff.stdin.write(buf)
            if k % (animate.FPS * 5) == 0:
                print(f"  frame {k}/{n}", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg failed while encoding the video")
    return out
