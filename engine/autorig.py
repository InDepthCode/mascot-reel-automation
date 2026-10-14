"""`python make.py create NAME --image pic.png`: any character picture -> a talking mascot.

1. Cut out the character (keeps transparency, removes a flat background, or uses rembg if installed).
2. Trim, size and pad it onto a sprite canvas -> sprites/pose_idle.png.
3. Claude looks at it on a pixel grid and finds the mouth, eyes, skin and line colours (structured output).
4. Claude checks its own work on a close-up of the rendered mouths and blinks, and nudges them (up to 3 rounds).
5. Writes mascot.py.

Steps 3-4 need an Anthropic API key (ANTHROPIC_API_KEY in .env, or `ant auth login`). Without one you get a
best-guess mascot.py and fix the numbers with `python make.py check NAME` + the grid.
"""
from __future__ import annotations

import base64
import io
import json
import os
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import pack, procedural
from .voice import load_env

MODEL = os.environ.get("MASCOT_CLAUDE_MODEL", "claude-opus-5-5")
TARGET_H = 1300   # character height on the sprite canvas
PAD = 70


# ── 1-2. cut out + normalise ────────────────────────────────────────────────

def cutout(src: Image.Image) -> Tuple[Image.Image, str]:
    im = src.convert("RGBA")
    a = np.asarray(im)[..., 3]
    if (a < 250).mean() > 0.02:
        return im, "kept the picture's transparency"
    rgb = np.asarray(im)[..., :3].astype(int)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    if np.abs(border - bg).max(axis=1).mean() < 18:            # flat background: flood it from the edges
        diff = np.abs(rgb - bg).max(axis=2)
        mask = _flood(diff < 34)
        alpha = np.where(mask, 0, 255).astype(np.uint8)
        out = np.dstack([rgb.astype(np.uint8), alpha])
        return _soften(Image.fromarray(out, "RGBA")), "removed the flat background"
    try:
        from rembg import remove   # pip install rembg (optional, ~170 MB model on first run)
        return remove(im), "removed the background with rembg"
    except ImportError:
        raise SystemExit("This picture has a busy background. Give it a transparent PNG (macOS: open it in Preview -> "
                         "Tools -> Remove Background, or right-click -> Quick Actions -> Remove Background), "
                         "or `pip install rembg` and run create again.")


