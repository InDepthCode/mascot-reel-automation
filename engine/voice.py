"""Text -> voice file, using the provider set in the mascot's VOICE setting.

Providers:
  say         macOS built-in voices. Zero setup, good for testing.     VOICE = {"provider": "say", "voice": "Samantha"}
  elevenlabs  Best quality. Needs ELEVENLABS_API_KEY in .env.         VOICE = {"provider": "elevenlabs", "voice_id": "..."}
  file        Bring your own recording (or a Voicebox export).         python make.py video NAME --audio take.wav

Voicebox (https://github.com/jamiepine/voicebox) is a free, local ElevenLabs alternative: clone or design a voice
in the app, generate the line, export the wav and pass it with --audio.

ElevenLabs Voice Design (make a brand-new voice from a description):
  python make.py design-voice NAME "a small excited cartoon creature, bright and squeaky but clear"
  -> 3 preview mp3s in out/NAME/voice-design/, then: python make.py save-voice NAME <generated_voice_id>
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from typing import List

from .pack import ROOT

API = "https://api.elevenlabs.io/v1"


def load_env():
    """Reads .env in the repo root into os.environ (no extra package needed)."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _key() -> str:
    load_env()
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("ELEVENLABS_API_KEY is not set. Copy .env.example to .env and paste your key "
                 "(elevenlabs.io -> Developers -> API keys).")
    return key


def _post(path: str, body: dict, accept: str = "application/json") -> bytes:
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"xi-api-key": _key(), "Content-Type": "application/json", "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"ElevenLabs {e.code}: {e.read().decode(errors='replace')[:400]}")


def speak(text: str, voice: dict, out_path: str) -> str:
    """Writes the line to out_path (any extension ffmpeg understands) and returns the path."""
    provider = voice.get("provider", "say")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if provider == "elevenlabs":
        vid = voice.get("voice_id") or sys.exit("VOICE needs a voice_id for elevenlabs (see mascot.py)")
        body = {"text": text, "model_id": voice.get("model", "eleven_multilingual_v2"),
                "voice_settings": voice.get("settings", {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35})}
        mp3 = _post(f"/text-to-speech/{vid}?output_format=mp3_44100_128", body, accept="audio/mpeg")
        tmp = out_path + ".mp3"
        open(tmp, "wb").write(mp3)
        _convert(tmp, out_path)
        os.remove(tmp)
    elif provider == "say":
        if not shutil.which("say"):
            sys.exit("The 'say' voice only exists on macOS. Use elevenlabs, or record a file and pass --audio.")
        tmp = out_path + ".aiff"
        cmd = ["say", "-o", tmp]
        if voice.get("voice"):
            cmd += ["-v", voice["voice"]]
        if voice.get("rate"):
            cmd += ["-r", str(voice["rate"])]
        subprocess.run(cmd + [text], check=True)
        _convert(tmp, out_path, pitch=voice.get("pitch", 1.0))
        os.remove(tmp)
    elif provider in ("file", "voicebox"):
        sys.exit("This mascot's voice comes from a file: pass it with --audio path/to/voice.wav")
    else:
        sys.exit(f"Unknown voice provider '{provider}' (use say, elevenlabs or file)")
    return out_path


def _convert(src: str, dst: str, pitch: float = 1.0):
    af = []
    if pitch and abs(pitch - 1.0) > 1e-3:   # cartoon pitch-up that keeps the speed
        af = ["-af", f"aresample=44100,asetrate=44100*{pitch},aresample=44100,atempo={1 / pitch:.4f}"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, *af, "-ac", "1", "-ar", "44100", dst], check=True)


def design(description: str, sample_text: str, out_dir: str) -> List[dict]:
    """ElevenLabs Voice Design: 3 previews of a brand-new voice. Listen, pick one, then save_voice()."""
    os.makedirs(out_dir, exist_ok=True)
    res = json.loads(_post("/text-to-voice/design", {
        "voice_description": description, "text": sample_text, "model_id": "eleven_multilingual_ttv_v2"}))
    previews = []
    for i, p in enumerate(res.get("previews", []), 1):
        path = os.path.join(out_dir, f"candidate-{i}.mp3")
        open(path, "wb").write(base64.b64decode(p["audio_base_64"]))
        previews.append({"candidate": i, "generated_voice_id": p["generated_voice_id"], "file": path})
    json.dump({"description": description, "text": sample_text, "previews": previews},
              open(os.path.join(out_dir, "candidates.json"), "w"), indent=2)
    return previews


def save_voice(name: str, description: str, generated_voice_id: str) -> str:
    res = json.loads(_post("/text-to-voice", {"voice_name": name, "voice_description": description,
                                              "generated_voice_id": generated_voice_id}))
    return res["voice_id"]
