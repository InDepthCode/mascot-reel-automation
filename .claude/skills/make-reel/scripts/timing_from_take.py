#!/usr/bin/env python3
"""timing_from_take.py WORKDIR TAKE_DIR  -> WORKDIR/timing.json

Times every caption phrase from a mascot take's word timings (Whisper, aligned to the script) instead of espeak + DTW.
Needs WORKDIR/phrases.json (make_phrases.py) and TAKE_DIR/take.json (make.py take / video)."""
import json, os, re, sys
W, T = sys.argv[1], sys.argv[2]
P = json.load(open(os.path.join(W, 'phrases.json')))
take = json.load(open(os.path.join(T, 'take.json')))
words = take['words']
n = lambda s: len(re.sub(r'[^0-9a-zA-Z]', '', s))
cum_w, c = [], 0
for w in words:
    c += max(1, n(w['word'])); cum_w.append(c)
cum_p, c = [], 0
for p in P:
    c += max(1, n(p['text'])); cum_p.append(c)
scale = cum_w[-1] / cum_p[-1]            # the phrases and the words come from the same script; this absorbs small spelling differences
out, start = [], words[0]['start']
for i, p in enumerate(P):
    j = next((k for k, v in enumerate(cum_w) if v >= cum_p[i] * scale - 0.5), len(words) - 1)
    end = words[j]['end'] if i < len(P) - 1 else words[-1]['end']
    out.append({'i': i, 'text': p['text'], 'start': round(start, 2), 'end': round(max(end, start + 0.15), 2)})
    nxt = words[min(j + 1, len(words) - 1)]['start']
    start = max(end, nxt) if j + 1 < len(words) else end
json.dump(out, open(os.path.join(W, 'timing.json'), 'w'), indent=1, ensure_ascii=False)
for o in out: print(f"p{o['i']:<3} {o['start']:7.2f}-{o['end']:7.2f}  {o['text']}")
