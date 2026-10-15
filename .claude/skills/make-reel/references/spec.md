# spec.json reference

> **Default to `"style": "pro"`** (section 0). The user rejected the classic look (emoji, pills, bouncy pops, visualizer bars) as "AI slop". Use classic only if they explicitly ask for it.

## 0. PRO style — how premium reels are made

**Process (do this before writing elements):**
1. **Find the subject's own visual metaphor** and make it the one memorable thing. It should be a `stage` element that persists across scenes and grows with the story. Example (`assets/example_spec_pro_sip.json`): compounding shown as tree rings, one ring per year, with area ∝ money. Other ideas: a city skyline that rises as population numbers grow, a map that zooms from world to street, a single line chart that keeps drawing through every scene, a timeline spine, a clock face.
2. **Palette: 4–7 named hex colours grounded in the subject**, never a generic default. Set `palette`: `bg`, `bg2` (light lift), `ink` (text), `muted`, `dim`, `accent` (hero numbers), `accent2`. Examples: finance → forest #0F2A22 + brass #D9A441; mystery → oxblood/ink; tech → graphite blue + signal cyan; sport → turf + chalk. **Avoid the AI tells:** near-black with a single acid-green or vermilion accent; cream + terracotta; tinted #0B0B0B.
3. **Type:** `fonts.display` = Fraunces (default) or Newsreader; `fonts.text` = BricolageGrotesque (default; it has ₹). Headlines use the display face, captions and small text use the text face. Sentence case only: no ALL-CAPS labels, no monospace, no "A · B · C" meta strings, and don't accent a single word inside a headline (colour whole lines instead).
4. **Layout:** left-aligned editorial at x≈96. The headline block sits at y≈300–700, the stage visual at y≈750–1400, karaoke captions at y≈1470. Give each scene one idea and lots of negative space.
5. **Motion:** headlines slide up out of line masks (expo easing, staggered with `line_at` on the spoken words), and numbers count with in-out easing. The camera drifts slowly (`drift`), and scenes exit by drifting up. No bounce, no emoji, no pills, no visualizer. Pro sound is soft swells on cuts and a low tone on hero numbers and ring reveals.
6. **Copy on screen** should complement the voice rather than repeat it. Use short editorial lines ("One ring for every year. Area is money."), and real numbers in Indian format (₹8.2 lakh, ₹1 crore).
7. **Be accurate.** Compute chart and ring values from real maths or data. If the script's claim is only true under some reading, show the reading that is true and label it.

**Pro-only top-level keys:** `style:"pro"`, `palette{}`, `fonts{display,text,display_weight,text_weight}`, `drift` (0.03), `stage[]` (persistent elements with their own `at`/`until`), `caption_size` (48), `caption_highlight` (accent), `grain` (0 = off; Instagram smears temporal grain and it bloats files). Pro disables chip, cta pill, visualizer and face_emoji, so put any CTA in as a headline or text line.

**Pro elements:**
- `headline`: `{"type":"headline","lines":["line one",[["line two","muted"]]],"x":96,"y":330,"size":76,"line_at":["p5","p6"],"font":"display|text","align":"left|center"}`. Each line rises out of its own mask. A line can be a string or `[[text,colour],...]`.
- `number`: `{"type":"number","value":10000,"prefix":"₹","x":92,"y":500,"size":230,"color":"accent","dur":1.1,"at":"p2"}`. Indian grouping by default (1,00,000); `grouping:"western"` switches it.
- `rings`: `{"type":"rings","x":430,"y":1095,"radius":300,"values":[...one per ring...],"ghost_at":"p4","reveal":[{"upto":5,"at":"p7","dur":1.6},...],"inner":{"value":24,"at":"p17","color":"accent2"},"bands":[{"from":16,"to":20,"at":"p20","color":"accent"}],"callouts":[{"ring":5,"text":"₹8.2 lakh","sub":"5 years","angle":-55,"at":"p9","until":"p11"}]}`. Ring area ∝ value. `ghost_at` draws faint outlines early to foreshadow. Callouts take `ring` or `value`, plus `angle`, `color` and `size`; keep the label text short (the right edge is at x≈1040).
- Classic elements (`chart`, `map`, `timeline`, `text`, ...) also work in pro and pick up the palette and fonts. Avoid `emoji`, `pill` and `card` in pro.