def _flood(cand: np.ndarray) -> np.ndarray:
    """Pixels connected to the image border through background-coloured pixels (grown on a small copy)."""
    h, w = cand.shape
    k = max(1, max(h, w) // 700)
    small = cand[::k, ::k]
    seen = np.zeros_like(small)
    seen[0, :], seen[-1, :], seen[:, 0], seen[:, -1] = small[0, :], small[-1, :], small[:, 0], small[:, -1]
    while True:
        grown = seen.copy()
        grown[1:] |= seen[:-1]; grown[:-1] |= seen[1:]; grown[:, 1:] |= seen[:, :-1]; grown[:, :-1] |= seen[:, 1:]
        grown &= small
        if (grown == seen).all():
            break
        seen = grown
    big = np.asarray(Image.fromarray(seen.astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 0
    return big & cand


def _soften(im: Image.Image) -> Image.Image:
    from PIL import ImageFilter
    a = im.getchannel("A").filter(ImageFilter.GaussianBlur(0.8))
    im.putalpha(a)
    return im


def normalise(im: Image.Image) -> Tuple[Image.Image, dict]:
    box = im.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    if not box:
        raise SystemExit("The picture is empty after removing the background.")
    cropped_bottom = box[3] >= im.height - 2           # cut off at the bottom edge = bust / waist-up
    ch = im.crop(box)
    k = TARGET_H / ch.height
    ch = ch.resize((max(1, round(ch.width * k)), TARGET_H), Image.LANCZOS)
    W, H = ch.width + 2 * PAD, TARGET_H + PAD * (1 if cropped_bottom else 2)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.alpha_composite(ch, (PAD, PAD))
    feet = (W // 2, PAD + TARGET_H)
    scale = round(min(1.0, 1000 / ch.width, 1500 / TARGET_H), 3)
    place = (540, 1990 if cropped_bottom else 1872)
    return canvas, {"canvas": (W, H), "feet": feet, "scale": scale, "place": place, "bust": cropped_bottom}


# ── 3. Claude: find the face ─────────────────────────────────────────────────

RIG_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "short display name (use the character's name if it is written or obvious)"},
        "description": {"type": "string", "description": "one sentence: what the character looks like"},
        "mouth_x": {"type": "integer"}, "mouth_y": {"type": "integer"},
        "mouth_width": {"type": "integer", "description": "width of a wide-open talking mouth for this face, in px"},
        "has_drawn_mouth": {"type": "boolean"},
        "cover_width": {"type": "integer", "description": "width of a patch that fully hides the existing mouth (0 if none)"},
        "cover_height": {"type": "integer"},
        "eyes_visible": {"type": "boolean"},
        "left_eye_x": {"type": "integer"}, "left_eye_y": {"type": "integer"},
        "right_eye_x": {"type": "integer"}, "right_eye_y": {"type": "integer"},
        "eye_radius_x": {"type": "integer"}, "eye_radius_y": {"type": "integer"},
        "skin_hex": {"type": "string", "description": "#RRGGBB of the face right next to the mouth"},
        "line_hex": {"type": "string", "description": "#RRGGBB of the character's outline / ink"},
        "background_top_hex": {"type": "string"}, "background_bottom_hex": {"type": "string"},
        "glow_hex": {"type": "string"}, "accent_hex": {"type": "string"},
        "voice_description": {"type": "string", "description": "an ElevenLabs Voice Design prompt that fits the character"},
    },
    "required": ["name", "description", "mouth_x", "mouth_y", "mouth_width", "has_drawn_mouth", "cover_width",
                 "cover_height", "eyes_visible", "left_eye_x", "left_eye_y", "right_eye_x", "right_eye_y",
                 "eye_radius_x", "eye_radius_y", "skin_hex", "line_hex", "background_top_hex",
                 "background_bottom_hex", "glow_hex", "accent_hex", "voice_description"],
    "additionalProperties": False,
}

FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "looks_right": {"type": "boolean"},
        "mouth_dx": {"type": "integer"}, "mouth_dy": {"type": "integer"},
        "mouth_width_scale": {"type": "number"},
        "cover_scale": {"type": "number"},
        "eyes_dx": {"type": "integer"}, "eyes_dy": {"type": "integer"},
        "eye_radius_scale": {"type": "number"},
        "notes": {"type": "string"},
    },
    "required": ["looks_right", "mouth_dx", "mouth_dy", "mouth_width_scale", "cover_scale", "eyes_dx", "eyes_dy",
                 "eye_radius_scale", "notes"],
    "additionalProperties": False,
}


def _png_b64(im: Image.Image, max_side: int = 1400) -> str:
    im = im.convert("RGB")
    if max(im.size) > max_side:
        k = max_side / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def _client():
    load_env()
    try:
        import anthropic
    except ImportError:
        return None, "the anthropic package is not installed (pip install anthropic)"
    if int(anthropic.__version__.split(".")[0]) < 1:
        return None, f"anthropic {anthropic.__version__} is too old (needs 1.x on Python 3.10+: pip install -U anthropic)"
    try:
        c = anthropic.Anthropic()
        return c, None
    except Exception as e:   # no credentials anywhere
        return None, str(e).splitlines()[0]


