"""Sprite-swap animator: mascot + take -> 1080x1920 mp4.

Every frame: the mouth cue at that time picks the mouth sprite, trigger words swap the pose (and eyes),
and blinks, breathing, a loudness bounce, spring-loaded parts (ears, tails, antennae) and camera punch-ins
keep the character alive. PIL composites, ffmpeg encodes, all CPU cores render.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from multiprocessing import Pool
from typing import List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import pack, procedural
from .procedural import rgba

FPS = 30
FW, FH = 1080, 1920
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def spring(t, t0, amp=1.0, freq=2.4, damp=5.5):
    """Damped spring kick that starts at t0 (0 before)."""
    if t < t0:
        return 0.0
    x = t - t0
    return amp * math.exp(-damp * x) * math.sin(2 * math.pi * freq * x)


class Scene:
    def __init__(self, mascot_name: str, take_dir: str, beats: Optional[list] = None):
        self.m = pack.load(mascot_name)
        self.take_dir = take_dir
        tk = json.load(open(os.path.join(take_dir, "take.json")))
        self.cues = tk["cues"]
        self.words = tk["words"]
        self.env_arr = np.array(tk["env"], dtype=float)
        self.env_fps = float(tk["env_fps"])
        self.dur = float(tk["duration"])
        self.audio = os.path.join(take_dir, tk["audio"])
        m = self.m
        self.k = m.scale
        self.sw, self.sh = int(m.canvas[0] * self.k), int(m.canvas[1] * self.k)
        self.feet = (m.feet[0] * self.k, m.feet[1] * self.k)
        self.face = (m.face[0] * self.k, m.face[1] * self.k)
        self.beats = sorted(beats) if beats is not None else self.auto_beats()
        self.blinks = self._blinks()
        self._spr = {}
        self._bg = None
        st = m.style
        self.cap_font = ImageFont.truetype(os.path.join(FONTS, "LuckiestGuy-Regular.ttf"), st["caption_size"])
        self.groups = self._groups(st["caption_words"])
        top = min(int(m.place[1] - (m.feet[1] - m.face[1]) * self.k + 110), 1200)   # just under the chin
        self.card_box = tuple(st["card_box"]) if st["card_box"] else (60, top, FW - 60, top + 340)
        self.card_list = self._load_cards()

    # ── timing ──────────────────────────────────────────────────────────────

    def auto_beats(self):
        """(start, end, pose, eyes, punch): wave hello, react to trigger words, wave goodbye."""
        b = [(0.0, 1.0, "wave", None, False)]
        for w in self.words:
            key = w["word"].strip(",.!?\"").lower()
            if key in self.m.triggers:
                pose, eyes, dur, punch = self.m.triggers[key]
                b.append((w["start"] - 0.05, w["start"] + dur, pose, eyes, punch))
        b.append((max(0.0, self.dur - 1.0), self.dur + 1, "wave", None, False))
        return sorted(b)

    def word_t(self, text: str, after: float = 0.0) -> float:
        for w in self.words:
            if w["start"] >= after - 1e-6 and w["word"].strip(",.!?\"").lower() == text.lower():
                return w["start"]
        raise KeyError(text)

    def env(self, t):
        i = t * self.env_fps
        a = self.env_arr
        i0 = int(max(0, min(len(a) - 1, math.floor(i))))
        i1 = min(len(a) - 1, i0 + 1)
        f = i - math.floor(i)
        return float(a[i0] * (1 - f) + a[i1] * f)

    def env_smooth(self, t, width=0.12):
        return sum(self.env(t - width + k * width / 4) for k in range(9)) / 9

    def mouth_at(self, t):
        for c in self.cues:
            if c["start"] <= t < c["end"]:
                return c["value"]
        return "X"

    def beat_at(self, t):
        cur = None
        for b in self.beats:
            if b[0] <= t < b[1]:
                cur = b
        return cur

    def _blinks(self):
        rng = np.random.default_rng(7)
        t, out = 1.3, []
        while t < self.dur + 1:
            out.append(t)
            if rng.random() < 0.18:
                out.append(t + 0.32)          # the odd double blink
            t += rng.uniform(2.4, 4.6)
        return out

    def blink(self, t):
        for b in self.blinks:
            d = t - b
            if 0 <= d < 0.05 or 0.15 <= d < 0.2:
                return "half"
            if 0.05 <= d < 0.15:
                return "closed"
        return None

    # ── sprites ─────────────────────────────────────────────────────────────

    def spr(self, name):
        if name not in self._spr:
            m = self.m
            if name.startswith("mouth_") and not m.sprite_mouths:
                if not m.mouth:
                    im = Image.new("RGBA", m.canvas, (0, 0, 0, 0))   # no mouth art and no MOUTH setting
                else:
                    im = procedural.mouth_layer(name[6:], m.mouth, m.canvas)
            elif name.startswith("eyes_") and not m.sprite_eyes:
                im = procedural.eyes_layer(name[5:], m.eyes, m.canvas) if m.eyes else Image.new("RGBA", m.canvas, (0, 0, 0, 0))
            elif name.startswith("eyes_") and not m.has(name):
                im = m.image("eyes_open")                          # happy / wide are optional
            elif name == "mouth_smile" and not m.has(name):
                im = m.image("mouth_X")
            else:
                im = m.image(name)
            if im.size != tuple(m.canvas):
                raise SystemExit(f"{name}.png is {im.size[0]}x{im.size[1]} but CANVAS is {m.canvas[0]}x{m.canvas[1]}. "
                                 "Export every layer at the same size (see mascots/_template/README.md).")
            self._spr[name] = im.resize((self.sw, self.sh), Image.LANCZOS)
        return self._spr[name]

    # ── backdrop + captions ─────────────────────────────────────────────────

    def background(self):
        if self._bg is not None:
            return self._bg
        st = self.m.style
        top, bot = np.array(rgba(st["background"][0])[:3], float), np.array(rgba(st["background"][1])[:3], float)
        y = np.linspace(0, 1, FH)[:, None, None]
        x = np.linspace(-1, 1, FW)[None, :, None]
        base = (top * (1 - y) + bot * y) * np.ones((1, FW, 1))
        glow = np.exp(-((x * 1.1) ** 2 + ((y - 0.6) * 2.2) ** 2))
        base = base + glow * np.array(rgba(st["glow"])[:3], float) * 0.45
        if st["dots"]:
            dots = np.zeros((FH, FW, 1))
            dots[::26, ::26] = 1
            base = base + dots * 9
        bg = Image.fromarray(np.clip(base, 0, 255).astype("uint8"))
        ring = Image.new("L", (FW, FH), 0)
        px, py = self.m.place
        ImageDraw.Draw(ring).ellipse((px - 360, py - 46, px + 360, py + 46), fill=120)
        ring = ring.filter(ImageFilter.GaussianBlur(26))
        bg.paste(Image.new("RGB", (FW, FH), rgba(st["glow"])[:3]), (0, 0), ring.point(lambda v: v // 3))
        self._bg = bg
        return bg

    def _groups(self, n):
        groups, cur = [], []
        for w in self.words:
            cur.append(w)
            if len(cur) == n or w["word"].endswith((",", ".", "!", "?")):
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        return groups

    def caption(self, fr, t):
        st = self.m.style
        if not st["captions"]:
            return
        g = next((g for g in self.groups if g[0]["start"] - 0.02 <= t < g[-1]["end"] + 0.12), None)
        if not g:
            return
        d = ImageDraw.Draw(fr)
        words = [w["word"].strip(",.\"").upper() for w in g]
        widths = [d.textlength(w + " ", font=self.cap_font) for w in words]
        x = FW / 2 - sum(widths) / 2
        accent = rgba(st["accent"])[:3]
        for w, wd, meta in zip(words, widths, g):
            on = meta["start"] <= t
            key = w.lower().strip("!?") in self.m.keywords
            dy = -10 * max(0.0, 1 - (t - meta["start"]) / 0.12) if on else 0
            col = (accent if key else (255, 255, 255)) if on else (255, 255, 255, 140)
            d.text((x, st["caption_y"] + dy), w, font=self.cap_font, fill=col, stroke_width=7, stroke_fill=(0, 0, 0))
            x += wd

    # ── info cards: title / stat / screenshot, frosted glass under the mascot ───
    # cards.json in the take folder: [{"at": "SnapStart" | 4.5, "dur": 2.2, "title": "...", "sub": "...", "image": "path.png"}]

    def _load_cards(self):
        p = os.path.join(self.take_dir, "cards.json")
        out = []
        for c in json.load(open(p)) if os.path.exists(p) else []:
            at = c["at"]
            try:
                t0 = float(at) if isinstance(at, (int, float)) else self.word_t(str(at), c.get("after", 0.0)) - 0.05
            except KeyError:
                heard = " ".join(w["word"] for w in self.words)
                print(f"  card skipped: the word '{at}' is not in the take. Whisper heard: {heard}")
                continue
            img = None
            if c.get("image"):
                path = c["image"] if os.path.isabs(c["image"]) else os.path.join(pack.ROOT, c["image"])
                if not os.path.exists(path):
                    raise SystemExit(f"card image not found: {path}")
                img = Image.open(path).convert("RGBA")
            card = dict(t0=t0, t1=t0 + c.get("dur", 2.2), title=c.get("title", ""), sub=c.get("sub", ""), img=img)
            card["layer"] = self._card_layer(card)
            out.append(card)
        return out

    @staticmethod
    def _wrap(d, text, font, max_w):
        lines, cur = [], ""
        for w in text.split():
            t = f"{cur} {w}".strip()
            if cur and d.textlength(t, font=font) > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = t
        return lines + [cur] if cur else lines

    def _card_layer(self, c):
        x0, y0, x1, y1 = self.card_box
        w, h = x1 - x0, y1 - y0
        lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        font = lambda s: ImageFont.truetype(os.path.join(FONTS, "Oswald-Bold.ttf"), s)
        pad, tx = 28, 28 + 30
        d.rounded_rectangle((0, 0, w - 1, h - 1), 36, outline=(255, 255, 255, 90), width=3)
        d.rounded_rectangle((pad, pad, pad + 10, h - pad), 5, fill=rgba(self.m.style["accent"]))
        title, sub = c["title"], c["sub"]
        label = 0
        if c["img"]:                                            # screenshot / logo, with the title as a label under it
            label = 84 if (title or sub) else 0
            box = (w - pad - tx, h - 2 * pad - label)
            im = c["img"].copy()
            im.thumbnail(box, Image.LANCZOS)
            m = Image.new("L", im.size, 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), 18, fill=255)
            lay.paste(im, (tx + (box[0] - im.width) // 2, pad), m)
            title, sub = title or sub, ""
        avail_h = h - 2 * pad - label - (64 if sub else 0)
        max_w = w - tx - pad
        for size in range(150 if not c["img"] else 54, 40, -4):   # biggest size that fits in <= 2 lines
            f = font(size)
            lines = self._wrap(d, title, f, max_w)
            if len(lines) <= 2 and len(lines) * size * 1.12 <= avail_h and all(d.textlength(l, font=f) <= max_w for l in lines):
                break
        lh = int(size * 1.12)
        block = len(lines) * lh + (64 if sub else 0)
        y = h - pad - label + (label - lh) // 2 if c["img"] else pad + (h - 2 * pad - block) // 2
        for l in lines:
            d.text((tx, y), l, font=f, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 120))
            y += lh
        if sub:
            d.text((tx, y + 14), sub, font=font(44), fill=(215, 220, 235, 255))
        return lay

    def cards(self, fr, t):
        for c in self.card_list:
            if not c["t0"] <= t < c["t1"] + 0.2:
                continue
            a_in = ease((t - c["t0"]) / 0.2)
            a = min(a_in, 1 - ease((t - c["t1"]) / 0.2))
            x0, y0, x1, y1 = self.card_box
            w, h = x1 - x0, y1 - y0
            y0 += int((1 - a_in) * 60)                          # slides up as it appears
            glass = Image.blend(fr.crop((x0, y0, x1, y0 + h)).filter(ImageFilter.GaussianBlur(18)),
                                Image.new("RGB", (w, h), (16, 20, 34)), 0.55)
            mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), 36, fill=int(255 * a))
            fr.paste(glass, (x0, y0), mask)
            lay = c["layer"].copy()
            lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a)))
            fr.paste(lay, (x0, y0), lay)

    # ── one frame ───────────────────────────────────────────────────────────

    def pose_mix(self, t):
        b = self.beat_at(t)
        pose = b[2] if b else "idle"
        if pose == "wave":
            pose = "wave_a" if int(t * 5) % 2 == 0 else "wave_b"
        start = b[0] if b else max([x[1] for x in self.beats if x[1] <= t] or [0.0])
        pb = self.beat_at(start - 0.01)
        prev = pb[2] if pb else "idle"
        if prev == "wave":
            prev = "wave_a"
        return pose, prev, ease((t - start) / 0.1), (b[3] if b else None), start, bool(b and b[4])

    def character(self, t):
        m = self.m
        pose, prev, blend, eyes_override, start, punch = self.pose_mix(t)
        lay = Image.new("RGBA", (self.sw, self.sh), (0, 0, 0, 0))
        e = self.env_smooth(t)
        kick = spring(t, start, amp=1, freq=2.2, damp=4.0)

        def parts(behind):
            for i, p in enumerate(m.parts):
                if bool(p.get("behind", True)) != behind:
                    continue
                side = p.get("side", -1 if i % 2 == 0 else 1)
                ang = p.get("sway", 2.2) * math.sin(2 * math.pi * t / 2.6 + side) + side * p.get("kick", 9) * kick \
                    + side * p.get("talk", 3.5) * e
                piv = (p["pivot"][0] * self.k, p["pivot"][1] * self.k)
                lay.alpha_composite(self.spr(p["sprite"]).rotate(ang, resample=Image.BICUBIC, center=piv))

        parts(True)
        body = self.spr(m.pose(pose))
        if blend < 1 and m.pose(prev) != m.pose(pose):
            body = Image.blend(self.spr(m.pose(prev)), body, blend)
        lay.alpha_composite(body)

        eyes = self.blink(t) or eyes_override or "open"
        if eyes_override == "happy" and t - start > 0.9 and not self.blink(t):
            eyes = "open"
        sacc = int(3 * math.sin(t * 1.7) * (math.sin(t * 0.37) > 0.6)) if m.sprite_eyes else 0
        look = 14 if (pose == "point" and m.sprite_eyes) else 0
        lay.alpha_composite(self.spr(f"eyes_{eyes}"), (look + sacc, 0))

        mo = self.mouth_at(t)
        if mo == "X" and pose in m.smile_poses:
            mo = "smile"
        lay.alpha_composite(self.spr(f"mouth_{mo}"))
        parts(False)
        return lay, start, punch

    def frame(self, t, overlays=True):
        lay, start, punch = self.character(t)
        e = self.env_smooth(t)
        pop = spring(t, start, amp=0.06, freq=2.6, damp=6.0)
        sx = 1 + 0.012 * e - pop * 0.5
        sy = 1 + 0.010 * math.sin(2 * math.pi * t / 2.8) - 0.012 * e + pop
        rot = 1.6 * math.sin(2 * math.pi * t / 5.3) + 2.2 * spring(t, start, amp=1, freq=1.8, damp=4.5)
        lift = -26 * e - 40 * max(0.0, spring(t, start, amp=1, freq=2.0, damp=5.0))
        lay = lay.resize((int(self.sw * sx), int(self.sh * sy)), Image.BICUBIC)
        fx, fy = self.feet[0] * sx, self.feet[1] * sy
        lay = lay.rotate(rot, resample=Image.BICUBIC, center=(fx, fy))
        fr = self.background().copy()
        px, py = self.m.place
        fr.paste(lay, (int(px - fx), int(py - fy + lift)), lay)

        z = 1.0 + 0.02 * math.sin(2 * math.pi * t / 9)
        if punch:
            z += 0.12 * ease((t - start) / 0.12) * (1 - 0.35 * ease((t - start - 0.4) / 0.8))
        if z > 1.001:
            cx, cy = px, py - (self.feet[1] - self.face[1]) * sy
            cw, ch = FW / z, FH / z
            x0 = min(max(0, cx - cw / 2), FW - cw)
            y0 = min(max(0, cy - ch * 0.42), FH - ch)
            fr = fr.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((FW, FH), Image.BICUBIC)
        if overlays:
            self.caption(fr, t)
            self.cards(fr, t)
        return fr


# ── rendering (one Scene per worker process) ────────────────────────────────

_W = {}


def _init(mascot, take_dir, beats):
    _W["s"] = Scene(mascot, take_dir, beats)


def _one(i):
    return _W["s"].frame(i / FPS).convert("RGB").tobytes()


def loudnorm(audio: str, i=-14.0, tp=-1.5, lra=11.0) -> str:
    """ffmpeg audio filter that lands the mix on Instagram's ~-14 LUFS. Two passes (measure, then apply the exact gain):
    single-pass loudnorm drifts a full LU low on short clips."""
    base = f"loudnorm=I={i}:TP={tp}:LRA={lra}"
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", audio, "-af", base + ":print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True, check=True)
        m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
        return (f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
                f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    except Exception:
        return base


def render(mascot: str, take_dir: str, out: str, beats: Optional[list] = None, t0=0.0, t1=None) -> str:
    s = Scene(mascot, take_dir, beats)
    t1 = s.dur if t1 is None else t1
    n0, n1 = int(t0 * FPS), int(t1 * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{FW}x{FH}",
           "-r", str(FPS), "-i", "-", "-ss", f"{t0}", "-t", f"{t1 - t0}", "-i", s.audio,
           "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
           "-threads", "2", "-pix_fmt", "yuv420p", "-af", loudnorm(s.audio), "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    workers = max(1, min(int(os.environ.get("WORKERS", "0")) or 3, 8))   # 3 render processes by default so the laptop stays usable; WORKERS=8 to go faster
    with Pool(workers, initializer=_init, initargs=(mascot, take_dir, s.beats)) as pool:
        for k, buf in enumerate(pool.imap(_one, range(n0, n1), chunksize=8)):
            ff.stdin.write(buf)
            if k % (FPS * 5) == 0:
                print(f"  frame {k}/{n1 - n0}", flush=True)
    ff.stdin.close()
    ff.wait()
    return out


def contact_sheet(mascot: str, take_dir: str, out: str, times: List[float]) -> str:
    s = Scene(mascot, take_dir)
    tiles = [s.frame(t).resize((360, 640), Image.LANCZOS) for t in times]
    im = Image.new("RGB", (360 * len(tiles), 680), (15, 15, 18))
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(os.path.join(FONTS, "Oswald-Bold.ttf"), 22)
    for i, (t, tile) in enumerate(zip(times, tiles)):
        im.paste(tile, (i * 360, 40))
        d.text((i * 360 + 10, 8), f"{t:.2f}s", fill=(200, 200, 200), font=font)
    im.save(out)
    return out


def cover(mascot: str, take_dir: str, text: str, t: Optional[float] = None) -> List[str]:
    """Instagram cover: 2-3 huge words over the mascot's best expression. Instagram's profile grid crops the middle 3:4
    of the 9:16 frame (y 240..1680), so everything important sits inside that. Writes cover.png and cover_grid.png."""
    s = Scene(mascot, take_dir)
    if t is None:   # the loudest moment of the first 3 seconds = the most expressive mouth
        lo, hi = int(0.3 * s.env_fps), int(3 * s.env_fps)
        t = (lo + int(np.argmax(s.env_arr[lo:hi]))) / s.env_fps
    fr = s.frame(t, overlays=False)
    d = ImageDraw.Draw(fr)
    for size in range(240, 90, -8):
        f = ImageFont.truetype(os.path.join(FONTS, "LuckiestGuy-Regular.ttf"), size)
        lines = Scene._wrap(d, text.upper(), f, FW - 140)
        if len(lines) <= 3 and len(lines) * size * 1.05 <= 330:
            break
    y = 262 + (330 - len(lines) * size * 1.05) / 2
    accent = rgba(s.m.style["accent"])[:3]
    for i, l in enumerate(lines):
        x = (FW - d.textlength(l, font=f)) / 2
        d.text((x, y), l, font=f, fill=accent if i == len(lines) - 1 else (255, 255, 255), stroke_width=12, stroke_fill=(0, 0, 0))
        y += size * 1.05
    a, b = os.path.join(take_dir, "cover.png"), os.path.join(take_dir, "cover_grid.png")
    fr.save(a)
    fr.crop((0, 240, FW, 1680)).save(b)
    print(f"  frame at {t:.2f}s")
    return [a, b]
