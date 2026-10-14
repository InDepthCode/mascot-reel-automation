#!/usr/bin/env python3
"""Claude Codes Influencers: talking mascot videos from a script.

  python make.py list                                   your mascots
  python make.py create NAME --image pic.png            any character picture -> talking mascot (Claude finds the face)
  python make.py new NAME [--from-image pic.png] [--refs a.png b.png]   blank mascot (refs/ = for Claude Code to draw)
  python make.py draw NAME                              re-run a code-drawn mascot's draw.py
  python make.py check NAME                             validate the art + model sheet + coordinate grid
  python make.py video NAME --text "Hey! ..."           voice -> lip sync -> mp4 (the whole thing)
  python make.py video NAME --audio voice.wav [--text "the script"]
  python make.py voice NAME --text "..."                just the voice file
  python make.py design-voice NAME "voice description"  ElevenLabs Voice Design: 3 new voices to pick from
  python make.py save-voice NAME GENERATED_VOICE_ID     keep one, prints the voice_id for mascot.py
  python make.py sheet NAME TAKE_DIR 0.5 2 4.5          stills from a finished take, for quick checks

Everything lands in out/NAME/.
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys

from engine import pack

ROOT = pack.ROOT
OUT = os.path.join(ROOT, "out")


def slug(text: str, n: int = 5) -> str:
    words = re.findall(r"[a-z0-9']+", text.lower())[:n]
    return "-".join(w.replace("'", "") for w in words) or "take"


def take_dir(name: str, label: str) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = os.path.join(OUT, name, f"{stamp}-{label}")
    os.makedirs(d, exist_ok=True)
    return d


def read_text(args) -> str:
    if getattr(args, "script", None):
        return open(args.script).read().strip()
    return (getattr(args, "text", None) or "").strip()


# ── commands ────────────────────────────────────────────────────────────────

def cmd_list(args):
    for d in sorted(os.listdir(pack.MASCOTS)):
        if d.startswith((".", "_")) or not os.path.isdir(os.path.join(pack.MASCOTS, d)):
            continue
        m = pack.load(d)
        kind = "code-drawn" if os.path.exists(os.path.join(m.folder, "draw.py")) else "image"
        print(f"  {d:<14} {m.name:<16} {kind:<11} voice: {m.voice.get('provider')}")


def cmd_new(args):
    dst = os.path.join(pack.MASCOTS, args.name)
    if os.path.exists(dst):
        sys.exit(f"mascots/{args.name} already exists")
    shutil.copytree(os.path.join(pack.MASCOTS, "_template"), dst)
    cfg = os.path.join(dst, "mascot.py")
    s = open(cfg).read().replace('NAME = "My Mascot"   # CHANGE ME', f'NAME = "{args.name.replace("-", " ").title()}"')
    open(cfg, "w").write(s)
    if args.refs:
        os.makedirs(os.path.join(dst, "refs"), exist_ok=True)
        for r in args.refs:
            shutil.copy(r, os.path.join(dst, "refs", os.path.basename(r)))
        print(f"  copied {len(args.refs)} reference image(s) -> mascots/{args.name}/refs/ "
              "(ask Claude Code: \"draw this mascot from its refs\")")
    if args.from_image:
        from PIL import Image
        im = Image.open(args.from_image).convert("RGBA")
        im.save(os.path.join(dst, "sprites", "pose_idle.png"))
        print(f"  copied {args.from_image} -> sprites/pose_idle.png ({im.width}x{im.height})")
    print(f"Created mascots/{args.name}/. Next:")
    print(f"  1. put your art in mascots/{args.name}/sprites/ (at least pose_idle.png)")
    print(f"  2. python make.py check {args.name}     (read the mouth position off the grid)")
    print(f"  3. set MOUTH in mascots/{args.name}/mascot.py, then check again")
    print(f'  4. python make.py video {args.name} --text "Hey! I am alive."')


def cmd_create(args):
    from engine import autorig
    folder = autorig.create(args.name, args.image, rounds=args.rounds)
    from engine import check
    out = os.path.join(OUT, args.name, "check")
    check.run(args.name, out)
    print(f"\nCreated {folder}")
    print(f"  look at   {out}/model_sheet.png")
    print(f'  then      python make.py video {args.name} --text "Hey! I am alive."')


def cmd_draw(args):
    m = pack.load(args.name)
    script = os.path.join(m.folder, "draw.py")
    if not os.path.exists(script):
        sys.exit(f"{args.name} has no draw.py: its art is plain images in sprites/")
    subprocess.run([sys.executable, script], check=True)


def cmd_check(args):
    from engine import check
    out = os.path.join(OUT, args.name, "check")
    ok = check.run(args.name, out)
    print(f"\n  model sheet -> {out}/model_sheet.png\n  grid        -> {out}/grid.png")
    if not ok:
        sys.exit(1)


def cmd_voice(args, quiet=False):
    from engine import voice
    m = pack.load(args.name)
    text = read_text(args) or sys.exit("give the line with --text or --script")
    d = getattr(args, "_dir", None) or take_dir(args.name, slug(text))
    path = voice.speak(text, m.voice, os.path.join(d, "voice.wav"))
    if not quiet:
        print("  voice ->", path)
    return path, d


def cmd_video(args):
    from engine import animate, lipsync
    m = pack.load(args.name)
    text = read_text(args)
    if args.audio:
        d = take_dir(args.name, slug(text) if text else slug(os.path.splitext(os.path.basename(args.audio))[0]))
        audio = args.audio
    else:
        if not text:
            sys.exit('give the script with --text "..." (or --script file.txt), or a recording with --audio')
        if m.voice.get("provider") in ("file", "voicebox"):
            sys.exit("This mascot's VOICE is a file: record or export the line, then pass --audio voice.wav")
        print("1/3 voice")
        args._dir = take_dir(args.name, slug(text))
        audio, d = cmd_voice(args, quiet=True)
    print("2/3 lip sync")
    lipsync.analyze(audio, text, d, use_whisper=not args.no_whisper)
    print("3/3 render")
    out = os.path.join(d, f"{args.name}.mp4")
    animate.render(args.name, d, out)
    print(f"\nDone -> {out}")


def cmd_design_voice(args):
    from engine import voice
    text = args.text or ("Hey hey! I run one command, and boom, my whole content calendar is done. "
                         "Pretty ridiculous, right? Comment the word mascot and I'll send it over!")
    d = os.path.join(OUT, args.name, "voice-design")
    for p in voice.design(args.description, text, d):
        print(f"  candidate {p['candidate']}: {p['file']}\n    generated_voice_id = {p['generated_voice_id']}")
    print(f"\nListen, then: python make.py save-voice {args.name} <generated_voice_id>")


def cmd_save_voice(args):
    import json
    from engine import voice
    meta = os.path.join(OUT, args.name, "voice-design", "candidates.json")
    desc = json.load(open(meta))["description"] if os.path.exists(meta) else f"{args.name} mascot voice"
    vid = voice.save_voice(f"{args.name} mascot", desc, args.generated_voice_id)
    print(f"Saved to your ElevenLabs voices. Put this in mascots/{args.name}/mascot.py:\n")
    print(f'VOICE = {{"provider": "elevenlabs", "voice_id": "{vid}"}}')


def cmd_sheet(args):
    from engine import animate
    out = os.path.join(args.take, "sheet.png")
    print("->", animate.contact_sheet(args.name, args.take, out, [float(t) for t in args.times] or [0.5, 2, 4]))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("new"); s.add_argument("name"); s.add_argument("--from-image"); s.add_argument("--refs", nargs="*")
    s.set_defaults(fn=cmd_new)
    s = sub.add_parser("create"); s.add_argument("name"); s.add_argument("--image", required=True)
    s.add_argument("--rounds", type=int, default=3, help="how many times Claude re-checks the mouth placement")
    s.set_defaults(fn=cmd_create)
    s = sub.add_parser("draw"); s.add_argument("name"); s.set_defaults(fn=cmd_draw)
    s = sub.add_parser("check"); s.add_argument("name"); s.set_defaults(fn=cmd_check)
    for n, fn in (("voice", cmd_voice), ("video", cmd_video)):
        s = sub.add_parser(n); s.add_argument("name"); s.add_argument("--text"); s.add_argument("--script")
        if n == "video":
            s.add_argument("--audio", help="use this recording instead of generating a voice")
            s.add_argument("--no-whisper", action="store_true", help="skip Whisper word timings")
        s.set_defaults(fn=fn)
    s = sub.add_parser("design-voice"); s.add_argument("name"); s.add_argument("description"); s.add_argument("--text")
    s.set_defaults(fn=cmd_design_voice)
    s = sub.add_parser("save-voice"); s.add_argument("name"); s.add_argument("generated_voice_id"); s.set_defaults(fn=cmd_save_voice)
    s = sub.add_parser("sheet"); s.add_argument("name"); s.add_argument("take"); s.add_argument("times", nargs="*")
    s.set_defaults(fn=cmd_sheet)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
