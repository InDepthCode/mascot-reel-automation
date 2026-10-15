"""Text -> voice file, using the provider set in the mascot's VOICE setting.

Providers:
  say         macOS built-in voices. Zero setup, good for testing.     VOICE = {"provider": "say", "voice": "Samantha"}
  edge        Microsoft Edge neural voices, free, any OS, needs internet.  VOICE = {"provider": "edge", "voice": "en-US-AriaNeural"}
              (also the automatic fallback when "say" is set but this machine has no `say`)
  clone       Your own voice from a reference clip, free, on a Hugging Face Space (no local GPU/CPU load).
              VOICE = {"provider": "clone", "ref_audio": "mascots/NAME/voice_ref.wav"}  + voice_ref.txt = its transcript
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
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from typing import List

from .pack import ROOT

API = "https://api.elevenlabs.io/v1"
CLONE_SPACES = ("ResembleAI/Chatterbox", "abidlabs/E2-F5-TTS")   # tried in order, first one that answers wins
# Broadcast polish for cloned speech: rumble cut, warmth + presence, gentle compression, -16 LUFS.
MASTER = ("highpass=f=80,equalizer=f=150:t=q:w=1:g=1.5,equalizer=f=3500:t=q:w=1:g=2.5,"
          "acompressor=threshold=-18dB:ratio=3:attack=15:release=200:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=11")
CACHE = os.path.join(ROOT, "out", "voice-cache")   # finished clone parts: a long script can be finished on another day
EDGE_VOICE = "en-US-AriaNeural"   # other good ones: en-US-ChristopherNeural, en-US-GuyNeural, en-GB-SoniaNeural


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
    if provider == "say" and not shutil.which("say"):   # not macOS: fall back to edge (macOS voice names don't carry over)
        print("  no macOS `say` here, using the edge voice instead (set VOICE provider to 'edge' to silence this)")
        provider, voice = "edge", {k: v for k, v in voice.items() if k == "pitch"}
    if provider == "clone":
        _clone(text, voice, out_path)
    elif provider == "edge":
        _edge(text, voice, out_path)
    elif provider == "elevenlabs":
        vid = voice.get("voice_id") or sys.exit("VOICE needs a voice_id for elevenlabs (see mascot.py)")
        body = {"text": text, "model_id": voice.get("model", "eleven_multilingual_v2"),
                "voice_settings": voice.get("settings", {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35})}
        mp3 = _post(f"/text-to-speech/{vid}?output_format=mp3_44100_128", body, accept="audio/mpeg")
        tmp = out_path + ".mp3"
        open(tmp, "wb").write(mp3)
        _convert(tmp, out_path)
        os.remove(tmp)
    elif provider == "say":
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
        sys.exit(f"Unknown voice provider '{provider}' (use say, edge, clone, elevenlabs or file)")
    return out_path


def _chunks(text: str, limit: int = 280) -> List[str]:
    """Sentences packed into pieces the Spaces accept (Chatterbox caps a request at ~300 characters)."""
    out, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        if cur and len(cur) + 1 + len(sent) > limit:
            out.append(cur)
            cur = ""
        cur = f"{cur} {sent}".strip()
    return out + [cur] if cur else out


def _cached(key: str, make) -> str:
    """Returns the cached wav for key, or runs make() (-> a wav path) and keeps a copy: finished parts survive a quota stop."""
    f = os.path.join(CACHE, key + ".wav")
    if not os.path.exists(f):
        src = make()
        os.makedirs(CACHE, exist_ok=True)
        shutil.copy(src, f)
    return f


def _quota_hit(e: Exception) -> bool:
    return "ZeroGPU" in str(e) and "limit" in str(e).lower()


def _clone_space(space: str, chunks: List[str], ref: str, ref_text: str, timeout: float = 240) -> List[str]:
    from gradio_client import Client, handle_file
    c = Client(space, token=os.environ.get("HF_TOKEN") or None, verbose=False, httpx_kwargs={"timeout": 60})
    wavs = []
    who = hashlib.sha1(space.encode() + open(ref, "rb").read()).hexdigest()[:10]
    for t in chunks:
        key = f"{who}-{hashlib.sha1(t.encode()).hexdigest()[:16]}"
        wavs.append(_cached(key, lambda t=t: _clone_part(c, handle_file, space, t, ref, ref_text, timeout)))
    return wavs


def _clone_part(c, handle_file, space: str, t: str, ref: str, ref_text: str, timeout: float) -> str:
    if space == "ResembleAI/Chatterbox":
        return c.submit(text_input=t, audio_prompt_path_input=handle_file(ref), exaggeration_input=0.5, temperature_input=0.8,
                        seed_num_input=0, cfgw_input=0.5, vad_trim_input=False, api_name="/generate_tts_audio").result(timeout=timeout)
    # an E2/F5-TTS Space: needs the words spoken in the reference clip too
    return c.submit(ref_audio_orig=handle_file(ref), ref_text=ref_text, gen_text=t, exp_name="F5-TTS", remove_silence=True,
                    cross_fade_duration=0.15, api_name="/infer").result(timeout=timeout)[0]


def _clone(text: str, voice: dict, out_path: str):
    try:
        import gradio_client  # noqa: F401
    except ImportError:
        sys.exit("The clone voice needs gradio_client: pip install gradio_client")
    load_env()
    ref = voice.get("ref_audio") or sys.exit('VOICE needs ref_audio for clone, e.g. "mascots/NAME/voice_ref.wav"')
    ref = ref if os.path.isabs(ref) else os.path.join(ROOT, ref)
    if not os.path.exists(ref):
        sys.exit(f"Reference clip not found: {ref}")
    txt = os.path.splitext(ref)[0] + ".txt"
    ref_text = voice.get("ref_text") or (open(txt).read().strip() if os.path.exists(txt) else "")
    chunks, errors = _chunks(text), []
    for space in voice.get("spaces", CLONE_SPACES):
        try:
            print(f"  cloning voice on {space} ({len(chunks)} part{'s' * (len(chunks) > 1)})...")
            wavs = _clone_space(space, chunks, ref, ref_text)
            break
        except Exception as e:
            if _quota_hit(e):   # the other Space is CPU-only and too slow to be a fallback: stop and keep what is done
                done = len([f for f in os.listdir(CACHE)]) if os.path.isdir(CACHE) else 0
                sys.exit(f"{space}: {str(e)[:260]}\n  Finished parts are saved ({done} in out/voice-cache): run the same command again "
                         "when your free Hugging Face quota resets and it continues where it stopped.")
            errors.append(f"{space}: {type(e).__name__}: {str(e)[:200]}")
            print(f"  {errors[-1]}\n  trying the next one...")
    else:
        sys.exit("Voice cloning failed on every Space (they are free and share GPU quota; try again later, or set HF_TOKEN "
                 "in .env for more quota, or pass your own recording with --audio):\n  " + "\n  ".join(errors))
    ins = [a for w in wavs for a in ("-i", w)]
    graph = "".join(f"[{i}]" for i in range(len(wavs))) + f"concat=n={len(wavs)}:v=0:a=1,{MASTER}"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", graph, "-ac", "1", "-ar", "44100",
                    out_path], check=True)


def _edge(text: str, voice: dict, out_path: str):
    try:
        import edge_tts
    except ImportError:
        sys.exit("The edge voice needs edge-tts: pip install edge-tts")
    import asyncio
    kw = {"rate": voice["rate"]} if voice.get("rate") else {}   # edge rate is a string like "+10%"
    tmp = out_path + ".mp3"
    try:
        asyncio.run(edge_tts.Communicate(text, voice.get("voice", EDGE_VOICE), **kw).save(tmp))
    except Exception as e:
        sys.exit(f"edge-tts failed (it needs internet access): {e}")
    _convert(tmp, out_path, pitch=voice.get("pitch", 1.0))
    os.remove(tmp)


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