`spec.json` describes everything that appears in the **top panel** (1080×880 px), plus the face-card punch-ins, face emojis, and the CTA. The engine handles the bottom face card, captions, audio, and SFX automatically.

## Contents
1. Top-level fields
2. Time references
3. Coordinates & safe zone
4. Element types (with every option)
5. States (change an element over time)
6. Design playbook (how to make it look like the approved reel)
7. Long videos (2–10 min)
8. AUDIO mode (full-screen animation)

---

## 1. Top-level fields

| field | default | meaning |
|---|---|---|
| `chip` | none | small label at top of panel, e.g. `"SYSTEM DESIGN  ·  SCALING"`. 2–4 words, caps, topic of the video |
| `theme` | `"navy"` | background: `navy`, `black`, `purple`, `green`, `mystery` (near-black, red glow, vignette, film grain, no grid, red chip). Pair mystery with `"caption_highlight":"red"` and `"visualizer":{"color":"blood"}` |
| `accent` | `"cyan"` | colour of the thin line between panels |
| `caption_highlight` | `"yellow"` | keyword colour in captions |
| `caption_size` | 60 | caption font size |
| `caption_pos` | `"seam"` | `"seam"` (straddles the panel divider, approved look) or `"bottom"` (uses `caption_y`, default 1480) |
| `cta` | `{"text":"+  FOLLOW for more","last":1.8}` | pulsing pill shown for the last N seconds at y=815. Use the user's handle if given: `"+  FOLLOW @handle"`. Set `null` for clips under ~6 s |
| `punch` | `[]` | face-card zoom punch-ins: `[["p0","p1.end"], ...]`, 8 % zoom inside the card. Use on the hook, on punchlines, and on the CTA. Typically one every 5–10 s |
| `punch_amount` | 0.08 | zoom strength |
| `face_emoji` | `[]` | `[{"at":"p4","e":"💸"}]`: emoji pops beside the face card for 1.4 s. Use 1 per ~6–8 s, only on emotionally strong words |
| `scenes` | required | list of scenes (below) |
| `trim` | auto | `[start, end]` seconds in the source. Default: speech start − 0.3 s to speech end + 0.6 s |
| `lead_in` / `tail` | 0.3 / 0.6 | padding used by auto-trim |
| `sfx` | true | auto pops on element entrances, whooshes on scene cuts, thuds on `shake`/`strike` |
| `grid` | true | faint grid in the background |
| `grade` | `eq=contrast=1.06:saturation=1.15:gamma=0.97` | ffmpeg colour grade for the face video |
| `x264_preset` / `crf` | `superfast` / 21 | encoder speed/quality. `veryfast` makes files ~2× smaller but renders ~15 % slower |

### Scenes
```json
{"start": "p6", "elements": [ ... ]}
```
A scene is shown from its `start` until the next scene starts. The old scene clears out in ~0.15 s and the new elements pop in on their own timings. The first scene should use `"start": "start"`.

## 2. Time references
Used by `start`, `at`, `until`, `value_at`, `punch`, `face_emoji`, `states[].at`:
- `"p12"`: phrase 12 starts being spoken (phrase numbers come from `make_phrases.py` output)
- `"p12.end"`: phrase 12 ends
- `"p12+0.3"`, `"p12-0.2"`, `"p12.end+0.5"`: offsets in seconds
- `"start"`, `"end-2"`: trimmed clip start/end
- a plain number = absolute seconds in the source video

**Sync rule:** a visual should appear **on the word it illustrates**: `at` = the phrase containing that word. Never early.

## 3. Coordinates & safe zone
- Panel is 1080 wide × 880 tall; `x`,`y` are the element **centre** (unless `anchor:"left"`).
- y < 150 is covered by Instagram's top bar. The chip sits at y=200. The CTA sits at y=815.
- Keep content at **y 250–840**, **x 60–1020**.
- Typical rows: title y≈300–320, second title line y≈420–430, diagram middle y≈560–640, footer/labels y≈780–830.
- Typical columns for a 3-node diagram: x = 115–170 / 540 / 900–960.

