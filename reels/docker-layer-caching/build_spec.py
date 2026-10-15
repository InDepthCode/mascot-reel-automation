#!/usr/bin/env python3
"""build_spec.py TAKE_DIR -> TAKE_DIR/work/spec.json + TAKE_DIR/tile_path.json  (Docker layer caching reel)

Scenes are keyed to phrase numbers (p0..p149 from make_phrases.py), so the same design works for any voice;
only the tile path needs seconds, and it is read from timing.json. Colours: green = cached, amber = rebuilt, blue = highlight."""
import json, os, sys

T = sys.argv[1]
W = os.path.join(T, "work")
timing = json.load(open(os.path.join(W, "timing.json")))
dur = round(json.load(open(os.path.join(T, "take.json")))["duration"], 2)
p = lambda n, off="": f"p{n}{off}"

NEU = dict(color="#12304F", outline="#35506F", fg="#EAF3FC")
OK = dict(color="#0F3A33", outline="#5EE0A0", fg="#D9FFEA")
BAD = dict(color="#3A2A14", outline="#FFB454", fg="#FFD9A0")
HI = dict(color="#12304F", outline="#4DB5FF", fg="#EAF3FC")


def box(title, y, at, sub=None, st=NEU, x=360, w=600, h=120, size=40, states=()):
    e = dict(type="box", title=title, x=x, y=y, w=w, h=h, size=size, at=p(at), **st)
    if sub:
        e.update(sub=sub, sub_size=28)
    if states:
        e["states"] = [dict(at=p(a), sub=sub_, **s) for a, s, sub_ in states]
    return e


def hdr(parts, at, size=48):
    return dict(type="text", parts=parts, x=60, y=300, size=size, anchor="left", weight="medium", at=p(at))


def text(parts, at, x=360, y=900, size=40, until=None):
    e = dict(type="text", parts=parts, x=x, y=y, size=size, weight="medium", anim="slide", at=p(at))
    if until is not None:
        e["until"] = p(until)
    return e


def headline(lines, at, y=330, size=80, line_at=None):
    e = dict(type="headline", lines=lines, x=96, y=y, size=size, at=p(at))
    if line_at:
        e["line_at"] = [p(a) for a in line_at]
    return e