def _ask(client, images, prompt: str, schema: dict) -> dict:
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _png_b64(i)}} for i in images]
    content.append({"type": "text", "text": prompt})
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": content}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined to read this image")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def grid_image(im: Image.Image) -> Image.Image:
    out = Image.new("RGBA", im.size, (128, 132, 140, 255))
    out.alpha_composite(im)
    d = ImageDraw.Draw(out)
    font = ImageFont.truetype(os.path.join(os.path.dirname(__file__), "fonts", "Oswald-Bold.ttf"), 22)
    W, H = im.size
    for x in range(0, W, 50):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 60 if x % 100 else 150))
        if x % 100 == 0:
            d.text((x + 3, 2), str(x), font=font, fill=(255, 235, 60), stroke_width=2, stroke_fill=(0, 0, 0))
    for y in range(0, H, 50):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 60 if y % 100 else 150))
        if y % 100 == 0:
            d.text((3, y + 2), str(y), font=font, fill=(255, 235, 60), stroke_width=2, stroke_fill=(0, 0, 0))
    return out


RIG_PROMPT = """This is a character that will become a talking, lip-synced cartoon mascot. The picture sits on a pixel
grid: the yellow numbers on the top and left edges are pixel coordinates ({w} x {h}). Give every position in those
coordinates.

Find:
- mouth_x, mouth_y: the centre of where the talking mouth should go (on the existing mouth if there is one).
- mouth_width: how wide the mouth should open when it says "AH", sized like a cartoon mouth on this face.
- has_drawn_mouth, cover_width, cover_height: if a mouth is already drawn, a patch size (in px, generous) that fully
  hides it so a new animated mouth can replace it. 0 x 0 if there is no visible mouth.
- the centre and radii of both eyes ("left" = the eye on the left side of the image). eyes_visible=false if they are
  hidden (sunglasses, covered, or too small to blink).
- skin_hex: the face colour right next to the mouth; line_hex: the outline colour (or a dark shade of the skin if the
  art has no outlines).
- background_top_hex / background_bottom_hex: a saturated, darkish video backdrop that makes this character pop
  (never white or pale); glow_hex: a light colour behind it; accent_hex: a caption highlight colour that fits.
- name, description, and a voice_description for designing a voice that suits the character.
Measure carefully against the grid lines."""

FIX_PROMPT = """Left: the character's face as drawn. Right, in order: the animated mouth at rest, the mouth wide open
("AH"), the mouth puckered ("OO"), and the eyes mid-blink, all drawn by the animation engine on top of the face.
Check them like an animator: the mouth should sit where a mouth belongs on this face, be a believable size, and the
original mouth must be completely hidden (no doubled lips or teeth). Blink lids should cover the eyes exactly.
If something is off, give the correction in pixels of the full-size picture (+x = right, +y = down) and scale factors
(1.0 = no change). If it all looks right, set looks_right=true and zeros / 1.0."""


def _face_box(cfg: dict, canvas: Tuple[int, int]) -> Tuple[int, int, int, int]:
    mx, my = cfg["mouth"]["at"]
    r = max(160, int(cfg["mouth"]["width"] * 2.2))
    if cfg.get("eyes"):
        ys = [cfg["eyes"]["left"][1], cfg["eyes"]["right"][1]]
        r = max(r, int((my - min(ys)) * 1.6))
    return (max(0, mx - r), max(0, my - int(r * 1.15)), min(canvas[0], mx + r), min(canvas[1], my + int(r * 0.85)))


def review_strip(base: Image.Image, cfg: dict) -> Image.Image:
    box = _face_box(cfg, base.size)
    tiles = [base.crop(box)]
    for mouth, eyes in (("X", "open"), ("D", "open"), ("F", "open"), ("X", "half")):
        im = base.copy()
        if cfg.get("eyes"):
            im.alpha_composite(procedural.eyes_layer(eyes, cfg["eyes"], base.size))
        im.alpha_composite(procedural.mouth_layer(mouth, cfg["mouth"], base.size))
        tiles.append(im.crop(box))
    w, h = tiles[0].size
    strip = Image.new("RGBA", (w * len(tiles) + 12 * (len(tiles) - 1), h), (128, 132, 140, 255))
    for i, t in enumerate(tiles):
        strip.alpha_composite(t, (i * (w + 12), 0))
    return strip


