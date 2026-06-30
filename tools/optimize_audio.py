#!/usr/bin/env python3
"""Audio size optimization:
  --loop <rel> <seconds>   make a seamless N-second loop from a long clip (equal-power crossfade)
  --mono                   down-mix every stereo .ogg in the asset tree to mono (saves ~half size)
Runs both by default with the project's chosen settings.
"""
import os, glob, sys
import numpy as np
import soundfile as sf

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SND = os.path.join(ROOT, "assets", "ambientsymphony", "sounds")

def write_ogg(path, y, sr):
    ch = 1 if y.ndim == 1 else y.shape[1]
    with sf.SoundFile(path, "w", samplerate=sr, channels=ch, format="OGG", subtype="VORBIS") as f:
        b = sr
        for i in range(0, len(y), b):
            f.write(y[i:i + b])

def make_loop(rel, seconds, xfade=3.0, skip_intro=60.0):
    """Seamless N-second loop: take N+xf samples, crossfade the tail back over the head so the
    wrap point is continuous in the source (both seams are adjacent samples)."""
    src = os.path.join(SND, *rel.split("/")) + ".ogg"
    x, sr = sf.read(src)
    mono = x.ndim == 1
    N, xf = int(seconds * sr), int(xfade * sr)
    total = N + xf
    if len(x) <= total:
        print("  loop: clip shorter than requested loop; left unchanged"); return
    start = int(min(skip_intro * sr, (len(x) - total) // 4))
    if start + total > len(x):
        start = len(x) - total
    chunk = x[start:start + total].astype(np.float64)
    t = np.linspace(0, 1, xf)
    fin, fout = np.sqrt(t), np.sqrt(1 - t)          # equal-power
    if not mono:
        fin, fout = fin[:, None], fout[:, None]
    loop = chunk[:N].copy()
    loop[:xf] = chunk[-xf:] * fout + chunk[:xf] * fin
    before = os.path.getsize(src)
    write_ogg(src, loop.astype(np.float32), sr)
    print("  loop %-32s %.0fs -> %.0fs   %.0f KB -> %.0f KB" %
          (rel, len(x) / sr, len(loop) / sr, before / 1024, os.path.getsize(src) / 1024))

def downmix_all():
    saved = 0
    n = 0
    for f in sorted(glob.glob(os.path.join(SND, "**", "*.ogg"), recursive=True)):
        x, sr = sf.read(f)
        if x.ndim == 1:
            continue
        before = os.path.getsize(f)
        write_ogg(f, x.mean(axis=1).astype(np.float32), sr)
        saved += before - os.path.getsize(f)
        n += 1
    print("  down-mixed %d stereo clips to mono, saved %.1f MB" % (n, saved / 1e6))

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or "--loop" in args:
        make_loop("biome/forest/forest_night", 180.0)
    if not args or "--mono" in args:
        downmix_all()
    print("done")
