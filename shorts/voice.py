"""Engelse voice-over met Kokoro (open-source stem, draait gratis in GitHub Actions).

- Elke scène in het verhaal heeft "say": een lijst zinnen; elke zin is een lijst tokens (ondertitel, uitspraak).
- We spreken elke zin apart uit, zodat ondertitels en stem altijd gelijk lopen.
- Het model (model-files-v1.1/kokoro-v1.0.onnx) geeft per klank een tijdstip: daarmee lichten de
  ondertitels woord per woord op. Lukt dat niet, dan verdelen we de tijd over de woorden.
- Is het model niet beschikbaar (of NO_VOICE=1), dan komt er stilte in de plaats en blijven de
  ondertitels op een rustig leestempo staan; de video wordt dan toch gemaakt.

Stemvoorbeelden maken:  python -m shorts.voice samples
"""
import os
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ.get("KOKORO_DIR", ROOT / "models"))
SR = 24000
GAP = 0.14          # pauze tussen zinnen binnen een scène
LEAD = {"hook": 0.05}
LEAD_DEFAULT = 0.18  # stem start kort na het begin van de scène
TAIL = 0.4          # rust na de laatste zin van een scène
MIN_DUR = {"hook": 2.4, "score": 3.4, "bars": 3.6, "table": 4.0, "next": 2.6, "results": 4.2, "cta": 2.8}
PUNCT = set(".,!?;:—–-…\"'“”‘’()")
SAMPLE_VOICES = ["am_michael", "am_fenrir", "bm_george", "bm_lewis", "af_heart", "bf_emma"]


def _group(timings):
    """Klank-tijdstippen -> lijst (start, einde) per gesproken woord (gesplitst op spaties)."""
    spans, cur = [], None
    for t in list(timings) + [None]:
        if t is not None and t.phoneme != " ":
            if all(ch in PUNCT for ch in t.phoneme):
                if cur:
                    cur[2] += t.phoneme
                continue
            if cur is None:
                cur = [t.start, t.end, t.phoneme]
            else:
                cur[1] = t.end
                cur[2] += t.phoneme
            continue
        if cur is not None:
            if all(ch in PUNCT for ch in cur[2]) and spans:
                pass
            else:
                spans.append((cur[0], cur[1]))
        cur = None
    return spans


def _spread(tokens, s0, s1):
    """Verdeelt de tijd evenredig met de lengte van de uitgesproken tekst."""
    weights = [len(sp) + 2 for _, sp in tokens]
    tot = sum(weights) or 1
    out, t = [], s0
    for (disp, _), w in zip(tokens, weights):
        d = (s1 - s0) * w / tot
        out.append((disp, t, t + d))
        t += d
    return out


class Narrator:
    def __init__(self, voice=None, speed=None):
        self.voice = voice or os.environ.get("VOICE", "am_michael")
        self.speed = float(speed or os.environ.get("VOICE_SPEED", "1.12"))
        self.k = None
        self.timed = False
        self.error = None
        self.exact = 0
        self.spread = 0
        if os.environ.get("NO_VOICE"):
            self.error = "NO_VOICE gezet"
            return
        model, voices = MODEL_DIR / "kokoro-v1.0.onnx", MODEL_DIR / "voices-v1.0.bin"
        if not (model.exists() and voices.exists()):
            self.error = f"stemmodel niet gevonden in {MODEL_DIR}"
            return
        try:
            from kokoro_onnx import Kokoro
            self.k = Kokoro(str(model), str(voices))
            self.timed = hasattr(self.k, "create_timed") and bool(getattr(self.k, "has_timings", False))
        except Exception as e:  # stem is mooi meegenomen, maar geen reden om geen video te maken
            self.error = f"{type(e).__name__}: {e}"
            self.k = None

    @property
    def active(self):
        return self.k is not None

    def describe(self):
        if not self.active:
            return f"geen stem ({self.error})"
        how = "woordtiming uit het model" if self.timed else "geschatte woordtiming"
        return f"Kokoro {self.voice} x{self.speed} ({how}; exact {self.exact}, geschat {self.spread})"

    def speak(self, tokens):
        """Geeft (audio float32 @ 24 kHz, [(ondertitel, start, einde)]) voor één zin."""
        text = " ".join(sp for _, sp in tokens)
        n_words = sum(len(sp.split()) for _, sp in tokens)
        if not self.active:
            dur = max(0.7, 0.36 * n_words + 0.2)
            return np.zeros(int(dur * SR), np.float32), _spread(tokens, 0.05, dur - 0.1)
        tim = None
        if self.timed:
            audio, sr, tim = self.k.create_timed(text, voice=self.voice, speed=self.speed, lang="en-us")
        else:
            audio, sr = self.k.create(text, voice=self.voice, speed=self.speed, lang="en-us")
        audio = np.asarray(audio, np.float32).reshape(-1)
        if sr != SR:   # Kokoro werkt op 24 kHz; voor de zekerheid toch omzetten
            idx = np.linspace(0, len(audio) - 1, int(len(audio) * SR / sr))
            audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
            if tim:
                tim = None
        dur = len(audio) / SR
        spans = _group(tim) if tim else []
        if spans and len(spans) == n_words:
            out, i = [], 0
            for disp, sp in tokens:
                k = len(sp.split())
                out.append((disp, spans[i][0], spans[i + k - 1][1]))
                i += k
            self.exact += 1
            return audio, out
        self.spread += 1
        s0, s1 = (spans[0][0], spans[-1][1]) if spans else (0.02, max(0.1, dur - 0.05))
        return audio, _spread(tokens, s0, s1)


