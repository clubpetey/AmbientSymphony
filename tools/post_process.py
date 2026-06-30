#!/usr/bin/env python3
"""Deterministic audio post-processing for flagged clips (beta feedback Wave 2).

Pure numpy + soundfile (no scipy). Operations:
  highshelf(cutoff, gain_db) - reduce energy above `cutoff` by gain_db (tames harsh highs)
  lowpass(cutoff)            - hard high cut (windowed-sinc FIR)
  normalize(target)          - peak-normalize down to `target` (fixes peaking/distortion)
  reverb()                   - add discrete decaying echoes (cave echo for the bigdrips)

Originals are backed up to build/eq_backup/ before being overwritten. Re-runnable: restore from
the backup first if you want to reprocess from the source.
"""
import os, shutil
import numpy as np
import soundfile as sf

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SND = os.path.join(ROOT, "assets", "ambientsymphony", "sounds")
BACKUP = os.path.join(ROOT, "build", "eq_backup")

HS, LP, NORM, REV = "highshelf", "lowpass", "normalize", "reverb"

JOBS = {
    "biome/jungle/insect_wall_night2": [(HS, 4000, -11)],
    "biome/desert/heat_day2":          [(HS, 4500, -9)],
    "day/insect/pondinsect_2":         [(HS, 4000, -10)],
    "night/pond/pondnight_5":          [(HS, 4500, -9)],
    # special/aurora/shimmer2: almost pure HF content -> EQ leaves it near-silent; REGENERATE instead.
    "special/hotspring/bubbling":      [(HS, 3500, -11)],             # loud hiss -> tame highs
    "day/birds/bird_7":                [(NORM, 0.6)],                 # peaking
    "biome/alpine/eagle_1":            [(NORM, 0.55)],                # distortion from peaking
    "environment/bigdrip":             [(REV,)],                      # missing cave echo
    "environment/bigdrip2":            [(REV,)],
}
for i in range(1, 9):
    JOBS[f"insect/insect_{i}"] = [(HS, 5000, -7)]   # grating if repeated -> gentle high cut


def fir_lowpass(x, sr, cutoff, taps=193):
    fc = cutoff / sr
    n = np.arange(taps) - (taps - 1) / 2.0
    h = np.sinc(2 * fc * n) * np.hamming(taps)
    h /= h.sum()
    return np.convolve(x, h, mode="same")


def apply_op(x, sr, op):
    kind = op[0]
    if kind == LP:
        return fir_lowpass(x, sr, op[1])
    if kind == HS:
        lp = fir_lowpass(x, sr, op[1])
        g = 10 ** (op[2] / 20.0)
        return lp + g * (x - lp)
    if kind == NORM:
        peak = float(np.max(np.abs(x))) or 1.0
        return x * (op[1] / peak)
    if kind == REV:
        out = x.astype(np.float64).copy()
        for ms, g in [(55, 0.5), (115, 0.33), (200, 0.2), (310, 0.12), (450, 0.07)]:
            d = int(ms / 1000.0 * sr)
            if d < len(x):
                out[d:] += g * x[: len(x) - d]
        return out
    raise ValueError("unknown op " + kind)


def process(rel, ops):
    src = os.path.join(SND, *rel.split("/")) + ".ogg"
    if not os.path.isfile(src):
        print("  MISSING", rel); return False
    # backup
    bdst = os.path.join(BACKUP, *rel.split("/")) + ".ogg"
    os.makedirs(os.path.dirname(bdst), exist_ok=True)
    if not os.path.exists(bdst):
        shutil.copy2(src, bdst)

    x, sr = sf.read(src)
    mono = x.ndim == 1
    chans = [x] if mono else [x[:, c] for c in range(x.shape[1])]
    out = []
    for ch in chans:
        y = ch.astype(np.float64)
        for op in ops:
            y = apply_op(y, sr, op)
        out.append(y)
    y = out[0] if mono else np.stack(out, axis=1)
    # safety peak-normalize to avoid clipping (reverb/shelf can add level)
    peak = float(np.max(np.abs(y)))
    if peak > 0.97:
        y = y * (0.95 / peak)
    y = y.astype(np.float32)

    ch = 1 if y.ndim == 1 else y.shape[1]
    with sf.SoundFile(src, "w", samplerate=sr, channels=ch, format="OGG", subtype="VORBIS") as f:
        b = sr
        for i in range(0, len(y), b):
            f.write(y[i:i + b])
    print("  ok  %-34s %s" % (rel, "+".join(o[0] for o in ops)))
    return True


if __name__ == "__main__":
    print("Post-processing %d clips (backups -> build/eq_backup/)" % len(JOBS))
    done = 0
    for rel, ops in JOBS.items():
        if process(rel, ops):
            done += 1
    print("done: %d/%d" % (done, len(JOBS)))
