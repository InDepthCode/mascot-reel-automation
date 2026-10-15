#!/usr/bin/env python3
"""make_phrases.py SCRIPT.txt WORKDIR [--highlight "Redis,Kafka,100,000,write spikes"] [--max-words 4]

Turns the user's script into short caption phrases (2-4 words) -> WORKDIR/phrases.json
and prints a numbered list (p0, p1, ...) to reference from spec.json.
Highlight terms: case-insensitive; multi-word terms allowed; separate terms with '|' if they contain commas.
"""
import argparse, json, os, re
from num2words import num2words

ap = argparse.ArgumentParser()
ap.add_argument('script'); ap.add_argument('work')
ap.add_argument('--highlight', default='')
ap.add_argument('--max-words', type=int, default=4)
ap.add_argument('--max-chars', type=int, default=26)
ap.add_argument('--lang', default='en')
a = ap.parse_args()

raw = open(a.script, encoding='utf-8').read()
# drop section labels like "Hook (0-5s):", "Body:", "CTA (20-30s):", "Scene 2:" and [stage directions]
LABEL = r'(?im)^\s*(hook|intro|opening|body|main|point\s*\d*|part\s*\d*|scene\s*\d*|step\s*\d*|cta|outro|ending|closing|call to action)\b[^:\n]{0,25}:\s*'
txt = re.sub(LABEL, '', raw)
txt = re.sub(r'\[[^\]]*\]', ' ', txt)
txt = txt.replace('—', ', ').replace('–', ', ').replace('…', '... ')
words = txt.split()

sep = '|' if '|' in a.highlight else ','
# keep numbers with thousands separators intact when splitting on commas
hl_raw = a.highlight
if sep == ',':
    hl_raw = re.sub(r'(\d),(\d{3})', r'\1<C>\2', hl_raw)
terms = [t.replace('<C>', ',').strip().lower() for t in hl_raw.split(sep) if t.strip()]
norm = lambda w: re.sub(r'[’‘`]', "'", re.sub(r"^[^\w$%]+|[^\w%]+$", '', w)).lower()
hl_terms = [[norm(x) for x in t.split()] for t in terms]

# mark highlighted word indices
hl = [False] * len(words)
glue = [False] * len(words)
nw = [norm(w) for w in words]
for tt in hl_terms:
    L = len(tt)
    for i in range(len(words) - L + 1):
        if nw[i:i + L] == tt:
            for k in range(i, i + L): hl[k] = True
            if L > 1:
                for k in range(i, i + L - 1): glue[k] = True   # keep term together

WEAK = {'a', 'an', 'the', 'to', 'of', 'and', 'or', 'in', 'on', 'at', 'for', 'your', 'my', 'is', 'are', 'with', 'by', 'it', 'that', 'this', 'like', 'so', 'but', 'from', 'as', 'be', 'into', 'their', 'our', 'we', 'you', 'i', 'if', 'when', 'because', 'then', 'than'}
# 1) clauses = runs ending in punctuation
clauses, cur = [], []
for i, w in enumerate(words):
    cur.append(i)
    if re.search(r'[.!?;:,]["\')]*$', w): clauses.append(cur); cur = []
if cur: clauses.append(cur)
# 2) units: highlighted multi-word terms stay together
def units_of(cl):
    out = []
    for k in cl:
        if out and glue[out[-1][-1]] and out[-1][-1] + 1 == k and not re.search(r'[.!?;:,]$', words[out[-1][-1]]): out[-1].append(k)
        else: out.append([k])
    return out
# 3) balanced partition of each clause (DP): even chunk sizes, never end on a weak word
merged = []
for cl in clauses:
    U = units_of(cl); n = len(U)
    best = [(0.0, -1)] + [(1e9, -1)] * n
    for e in range(1, n + 1):
        for s0 in range(e - 1, -1, -1):
            wc = sum(len(u) for u in U[s0:e]); ch = sum(len(words[k]) + 1 for u in U[s0:e] for k in u)
            if (wc > a.max_words or ch > a.max_chars + 4) and e - s0 > 1: break
            c = best[s0][0] + (wc - 3) ** 2 + 1.5 + (6 if (e < n and nw[U[e - 1][-1]] in WEAK) else 0) + (2 if wc == 1 and n > 1 else 0)
            if c < best[e][0]: best[e] = (c, s0)
    cuts, e = [], n
    while e > 0: s0 = best[e][1]; cuts.append([k for u in U[s0:e] for k in u]); e = s0
    merged += cuts[::-1]

def spoken(w):
    s = w
    s = re.sub(r'(\d+(?:,\d{3})+|\d+\.\d+|\d+)', lambda m: ' ' + num2words(float(m.group(1).replace(',', '')) if '.' in m.group(1) else int(m.group(1).replace(',', '')), lang=a.lang) + ' ', s)
    s = s.replace('%', ' percent').replace('&', ' and ').replace('$', ' dollars ').replace('/', ' ').replace('-', ' ').replace('+', ' plus ')
    s = re.sub(r'\b([A-Z]{2,5})s?\b', lambda m: ' '.join(m.group(1)), s)  # acronyms -> letters
    return s

out = []
for p in merged:
    disp = [re.sub(r'[,;:]+$', '', words[k]) if k == p[-1] else words[k] for k in p]
    disp[-1] = re.sub(r'\.+$', '', disp[-1]) if not disp[-1].endswith('...') else disp[-1]
    out.append({'text': ' '.join(disp), 'spoken': ' '.join(spoken(words[k]) for k in p),
                'hl': [j for j, k in enumerate(p) if hl[k]]})
os.makedirs(a.work, exist_ok=True)
json.dump(out, open(os.path.join(a.work, 'phrases.json'), 'w'), indent=1, ensure_ascii=False)
for i, o in enumerate(out):
    marked = ' '.join(('*' + w + '*') if j in o['hl'] else w for j, w in enumerate(o['text'].split()))
    print(f'p{i}: {marked}')
missing = [t for t, tt in zip(terms, hl_terms) if not any(nw[i:i + len(tt)] == tt for i in range(len(nw)))]
if missing: print('WARNING highlight terms not found in script:', missing)
print(f'{len(out)} phrases, {len(words)} words')
