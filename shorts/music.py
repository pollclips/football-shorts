"""Muziek onder de video.

- Staan er audiobestanden in de map music/ (bv. nummers uit de gratis YouTube Audiotheek),
  dan kiezen we er elke dag één (wisselend) en maken we hem even lang als de video.
- Is de map leeg, dan genereren we zelf een rechtenvrije beat die elke dag een beetje anders klinkt.
"""
import hashlib
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "music"
SR = 44100
EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}


def _seed(key):
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def from_library(key, duration, out_path):
    tracks = sorted(p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in EXTS) if MUSIC_DIR.exists() else []
    if not tracks:
        return None
    track = tracks[_seed(key) % len(tracks)]
    fade_start = max(0.0, duration - 1.2)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(track), "-t", f"{duration:.2f}",
           "-af", f"afade=t=in:d=0.3,afade=t=out:st={fade_start:.2f}:d=1.2,loudnorm=I=-14:TP=-1.5:LRA=11",
           "-ar", str(SR), "-ac", "2", str(out_path)]
    subprocess.run(cmd, check=True)
    return track.name


def synth(key, duration, transitions, out_path):
    rng = np.random.default_rng(_seed(key))
    n = int(SR * duration)
    out = np.zeros(n, np.float32)
    bpm = float(rng.integers(112, 127))
    beat = 60 / bpm
    bar = beat * 4
    semis = int(rng.integers(-3, 4))
    tr = 2 ** (semis / 12)
    progressions = [
        ([55.0, 43.65, 65.41, 49.0], [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [261.63, 329.63, 392.0], [196.0, 246.94, 293.66]]),
        ([55.0, 49.0, 43.65, 41.2], [[220.0, 261.63, 329.63], [196.0, 246.94, 293.66], [174.61, 220.0, 261.63], [164.81, 207.65, 246.94]]),
        ([43.65, 65.41, 49.0, 55.0], [[174.61, 220.0, 261.63], [261.63, 329.63, 392.0], [196.0, 246.94, 293.66], [220.0, 261.63, 329.63]]),
    ]
    roots, chords = progressions[int(rng.integers(0, len(progressions)))]

    def add(sig, start):
        s = int(start * SR)
        if s >= n or s < 0:
            return
        e = min(n, s + len(sig))
        out[s:e] += sig[: e - s]

    kt = np.arange(int(0.35 * SR)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(45 + 90 * np.exp(-kt * 30)) / SR) * np.exp(-kt * 9) * 0.9
    hn = rng.standard_normal(int(0.06 * SR))
    hn = hn - np.convolve(hn, np.ones(6) / 6, mode="same")
    hat = hn * np.exp(-np.arange(len(hn)) / SR * 70) * 0.12
    cn = np.convolve(rng.standard_normal(int(0.18 * SR)), np.ones(3) / 3, mode="same")
    clap = cn * np.exp(-np.arange(len(cn)) / SR * 22) * 0.22

    k, tb = 0, 0.0
    while tb < duration:
        if tb >= 1.0 or k % 2 == 0:
            add(kick, tb)
        add(hat, tb + beat / 2)
        if k % 2 == 1 and tb > 3.4:
            add(clap, tb)
        k += 1
        tb += beat

    for ci in range(int(duration / (bar * 2)) + 1):
        c0 = ci * bar * 2
        idx = ci % 4
        for b8 in range(16):
            ln = int(beat / 2 * SR * 0.9)
            lt = np.arange(ln) / SR
            f = roots[idx] * tr * (2 if b8 % 4 == 3 else 1)
            env = np.minimum(1, lt * 200) * np.exp(-lt * 5)
            add((np.sin(2 * np.pi * f * lt) + 0.3 * np.sin(4 * np.pi * f * lt)) * env * 0.32, c0 + b8 * beat / 2)
        pl = int(bar * 2 * SR)
        pt = np.arange(pl) / SR
        penv = np.minimum(1, pt / 0.6) * np.minimum(1, (pl / SR - pt) / 0.6)
        pad = sum(np.sin(2 * np.pi * f * tr * pt + 0.3 * np.sin(2 * np.pi * 5 * pt)) for f in chords[idx]) / 3
        add(pad * penv * 0.07, c0)

    wt = np.arange(int(0.5 * SR)) / SR
    wn = np.convolve(rng.standard_normal(len(wt)), np.ones(12) / 12, mode="same")
    whoosh = wn * np.sin(np.pi * wt / 0.5) ** 2 * 0.35
    for s in transitions[1:]:
        add(whoosh, s - 0.3)

    fl = int(1.2 * SR)
    out[-fl:] *= np.linspace(1, 0, fl)
    out = np.tanh(out * 1.2)
    out = out / (np.max(np.abs(out)) + 1e-9) * 0.7
    pcm = (out * 32767).astype(np.int16)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(np.stack([pcm, pcm], 1).tobytes())
    return f"synth {int(bpm)} bpm"


def make_music(key, duration, transitions, out_path):
    used = from_library(key, duration, out_path)
    return used or synth(key, duration, transitions, out_path)