## 4. Element types

Common options for all: `at` (default = scene start), `until` (fade out at that time), `x`, `y`, `anim` (`pop` default, `slide` = rise up + fade, `fade`, `none`), `states` (§5).

### text
```json
{"type":"text","parts":[["STOP","red"],["adding","white"]],"x":540,"y":320,"size":92,"at":"p0"}
```
`parts` = list of [text, colour]; or `text` + `color`. `size` (default 64), `weight` (`"medium"` for lighter), `max_w` (wrap width, default 980), `anchor` (`center`/`left`). Inline emoji in text works (`"FIX ✅"`). Titles are 80–98 px. Labels are 26–34 px.

### emoji
```json
{"type":"emoji","e":"🔒","x":830,"y":585,"size":100,"at":"p9"}
```
`size` px. `bob:true` = gentle up-down loop (hero icons). `float:true` = rises and fades, looping (money flying, bubbles).

### pill
```json
{"type":"pill","label":"LOCKED","x":830,"y":425,"size":34,"fg":"white","bg":"red","at":"p9"}
```
`fg`, `bg`, `outline`, `pulse:true`. Short tags: "< 1 ms", "100%", "WRONG", "NEW".

### db  (database cylinder)
```json
{"type":"db","x":830,"y":610,"w":200,"h":235,"color":"blue","label":"SQL DB","at":"p6"}
```
`emoji` overlays an icon on it. Use states to turn it red/locked.

### box  (labelled node / component)
```json
{"type":"box","title":"Redis","sub":"in-memory cache","emoji":"⚡","color":"redis","x":540,"y":470,"w":350,"h":128,"at":"p14"}
```
`color` fill, `outline`, `fg`, `size` (title, default 42), `sub_size`, `radius`. Works for any concept node: "Bank", "Your Brain", "API Gateway", "Step 1".

### flow  (animated dots travelling from → to)
```json
{"type":"flow","from":[190,570],"to":[360,470],"color":"cyan","rate":1.6,"n":4,"at":"p15"}
```
`rate` speed, `n` dots, `dot` radius, `square:true` (packets/messages). It draws the line first, then the dots. It is always animating, so use it only where movement means something (traffic, money flow, data).

### counter
```json
{"type":"counter","to":100000,"after":[["users","white"]],"x":540,"y":310,"size":98,"at":"p6"}
```
Counts up over `dur` (1.6 s). Options: `from`, `prefix` (`"$"`), `suffix` (`"%"`, `"x"`), `decimals`, `color` (default yellow). Use it on every number the speaker says.

### gauge  (progress / load bar)
```json
{"type":"gauge","label":"DISK I/O","x":600,"y":830,"w":520,"to":100,"at":"p10"}
```
Fills to `to`% over `dur`, colour moving from `color_from` to `color_to` (cyan to red). `show_pct`.

### card  (key → value row)
```json
{"type":"card","emoji":"⚡","key":"Cache","value":"READ spikes","color":"cyan","x":540,"y":430,"at":"p22","value_at":"p22+0.6"}
```
880×170 by default (`w`,`h`). The value appears at `value_at`. Use cards for recaps and comparisons, stacked at y≈430 and 650.

### bullets
```json
{"type":"bullets","x":90,"y":330,"gap":95,"size":48,"items":[
  {"text":"Sleep 8 hours","emoji":"😴","at":"p3"},
  {"text":"Walk 10k steps","emoji":"🚶","at":"p5"}]}
```
Left-aligned list. Each item slides in on its own `at`. Use it for "3 tips" or "steps" content. Fit at most 5 items per scene.

