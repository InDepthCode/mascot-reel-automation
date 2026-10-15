#!/usr/bin/env python3
"""probe.py VIDEO WORKDIR  -> WORKDIR/probe.json + WORKDIR/contact.jpg
Reports display size (rotation-aware), duration, fps, speech start/end and long pauses."""
import json, os, re, subprocess, sys
video, work = sys.argv[1], sys.argv[2]
os.makedirs(work, exist_ok=True)
pj = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', video],
                               capture_output=True, text=True).stdout)
# audio-only inputs (mp3/m4a/wav/voice notes, or cover-art-only video streams) -> full animated mode
vs = next((s for s in pj['streams'] if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
has_video = vs is not None
has_audio = any(s['codec_type'] == 'audio' for s in pj['streams'])
if not has_audio and not has_video: sys.exit('no audio or video stream found')
w, h = (int(vs['width']), int(vs['height'])) if has_video else (1080, 1920)
rot = 0
for sd in (vs or {}).get('side_data_list', []):
    if 'rotation' in sd: rot = int(sd['rotation'])
rot = int((vs or {}).get('tags', {}).get('rotate', rot))
if abs(rot) % 180 == 90: w, h = h, w
dur = float(pj['format']['duration'])
num, den = ((vs or {}).get('avg_frame_rate') or '30/1').split('/')
fps = float(num) / float(den or 1) if float(den or 1) else 30.0
speech_start, speech_end, pauses = 0.0, dur, []
if has_audio:
    err = subprocess.run(['ffmpeg', '-v', 'info', '-i', video, '-vn', '-af', 'silencedetect=n=-35dB:d=0.35', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r'silence_start: ([\d.]+)', err)]
    ends = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', err)]
    sil = list(zip(starts, ends + [dur] * (len(starts) - len(ends))))
    # voiced segments = gaps between silences; ignore short/quiet blips (taps, clicks, breaths)
    edges = [0.0] + [x for ab in sil for x in ab] + [dur]
    voiced = [(edges[k], edges[k + 1]) for k in range(0, len(edges), 2) if edges[k + 1] - edges[k] > 0.01]
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', video, '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-'], capture_output=True).stdout
    import numpy as np
    pcm = np.frombuffer(raw, np.int16).astype(np.float32)
    rms = lambda a_, b_: float(np.sqrt(np.mean(pcm[int(a_ * 8000):max(int(a_ * 8000) + 1, int(b_ * 8000))] ** 2)) + 1e-9)
    if voiced:
        ref = np.median([rms(a_, b_) for a_, b_ in voiced if b_ - a_ >= 0.5] or [rms(*voiced[0])])
        real = [(a_, b_) for a_, b_ in voiced if b_ - a_ >= 0.45 and rms(a_, b_) >= 0.35 * ref]
        if real:
            speech_start, speech_end = real[0][0], real[-1][1]
            for a_, b_ in voiced:  # pull in quieter/short word tails that sit right next to real speech
                if rms(a_, b_) >= 0.1 * ref:
                    if b_ < speech_start and speech_start - b_ < 0.6: speech_start = a_
            for a_, b_ in voiced:
                if rms(a_, b_) >= 0.1 * ref and a_ > speech_end and a_ - speech_end < 0.6: speech_end = b_
    pauses = [(round(a_, 2), round(b_, 2)) for a_, b_ in sil if a_ > speech_start + 0.1 and b_ < speech_end - 0.1]
info = dict(video=os.path.abspath(video), has_video=has_video, mode='video' if has_video else 'audio',
            width=w, height=h, duration=round(dur, 3), fps=round(fps, 2), codec=vs['codec_name'] if has_video else None, has_audio=has_audio, speech_start=round(speech_start, 2),
            speech_end=round(speech_end, 2), pauses=pauses)
json.dump(info, open(os.path.join(work, 'probe.json'), 'w'), indent=1)
if has_video:
    n = 10 if dur > 5 else max(1, int(dur * 2))
    step = dur / n
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', video, '-vf', f'fps={1/step},scale=240:-2,tile={min(n,5)}x{(n+4)//5}',
                    '-frames:v', '1', os.path.join(work, 'contact.jpg')])
print(json.dumps({k: v for k, v in info.items() if k != 'pauses'}, indent=1))
print(f"{len(pauses)} pauses; mode={info['mode']}" + (f'; contact sheet: {work}/contact.jpg' if has_video else ' (audio only -> full-screen animation)'))