def _pages(words, max_tokens=3, max_chars=18):
    """Knipt een zin in korte ondertitel-'pagina's' van 1 à 3 woorden."""
    pages, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_tokens or sum(len(x[0]) + 1 for x in cur) + len(w[0]) > max_chars):
            pages.append(cur)
            cur = []
        cur.append(w)
        if w[0][-1:] in ".!?,:" and len(cur) >= 1 and w is not words[-1]:
            pages.append(cur)
            cur = []
    if cur:
        pages.append(cur)
    return pages


def narrate(story, narrator, out_wav, build_timeline):
    """Spreekt alle scènes in, zet per scène de duur ("dur") en de ondertitels (story["captions"]).

    build_timeline: functie uit render.py die van de scène-duren de starttijden maakt (met overlap).
    Schrijft de stem als mono wav (24 kHz) naar out_wav.
    """
    per_scene = []
    for sc in story["scenes"]:
        clips, t = [], LEAD.get(sc["type"], LEAD_DEFAULT)
        for line in sc.get("say", []):
            audio, ws = narrator.speak(line)
            clips.append((t, audio, ws))
            t += len(audio) / SR + GAP
        voice_end = (t - GAP) if clips else 0.0
        sc["dur"] = round(max(MIN_DUR.get(sc["type"], 3.0), voice_end + TAIL), 2)
        per_scene.append(clips)

    timeline, total = build_timeline(story)
    track = np.zeros(int((total + 0.5) * SR), np.float32)
    captions = []
    for sc_obj, sc, clips in zip(timeline, story["scenes"], per_scene):
        for t, audio, ws in clips:
            s = int((sc_obj.start + t) * SR)
            e = min(len(track), s + len(audio))
            track[s:e] += audio[: e - s]
            if sc.get("captions", True):
                abs_words = [(d, sc_obj.start + t + a, sc_obj.start + t + b) for d, a, b in ws]
                for pg in _pages(abs_words):
                    captions.append({"t0": pg[0][1], "t1": pg[-1][2], "words": pg})
    for i, c in enumerate(captions):       # pagina blijft staan tot de volgende komt (max 0.5 s extra)
        nxt = captions[i + 1]["t0"] if i + 1 < len(captions) else c["t1"] + 0.5
        c["t_end"] = min(nxt, c["t1"] + 0.5)
    story["captions"] = captions

    peak = float(np.max(np.abs(track))) if len(track) else 0.0
    if peak > 0:
        track = track / peak * 0.89
    pcm = (np.clip(track, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    return total


def samples(out_dir, text="Gladbach finally win! It took them seven games. Is this the turnaround?"):
    """Maakt korte voorbeelden van verschillende stemmen (om er één te kiezen)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for v in SAMPLE_VOICES:
        nr = Narrator(voice=v)
        if not nr.active:
            print("geen stem:", nr.error)
            break
        try:
            audio, _ = nr.speak([(w, w) for w in text.split()])
        except Exception as e:
            print(f"{v}: {e}")
            continue
        wav = out_dir / f"{v}.wav"
        pcm = (np.clip(audio / (np.max(np.abs(audio)) + 1e-9) * 0.89, -1, 1) * 32767).astype(np.int16)
        with wave.open(str(wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SR)
            wf.writeframes(pcm.tobytes())
        m4a = wav.with_suffix(".m4a")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "aac", "-b:a", "128k",
                        str(m4a)], check=True)
        wav.unlink()
        made.append(m4a.name)
        print("stemvoorbeeld:", m4a)
    return made


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "samples":
        samples(sys.argv[2] if len(sys.argv) > 2 else ROOT / "previews" / "voices")