def sample_skin(im: Image.Image, at, width) -> Optional[str]:
    """Most common colour in a ring around the mouth (ignores ink lines and the mouth itself)."""
    a = np.asarray(im.convert("RGBA")).astype(int)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - at[0], (yy - at[1]) * 1.3)
    ring = (d > width * 0.75) & (d < width * 1.15) & (a[..., 3] > 240)
    px = a[ring][:, :3]
    if len(px) < 30:
        return None
    px = px[px.mean(axis=1) > 70]
    if len(px) < 30:
        return None
    q = px // 16
    keys, counts = np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2], return_counts=True)
    top = keys[counts.argmax()]
    sel = px[(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]) == top]
    r, g, b = sel.mean(axis=0).astype(int)
    return f"#{r:02X}{g:02X}{b:02X}"


def to_cfg(r: dict, skin: Optional[str]) -> dict:
    skin = skin or r["skin_hex"]
    cfg = {"mouth": dict(at=(r["mouth_x"], r["mouth_y"]), width=max(30, r["mouth_width"]), line=r["line_hex"],
                         line_width=max(4, round(r["mouth_width"] / 15)))}
    if r["has_drawn_mouth"] and r["cover_width"] > 0:
        cfg["mouth"]["cover"] = dict(color=skin, size=(r["cover_width"], r["cover_height"]))
    if r["eyes_visible"] and r["eye_radius_x"] > 6:
        cfg["eyes"] = dict(left=(r["left_eye_x"], r["left_eye_y"]), right=(r["right_eye_x"], r["right_eye_y"]),
                           size=(r["eye_radius_x"], r["eye_radius_y"]), lid=skin, line=r["line_hex"],
                           line_width=max(4, round(r["eye_radius_x"] / 6)))
    return cfg


def apply_fix(cfg: dict, f: dict) -> dict:
    m = cfg["mouth"]
    m["at"] = (m["at"][0] + f["mouth_dx"], m["at"][1] + f["mouth_dy"])
    m["width"] = max(30, round(m["width"] * (f["mouth_width_scale"] or 1)))
    if m.get("cover"):
        k = f["cover_scale"] or 1
        m["cover"]["size"] = (round(m["cover"]["size"][0] * k), round(m["cover"]["size"][1] * k))
    if cfg.get("eyes"):
        e = cfg["eyes"]
        e["left"] = (e["left"][0] + f["eyes_dx"], e["left"][1] + f["eyes_dy"])
        e["right"] = (e["right"][0] + f["eyes_dx"], e["right"][1] + f["eyes_dy"])
        k = f["eye_radius_scale"] or 1
        e["size"] = (round(e["size"][0] * k), round(e["size"][1] * k))
    return cfg


# ── 5. write mascot.py ───────────────────────────────────────────────────────