### chart  (animated bar / line graph)
```json
{"type":"chart","kind":"bar","x":540,"y":760,"w":940,"h":640,"labels":["5y","10y","15y","20y"],"values":[8.2,23,50,99.9],"prefix":"₹","suffix":"L","colors":{"3":"green"},"at":"p7"}
```
Bars grow left to right with counting value labels. **`bar_at`** (list of time refs, one per bar) makes each bar grow when its number is spoken; **`value_text`** (list) sets the final label per bar (e.g. `"₹1 Cr"`). `kind:"line"` draws the line progressively with a soft fill and labels the last value (`end_color`). Options: `color`, `colors` (per-bar, by index as a string), `max`, `decimals`, `dur`, `value_labels`, `label_size`, `value_size`. Use it for growth, comparisons, rankings, and before/after numbers.

### map  (world map: highlight, zoom, pins)
```json
{"type":"map","x":540,"y":720,"w":1000,"h":620,"at":"p0",
 "highlight":[{"iso":"JPN","color":"red","at":"p1"},{"iso":["CHN","KOR"],"color":"orange","at":"p3"}],
 "focus":[{"iso":"JPN","pad":8,"at":"p2"}],
 "pins":[{"lon":139.7,"lat":35.7,"label":"Tokyo","at":"p3"}]}
```
Countries use ISO-3 codes (IND, USA, GBR, CHN, JPN, RUS, BRA, AUS, FRA, DEU, PAK, SAU, ARE, EGY...). `focus` smoothly zooms to countries (`iso`, `pad` in degrees) or `"bbox":[lon0,lat0,lon1,lat1]`. Several focus steps can tell a journey. `pins` take lon/lat plus an optional label. Styling: `land`, `border`. Shapes are 1:110m Natural Earth, so they suit countries and regions, not cities' streets. It is the go-to element for geography, history, and "why this happens" topics.

