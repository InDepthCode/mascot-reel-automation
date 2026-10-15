# Documentary collage style (`"style": "collage"`), the user's chosen DEFAULT

This is the Johnny Harris-style documentary look. Everything is a physical object on a dark wooden desk, a handheld camera travels between the objects, and red marker annotations draw themselves. `render.py` hands off to `scripts/collage.py` automatically. Example: `assets/example_spec_collage_sip.json` (approved reel; script in `assets/example_pro_sip_script.txt`).

## How to design one (do this before writing JSON)
1. **Storyboard as a camera path, not slides.** Lay the props out on the desk in reading order, roughly top-left to bottom-right, about 300–600 px apart. The camera moves between them on the spoken words. End with a pull-back that reveals the whole desk.
2. **Choose real-world props for each idea.** A fact becomes a typed document or form with highlights. A number over time becomes a hand-drawn graph-paper chart. A claim or news becomes a newspaper clipping. An aside or punchline becomes a sticky note. A big idea becomes a title strip (bold condensed type on torn paper). A warning or verdict becomes a rubber stamp. Places, people and objects become the **user's photos** (`photo`), which matter most for the look.
3. **Annotate what's being said.** Highlight the line as it's read, circle the key number, underline the claim, and draw arrows from notes to evidence. Use one annotation every 1–3 s.
4. **Overlap props a little** (a sticky on the corner of a chart, a stamp across a document). Vary rotation between −6° and +6°. Never make a perfect grid.
5. **Use real numbers and honest documents.** Mock forms are fine as illustration, but never fake a real newspaper's name or a real person's quote. Typed docs use "Rs." (the typewriter font has no ₹). Handwriting, titles and clippings support ₹.
6. **Ask the user for photos** whenever the topic has places, people or objects. Phone photos are fine: the engine turns them into black-and-white or duotone prints with borders and tape.

## World and camera
- `"world": {"w": 2400, "h": 3800, "surface": "walnut"|"cork", "plank": 520}`. The desk also extends 900 px beyond these bounds.
- `"camera": [{"at":"start","x":690,"y":720,"zoom":1.2,"rot":-1}, {"at":"p5+0.3","x":1500,"y":1520,"zoom":1.0,"dur":1.0}, ...]`. Each key eases (in-out) from the previous one over `dur`. At zoom 1 the screen shows 1080×1920 world px; 0.85–1.0 frames a whole prop, 1.2–1.6 is a push-in. The final pull-back is ~0.5. A soft swoosh plays on moves of 1.4 s or less.
- `"handheld": 1.0` sets the drift amount (0 = locked off). Use `"tail": 2–2.5` so the final reveal can breathe.

## Props (`"props": [...]`; x, y = centre in world px; `rot` in degrees; `at` = when it lands)
Common options: `enter` (`slap` default: dropped onto the desk with a shadow settle and paper sound; `slide`; `stamp`; `fade`), `until`, `scale`, `tape` (auto for doc/graph/photo/clipping), `torn` (list of sides).
- `doc`: `{"title":"STANDING INSTRUCTION - SIP","lines":["Amount: Rs. 10,000", ...],"w":720,"size":34}`. Typewriter text on paper; lines are indexable for marks.
- `clipping`: `{"kicker":"YOUR MONEY","headline":"...","dek":"...","w":780,"size":64}`. Newsprint with a serif headline; headline lines are indexable.
- `graph`: `{"w":880,"h":1020,"title":"₹10k a month at 12%","bars":[{"value":8.2,"label":"₹8.2L","x":"5 yrs","at":"p9","color":"blue|red|green"}],"max":112,"refs":[{"value":24,"at":"p17","color":"green","label":"optional"}]}`. Marker-hatched bars draw on when each is spoken. Keep ref labels off when bars sit near the ref value; use a sticky note instead.
- `sticky`: `{"text":"₹24L is yours.\nThe rest is growth.","w":360,"size":50,"color":"sticky|white"}`. Handwritten; `\n` for lines.
- `strip`: `{"text":"THE POWER OF COMPOUNDING","size":96,"w":1000,"color":"white|sticky","font":"title"}`. A title strip.
- `stamp`: `{"text":"NOT GUARANTEED","size":120,"color":"red"}`. Slams down with a thud.
- `photo`: `{"path":"/mnt/user-data/uploads/x.jpg","w":620,"treatment":"bw|duotone|color","caption":"Mumbai, 1998","chin":70,"border":22}`.

**Marks** (inside a prop, so they follow its rotation): `"marks":[{"type":"highlight|circle|underline|cross","line":1,"at":"p2"}]`. For graphs, use `"bar":3` instead of `line`. `underline` takes `"double":true`. `dur` sets the draw time. Lines boil slightly like hand animation.

**Arrows** (world space, between props): `"arrows":[{"from":[x,y],"to":[x,y],"at":"p22+0.4","bend":0.25}]`.

## Captions & sound
Captions are clean phrases on torn black paper strips at y≈1480 (`caption_size` 48, `captions:false` to hide). The sound design is paper slaps on landings, thuds on stamps, quiet marker scratches and camera swooshes. Optional music: `"music":"/mnt/user-data/uploads/track.mp3","music_gain":0.22` (auto-ducked under the voice). Only use music the user supplies.

## Speed
~5 fps on 1 CPU (≈ 6–7× the clip length). Always use `run_bg.sh` and poll. Finishing re-encodes the result to ~8–25 MB.
