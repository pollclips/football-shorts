"""Houdt de video onder de bestandslimiet van Make.

Make (gratis plan) weigert bestanden groter dan 5 MB: de HTTP-download faalt dan en er komt niets op YouTube.
De broadcast-stijl (verlopen, korrel) levert ±10-14 MB op; daarom comprimeren we achteraf met een
2-pass x264-encode naar een vaste doelgrootte. YouTube hercodeert sowieso alles.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

LIMIT = int(os.environ.get("MAX_VIDEO_BYTES", 4_500_000))   # veilig onder 5 MB (= 5 242 880 bytes)
AUDIO_KBPS = 128


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def fit(path, limit=LIMIT):
    """Comprimeert path ter plaatse tot het kleiner is dan limit (in bytes). Geeft de eindgrootte terug."""
    path = Path(path)
    size = path.stat().st_size
    if size <= limit:
        return size
    dur = max(duration(path), 1.0)
    target = limit * 0.94
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "pass")
        out = os.path.join(tmp, "small.mp4")
        for attempt in range(4):
            v_kbps = max(400, int(target * 8 / 1000 / dur - AUDIO_KBPS))
            common = ["-c:v", "libx264", "-preset", "medium", "-b:v", f"{v_kbps}k",
                      "-maxrate", f"{int(v_kbps * 1.4)}k", "-bufsize", f"{v_kbps * 2}k",
                      "-pix_fmt", "yuv420p", "-passlogfile", log]
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), *common, "-pass", "1",
                            "-an", "-f", "mp4", os.devnull], check=True)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), *common, "-pass", "2",
                            "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-movflags", "+faststart", out], check=True)
            new = os.path.getsize(out)
            print(f"gecomprimeerd: {size / 1e6:.1f} MB -> {new / 1e6:.1f} MB ({v_kbps} kbps)")
            if new <= limit:
                shutil.move(out, path)
                return new
            target *= 0.85
    raise RuntimeError(f"Video blijft groter dan {limit / 1e6:.1f} MB")