### timeline
```json
{"type":"timeline","x":150,"y":420,"length":640,"color":"cyan","items":[
  {"date":"2004","text":"Debut for Barcelona","at":"p20"},
  {"date":"2012","text":"91 goals in a year","at":"p22","color":"yellow"}]}
```
Vertical by default (`x` = the line's x; text appears to its right). Use `orient:"horizontal"` (x = centre) for 3–5 short items. The line grows to each item as it is spoken. Options: `size`, `date_size`, `text_w`. Use it for history, careers, mysteries, and company stories.

### note  (pinned paper note, evidence board)
```json
{"type":"note","text":"Tent cut open FROM THE INSIDE","x":300,"y":420,"w":400,"rotate":-4,"emoji":"🥾","at":"p6"}
```
A cream paper card with a red pin and a shadow. Options: `bg`, `fg`, `pin`, `size`. The pin sits at about (x, y − note height/2 + 10).

### string  (red string linking points)
```json
{"type":"string","points":[[300,330],[790,480],[340,780]],"at":"p11"}
```
Draws progressively through the points, with pins. Point it at note pins for the "connecting the clues" moment.

### Typewriter text
Any `text` with `"anim":"type"` types out with a blinking cursor and soft key-click SFX. `type_dur` overrides the speed (default ≈0.045 s per character, max 2.5 s). Use it for dates, case files, quotes, and dramatic one-liners.

### strike
```json
{"type":"strike","from":[190,540],"to":[890,740],"color":"red","width":12,"at":"p5"}
```
Draws a line across a scene to mean "wrong / don't".

### image  (user-supplied picture)
```json
{"type":"image","path":"/mnt/user-data/uploads/chart.png","w":700,"x":540,"y":560,"at":"p8"}
```
Rounded corners (`radius`). Only use files the user uploaded.

## 5. States
Any element can change over time. Each state's fields override the element's, from `at` onward:
```json
"states":[{"at":"p9","color":"red","emoji":"🔒","shake":true}]
"states":[{"at":"p19","title":"Kafka"}]
"states":[{"at":"p9","color":"red","rate":3}]
```
`shake:true` shakes for 0.6 s and adds a thud SFX. Use states to tell before/after stories inside one scene.

Colours: `paper ink blood white muted yellow cyan red green orange purple pink blue redis dark black gray`, `"#RRGGBB"`, `"#RRGGBBAA"`, or `"white/40"` (40 % opacity).

## 6. Design playbook

These are the rules that made the approved reel work:

1. **One scene per idea.** Hook → problem → solution → recap → CTA. A scene usually covers 1–3 sentences (5–12 s).
2. **The hook scene shows the claim as big text** (2 lines, 90 px, one red or yellow keyword), then illustrates it with icons that pop in on the words.
3. **New motion every 1–3 s.** Something should appear or change roughly every phrase or two: an icon pop, a counter, a state change, a pill. Long stretches with nothing new feel dead.
4. **Show, don't repeat.** Captions already carry the words, so the top panel should *visualise* them: diagrams, icons, numbers, before/after. Use at most one short title per scene.
5. **Colour semantics.** Red = problem/bad, green = fix/good, yellow = numbers & key terms, cyan = data/neutral, orange = secondary path.
6. **Before → after.** For problem/solution content, the problem scene ends in red (locked, 100 %, strike-through) and the fix scene opens with "The FIX ✅" and green elements.
7. **Recap cards** (`card`) for the 1–2 sentence summary, then a **SAVE THIS 🔖** scene (bobbing bookmark + big text) if the script says save, share, or comment.
8. **Every number → counter.** **Every named tool or thing → box or emoji.** **Every "vs" → two cards or two columns.**
9. **Keep it uncluttered:** at most ~8 elements visible at once, nothing overlapping, and labels at 26 px or larger.
10. **Topic vocabulary:** geography uses `map` (highlight → focus → pins) + counters + flag emojis 🇯🇵; history, mystery, and true crime use the `mystery` theme + typewriter dates + `note`/`string` evidence boards + `timeline`; finance and stats use `chart` (bar for comparisons, line for growth); sports uses `timeline` for careers + `chart` for stat comparisons + `card` for head-to-head; tech uses db/box/flow/gauge; money uses 💸💰📈📉 + counter with `$`; fitness uses 💪🔥⏱️ + bullets + gauge; mindset or story uses big text + emoji + bullets; tutorials use numbered bullets ("1.", "2.") + box per step.
11. Punch-ins go on the hook, the "but/instead" turn, and the CTA. Face emojis go on 3–6 strongest emotional words.

## 7. Long videos (2–10 min)
- Expect roughly one scene per 6–12 s, so a 10-min video has ~50–90 scenes. Write the spec section by section (one per script paragraph); don't try to hold it all at once.
- Reuse patterns: a "point N" scene = big number title (`"#3"` + heading) + bullets or a box diagram, then a short recap card.
- Preview 1–2 frames per minute of video, plus every scene that has a complex diagram.
- Render time is about 2.1× the clip length on 1 CPU (≈14 fps), so 10 min takes ≈21 min. Always render with `run_bg.sh` and poll.

## 8. AUDIO mode (full-screen animation)
When the input is audio only, the panel is the **whole 1080×1920 canvas** and there is no face card. Everything above still applies, with these differences:

**Zones (y):** chip 200 · **content 260–1120** · visualizer ≈1235 · captions ≈1390 · 1550+ is covered by Instagram's caption/username overlay, so leave it empty. The CTA defaults to y=1130.

**Scale up:** there is ~1.6× more vertical room than VIDEO mode, so use bigger visuals. Titles 100–120 px, hero emojis 160–220 px, boxes ~420×150, db ~240×280, cards 900×190 (`w`,`h`), labels 30–38 px. Use the height: stack title (y≈330) → diagram (y≈600–900) → footer pill/gauge (y≈1050–1100).

**Fill the screen:** with no face to look at, the animation carries the whole reel. Aim for something new every ~1–2 s, prefer scenes with a big visual (diagram, counter, hero emoji with `bob`) over text alone, and use more scenes (one per sentence is fine).

**Punch-ins** gently zoom the whole scene (content zone only). Use them on the hook and punchlines.

**`face_emoji`** pops appear at the left end of the visualizer. Use them sparingly.

**Visualizer options:** `"visualizer": {"color":"cyan","bars":26,"height":90,"y":1235}` or `false` to hide. It's on by default in AUDIO mode, off in VIDEO mode.

Typical AUDIO-mode coordinates for a 3-node diagram: users x≈130 / middle boxes x≈540 at y≈640 and y≈920 / db x≈950 at y≈780.
