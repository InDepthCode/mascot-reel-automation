---
name: reel-script
description: Write and produce an Instagram Reel with a talking mascot from just a topic, following a retention playbook (hook, proof, comment prompt, share CTA), with timed info cards, a grid-safe cover and a caption. Use when the user wants a reel, short, script, hook, caption or "a video about X" made with a mascot from this repo.
---

# Reel script + production

Goal: the user gives a topic (or a rough script); you hand back a finished 1080x1920 mp4, a cover and a caption.
Ask only what you cannot decide yourself. Never invent facts: every number, name and claim must be checkable.

## 1. Script (30-40 s = 75-105 words, the mascot speaks ~2.5 words/s)

- **Hook (0-3 s):** first sentence under 12 words, a bold claim or a what/how/why question. No "hey guys", no intro.
  The payoff starts within 1.5 s. Never bait and switch.
- **Proof (3-10 s):** a concrete number, name or before/after. A claim with nothing behind it loses people here.
- **Middle:** new information every 1.5-2 s. Short sentences; the full stops are the pauses.
- **Comment prompt around 25-30 s** and **share CTA at the end** ("send this to a [specific person]"). Give options to pick from.
- Write it as it is spoken: numbers as words ("two hundred milliseconds"), no symbols, no emojis, no hyphen chains.
- Save it as `scripts/<name>.txt` (one paragraph).

## 2. Cards (the B-roll layer)

`cards.json`, one card per information beat, 4-7 per reel. A card appears under the mascot's chin when its word is spoken:

```json
[{"at": "SnapStart", "dur": 2.4, "title": "AWS Lambda SnapStart", "sub": "optional second line", "image": "path/to/proof.png"}]
```

- `at` = a word from the script (first occurrence; add `"after": 12.0` to pick a later one) or a number of seconds.
- Priority: real proof (screenshot, UI, code, tweet) > a number ("< 200 ms") > a name > a concept title. Stay on the face
  when a card would add nothing: do not add a card just because 2 s passed.
- Titles up to 4 words; numbers get their own card. No emojis. Real logos/screenshots only if the user supplied them or you
  can show where they came from; no stock footage.
- Check every `at` word really appears in the script.

## 3. Produce

1. Voice: the mascot's `VOICE` provider. `clone` needs `HF_TOKEN` in `.env` for enough free quota; if it fails, ask for a
   recording and pass `--audio`.
2. `python make.py video NAME --script scripts/x.txt --cards cards.json` (a long render: run it in the background).
3. `python make.py sheet NAME <take dir> <card times...>` and READ `sheet.png`: cards readable, nothing over the mouth,
   captions right. Fix and `python make.py render NAME <take dir> --cards cards.json` (no new voice needed).
4. `python make.py cover NAME <take dir> "2-3 WORD QUESTION"` and read `cover_grid.png`.
5. Caption: hook line, one line of context, the comment question, 5-8 hashtags.

## 4. Report back

Output paths, raw length, which details are illustrative or need verifying, and sources for every fact.

## Learned rules

When the user gives feedback, add it here as a one-line rule so the next reel starts better.
