"""Audio -> a "take": mouth cues, word timings and a loudness envelope.

    take = analyze("voice.wav", script="what the voice says")   # dict, saved as take.json

Mouth cues, best first:
  1. Rhubarb Lip Sync (free, open source): real phoneme recognition -> mouths A-H + X.
     Install: bash scripts/install_rhubarb.sh   (or set RHUBARB_PATH)
  2. Loudness fallback: no install, mouth opens with the volume. Fine for a first test.

Word timings (for captions and trigger words), best first:
  1. Whisper (pip install openai-whisper): exact word times.
  2. Your script text spread over the voiced parts of the audio: close enough for captions.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Optional

import numpy as np

from .pack import ROOT

ENV_FPS = 100


# ── audio ────────────────────────────────────────────────────────────────────

def to_wav(src: str, dst: str) -> str:
    """Any audio/video file -> 44.1 kHz mono 16-bit wav (what Rhubarb wants)."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-ar", "44100",
                    "-c:a", "pcm_s16le", dst], check=True)
    return dst


def duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def envelope(path: str) -> np.ndarray:
    """Loudness at 100 fps, normalised so ordinary speech peaks around 1."""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    hop = 16000 // ENV_FPS
    n = len(x) // hop
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1)) if n else np.zeros(1)
    ref = np.percentile(rms[rms > 1e-4], 90) if np.any(rms > 1e-4) else 1.0
    env = np.clip(rms / (ref + 1e-9), 0, 1.6)
    env[env < 0.06] = 0.0
    return np.convolve(env, np.ones(3) / 3, mode="same")


# ── words ────────────────────────────────────────────────────────────────────

def whisper_words(wav: str, prompt: str = "", model: str = "small.en") -> Optional[List[dict]]:
    try:
        import whisper   # openai-whisper
    except ImportError:
        return None
    print(f"  whisper ({model}) word timings...")
    m = whisper.load_model(model)
    res = m.transcribe(wav, word_timestamps=True, initial_prompt=prompt or None, fp16=False)
    out = []
    for seg in res["segments"]:
        for w in seg.get("words", []):
            out.append({"word": w["word"].strip(), "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3)})
    return out


def spread_words(script: str, env: np.ndarray) -> List[dict]:
    """No Whisper: lay the script's words over the voiced stretches, longer words get more time."""
    words = script.split()
    if not words:
        return []
    voiced = env > 0.08
    idx = np.flatnonzero(voiced)
    if not len(idx):
        return []
    t0, t1 = idx[0] / ENV_FPS, (idx[-1] + 1) / ENV_FPS
    # time only counts while someone is talking, so pauses stay pauses
    talk_t = np.cumsum(voiced.astype(float)) / ENV_FPS
    total = talk_t[-1]
    weights = np.array([len(re.sub(r"\W", "", w)) + 2 for w in words], dtype=float)
    edges = np.concatenate([[0], np.cumsum(weights) / weights.sum() * total])

    def real_time(talk):
        i = int(np.searchsorted(talk_t, talk))
        return float(min(max(i / ENV_FPS, t0), t1))

    return [{"word": w, "start": round(real_time(edges[i]), 3), "end": round(real_time(edges[i + 1]), 3)}
            for i, w in enumerate(words)]


# ── mouth cues ───────────────────────────────────────────────────────────────

def rhubarb_bin() -> Optional[str]:
    cands = [os.environ.get("RHUBARB_PATH", ""), shutil.which("rhubarb") or ""]
    cands += glob.glob(os.path.join(ROOT, "tools", "rhubarb", "**", "rhubarb"), recursive=True)
    cands += glob.glob(os.path.join(ROOT, "tools", "rhubarb", "**", "rhubarb.exe"), recursive=True)
    cands += glob.glob(os.path.expanduser("~/.local/share/rhubarb/**/rhubarb"), recursive=True)
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def rhubarb_cues(wav: str, script: str = "") -> Optional[List[dict]]:
    exe = rhubarb_bin()
    if not exe:
        return None
    print("  rhubarb lip sync...")
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [exe, "-f", "json", "--extendedShapes", "GHX", "-o", os.path.join(tmp, "r.json")]
        if script:
            open(os.path.join(tmp, "dialog.txt"), "w").write(script)
            cmd += ["-d", os.path.join(tmp, "dialog.txt")]
        subprocess.run(cmd + [wav], check=True, capture_output=True)
        return json.load(open(os.path.join(tmp, "r.json")))["mouthCues"]


def energy_cues(env: np.ndarray) -> List[dict]:
    """Fallback: mouth size follows the volume, with a lip close between syllables."""
    cues, cur, start = [], None, 0.0
    step = 0.06   # ~2 frames per mouth, like hand animation on twos
    n = int(len(env) / ENV_FPS / step)
    for i in range(n):
        t = i * step
        a = env[int(t * ENV_FPS): int((t + step) * ENV_FPS)]
        e = float(a.mean()) if len(a) else 0.0
        prev = float(env[max(0, int((t - step) * ENV_FPS))])
        if e < 0.08:
            v = "X"
        elif e < prev * 0.55:
            v = "A"            # sudden dip = lips meet
        elif e < 0.3:
            v = "B"
        elif e < 0.55:
            v = "C" if i % 3 else "F"
        elif e < 0.85:
            v = "E" if i % 4 == 0 else "C"
        else:
            v = "D"
        if v != cur:
            if cur is not None:
                cues.append({"start": round(start, 3), "end": round(t, 3), "value": cur})
            cur, start = v, t
    cues.append({"start": round(start, 3), "end": round(n * step, 3), "value": cur or "X"})
    return cues


# ── take ─────────────────────────────────────────────────────────────────────

def analyze(audio: str, script: str = "", out_dir: Optional[str] = None, use_whisper: bool = True) -> dict:
    out_dir = out_dir or os.path.dirname(os.path.abspath(audio))
    os.makedirs(out_dir, exist_ok=True)
    wav = os.path.join(out_dir, "voice.wav")
    if os.path.abspath(audio) != os.path.abspath(wav):
        to_wav(audio, wav)
    env = envelope(wav)
    words = whisper_words(wav, script) if use_whisper else None
    word_src = "whisper"
    if words is None:
        words, word_src = spread_words(script, env), "script"
    cues = rhubarb_cues(wav, script or " ".join(w["word"] for w in words))
    cue_src = "rhubarb"
    if cues is None:
        print("  rhubarb not installed -> loudness lip sync (bash scripts/install_rhubarb.sh for the real thing)")
        cues, cue_src = energy_cues(env), "loudness"
    take = {"audio": "voice.wav", "duration": round(duration(wav), 3), "mouth_engine": cue_src, "word_engine": word_src,
            "cues": cues, "words": words, "env_fps": ENV_FPS, "env": [round(float(v), 3) for v in env]}
    json.dump(take, open(os.path.join(out_dir, "take.json"), "w"))
    print(f"  take -> {out_dir}/take.json  (mouths: {cue_src}, words: {word_src})")
    return take