def write_settings(folder: str, info: dict, cfg: dict, r: Optional[dict]):
    name = (r or {}).get("name") or os.path.basename(folder).replace("-", " ").title()
    face = cfg["mouth"]["at"]
    if cfg.get("eyes"):
        face = (face[0], (cfg["eyes"]["left"][1] + face[1]) // 2)
    style = dict(background=((r or {}).get("background_top_hex", "#1E2126"), (r or {}).get("background_bottom_hex", "#2C313B")),
                 glow=(r or {}).get("glow_hex", "#6070FF"), accent=(r or {}).get("accent_hex", "#FFD43A"))
    lines = [
        f'"""{name}: made by `python make.py create` from {info["source"]}.',
        "",
        f'{(r or {}).get("description", "")}',
        'Tune the numbers with `python make.py check <name>` (grid.png + model_sheet.png)."""',
        "",
        f"NAME = {name!r}",
        "",
        "# ── Art ──",
        f"CANVAS = {tuple(info['canvas'])}",
        f"FEET = {tuple(info['feet'])}",
        f"FACE = {tuple(int(v) for v in face)}",
        f"SCALE = {info['scale']}",
        f"PLACE = {tuple(info['place'])}",
        "",
        "# ── Mouth + blinks drawn by the engine (or add mouth_*.png / eyes_*.png sprites to replace them) ──",
        f"MOUTH = {_fmt(cfg['mouth'])}",
        f"EYES = {_fmt(cfg['eyes']) if cfg.get('eyes') else None}",
        "",
        "# ── Voice ──",
        'VOICE = {"provider": "say", "voice": "Samantha"}',
        "# A voice made for this character (needs ELEVENLABS_API_KEY):",
        f"#   python make.py design-voice {os.path.basename(folder)} {json.dumps((r or {}).get('voice_description', 'a friendly cartoon mascot voice'))}",
        '# VOICE = {"provider": "elevenlabs", "voice_id": "YOUR_VOICE_ID"}',
        "",
        "# ── Look + behaviour ──",
        f"STYLE = {_fmt(style)}",
        'KEYWORDS = ["free", "comment"]',
        "TRIGGERS = {}",
        "",
    ]
    open(os.path.join(folder, "mascot.py"), "w").write("\n".join(lines))


def _fmt(d: dict) -> str:
    return "dict(" + ", ".join(f"{k}={_fmt(v) if isinstance(v, dict) else repr(tuple(v) if isinstance(v, list) else v)}"
                               for k, v in d.items()) + ")"


# ── entry point ──────────────────────────────────────────────────────────────

def create(name: str, image: str, rounds: int = 3) -> str:
    folder = os.path.join(pack.MASCOTS, name)
    if os.path.exists(os.path.join(folder, "mascot.py")):
        raise SystemExit(f"mascots/{name} already exists. Pick another name or delete that folder.")
    os.makedirs(os.path.join(folder, "sprites"), exist_ok=True)
    os.makedirs(os.path.join(folder, "refs"), exist_ok=True)
    src = Image.open(image)
    src.save(os.path.join(folder, "refs", "original" + os.path.splitext(image)[1].lower()))

    print("1/4 cut out")
    im, how = cutout(src)
    print("    " + how)
    print("2/4 size + canvas")
    base, info = normalise(im)
    info["source"] = os.path.basename(image)
    base.save(os.path.join(folder, "sprites", "pose_idle.png"))
    print(f"    {info['canvas'][0]}x{info['canvas'][1]}, {'waist-up' if info['bust'] else 'full body'}")

    client, why = _client()
    r = None
    if client is None:
        print(f"3/4 no Claude ({why}): guessing the face, fix it with `python make.py check {name}`")
        W, H = info["canvas"]
        cfg = {"mouth": dict(at=(W // 2, int(PAD + TARGET_H * 0.3)), width=120)}
    else:
        print(f"3/4 Claude ({MODEL}) finds the face")
        W, H = info["canvas"]
        r = _ask(client, [grid_image(base)], RIG_PROMPT.format(w=W, h=H), RIG_SCHEMA)
        skin = sample_skin(base, (r["mouth_x"], r["mouth_y"]), r["mouth_width"])
        cfg = to_cfg(r, skin)
        print(f"    {r['name']}: mouth at {cfg['mouth']['at']}, eyes {'yes' if cfg.get('eyes') else 'no'}, skin {skin or r['skin_hex']}")
        print("4/4 Claude checks the mouths and blinks")
        for i in range(rounds):
            strip = review_strip(base, cfg)
            strip.save(os.path.join(folder, "refs", f"review-{i + 1}.png"))
            f = _ask(client, [strip], FIX_PROMPT, FIX_SCHEMA)
            print(f"    round {i + 1}: {'looks right' if f['looks_right'] else f['notes']}")
            if f["looks_right"]:
                break
            cfg = apply_fix(cfg, f)
    write_settings(folder, info, cfg, r)
    return folder