scenes = [
    dict(start="start", elements=[
        headline(["Your Docker builds", "are slow."], 0, size=90, line_at=[0, 1]),
        headline([[["One mistake.", "accent2"]]], 2, y=640, size=120),
        text([["You are throwing away your cache.", "muted"]], 3, x=96, y=800, size=34) | dict(anchor="left")]),
    dict(start=p(7), elements=[
        headline(["In 3 minutes,", [["how Docker layer caching", "muted"]], [["really works and how to fix it.", "muted"]]], 7, size=64, line_at=[7, 10, 12])]),
    dict(start=p(14), elements=[
        hdr([["How it works", "muted"]], 14),
        box("RUN", 440, 16, states=[(20, NEU, "a layer"), (29, OK, "cached")]),
        box("COPY", 590, 17, states=[(20, NEU, "a layer"), (29, OK, "cached"), (32, BAD, "rebuilt")]),
        box("ADD", 740, 18, states=[(20, NEU, "a layer"), (29, OK, "cached"), (37, BAD, "rebuilt")]),
        text([["Everything after a change rebuilds", "accent2"]], 38, y=900, size=36)]),
    dict(start=p(42), elements=[
        hdr([["The classic mistake", "accent2"]], 42),
        box("FROM node:20", 440, 46),
        box("COPY . .", 590, 47, states=[(54, BAD, "changed")]),
        box("RUN npm install", 740, 49, states=[(55, BAD, "rebuilt"), (58, BAD, "from scratch")]),
        text([["You edit one line of code", "muted"]], 51, y=900, until=54),
        text([["Every single build.", "accent2"]], 59, y=1010, size=60)]),
    dict(start=p(60), elements=[
        headline(["Quick question.", [["Which one are you", "muted"]], [["guilty of?", "muted"]]], 60, size=70, line_at=[60, 61, 62]),
        box("Copying everything first", 700, 63, st=HI, size=38),
        box("No .dockerignore file", 850, 65, st=HI, size=38),
        text([["Tell me in the comments", "accent"]], 66, y=1040, size=46)]),
    dict(start=p(68), elements=[
        hdr([["Fix 1", "accent"], ["  order your layers", "ink"]], 68),
        box("FROM node:20", 430, 69, states=[(80, OK, "cached")]),
        box("COPY package*.json ./", 570, 72, size=36, states=[(80, OK, "cached")]),
        box("RUN npm install", 710, 74, states=[(81, OK, "dependencies cached")]),
        box("COPY . .", 850, 75, states=[(78, BAD, "rebuilds")])]),
    dict(start=p(83), elements=[
        hdr([["Fix 2", "accent"], ["  add a .dockerignore", "ink"]], 83),
        box(".dockerignore", 450, 84, st=HI, size=44),
        dict(type="bullets", x=90, y=620, gap=100, size=52, items=[dict(text="node_modules", at=p(85)), dict(text=".git", at=p(86)), dict(text="*.log", at=p(87))]),
        text([["Ignored files can't break your cache.", "accent"]], 94, y=960, size=36)]),
    dict(start=p(95), elements=[
        hdr([["Fix 3", "accent"], ["  apt and base image", "ink"]], 95),
        box("apt-get update", 440, 96, "on its own line = stale list", BAD),
        box("apt-get update && install", 590, 98, "same RUN instruction", OK, size=36),
        box("FROM node:20.11", 790, 103, "pinned tag", OK),
        box("FROM node:latest", 940, 105, "floating tag", BAD, states=[(108, BAD, "whole cache lost")])]),
    dict(start=p(110), elements=[
        hdr([["Fix 4", "accent"], ["  BuildKit cache mount", "ink"]], 110),
        box("RUN --mount=type=cache", 450, 112, "on your package manager folder", HI, size=36),
        box("Download cache", 620, 116, "survives between builds", OK),
        box("Layer rebuilds", 790, 118, "packages still cached", BAD)]),
    dict(start=p(120), elements=[
        hdr([["CI", "accent"], ["  starts with no cache", "ink"]], 120),
        box("Fresh CI runner", 450, 121, "no cache at all", BAD),
        text([["cache from  |  cache to", "accent"]], 125, y=615, size=42),
        dict(type="flow", **{"from": [570, 725], "to": [570, 515]}, color="accent", rate=1.4, n=3, at=p(125)),
        dict(type="flow", **{"from": [90, 515], "to": [90, 725]}, color="accent", rate=1.4, n=3, at=p(126)),
        box("Registry or GitHub Actions cache", 790, 127, "layers reused", OK, size=34)]),
    dict(start=p(132), elements=[
        hdr([["Recap", "accent"]], 132),
        dict(type="bullets", x=90, y=390, gap=90, size=46, items=[
            dict(text="Order layers, stable first", at=p(134)), dict(text="Add a .dockerignore", at=p(136)),
            dict(text="apt update + install together", at=p(137)), dict(text="Pin the base image", at=p(139)),
            dict(text="Cache mounts + CI cache", at=p(141))])]),
    dict(start=p(143), elements=[
        headline([[["Minutes", "accent2"]], [["to seconds.", "accent"]]], 143, y=360, size=120, line_at=[143, 145])]),
    dict(start=p(147), elements=[
        headline(["Send this to the", "teammate whose", "pipeline takes forever."], 147, y=340, size=72, line_at=[147, 148, 149]),
        text([["Follow for more", "accent"]], "149+0.3", x=96, y=660, size=52) | dict(anchor="left")]),
]
spec = dict(style="pro", trim=[0, dur], drift=0.03, grain=0, caption_size=48, caption_highlight="accent",
            palette=dict(bg="#0B1B2E", bg2="#12304F", ink="#EAF3FC", muted="#8CA6C4", dim="#35506F", accent="#4DB5FF", accent2="#FFB454"),
            punch=[[p(n), p(n, ".end")] for n in (0, 34, 59, 68, 143)], scenes=scenes)
json.dump(spec, open(os.path.join(W, "spec.json"), "w"), indent=1, ensure_ascii=False)

# tile path: (phrase, spot). Right column while a left-aligned stack/boxes are on screen; left or bottom when text runs wide.
moves = [(0, "br"), (14, "tr"), (29, "mr"), (35, "br"), (42, "mr"), (49, "br"), (54, "tr"), (60, "mr"), (66, "br"), (68, "tr"), (75, "mr"),
         (79, "br"), (83, "mr"), (88, "tr"), (95, "tr"), (103, "mr"), (108, "br"), (110, "tr"), (116, "mr"), (120, "br"), (127, "tr"),
         (132, "br"), (143, "bl"), (147, "br")]
start = {t["i"]: t["start"] for t in timing}
keys = []
for n, spot in moves:
    if not keys or keys[-1][1] != spot:
        keys.append([round(start[n], 2) if n else 0, spot])
json.dump(keys, open(os.path.join(T, "tile_path.json"), "w"))
print(f"{len(scenes)} scenes, {len(keys)} tile spots, {dur}s")
