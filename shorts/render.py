"""Zet een verhaal (dict met scènes) om in een verticale Short van 1080x1920."""
import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"
W, H, FPS = 1080, 1920, 30
CX = W / 2

BLACK, XB, BOLD, SB = ("InterDisplay-Black.otf", "InterDisplay-ExtraBold.otf",
                       "InterDisplay-Bold.otf", "InterDisplay-SemiBold.otf")
BG = (9, 13, 22)
PANEL = (22, 29, 44)
TXT = (244, 246, 250)
MUT = (138, 149, 170)
ACC = (200, 255, 70)      # kanaalkleur
FOC = (120, 182, 232)     # ploeg in de kijker
OPP = (112, 122, 142)     # tegenstander

DURATION = {"hook": 3.6, "score": 5.4, "bars": 5.6, "table": 6.6, "next": 4.2, "results": 6.4, "cta": 3.4}

_fc = {}


def F(name, size):
    key = (name, int(size))
    if key not in _fc:
        _fc[key] = ImageFont.truetype(str(FONTS / name), int(size))
    return _fc[key]


# ------------------------------------------------------------------ helpers
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def back(t):
    t = clamp(t)
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def prog(t, s, d):
    return clamp((t - s) / d)


def rgba(c, a):
    return (c[0], c[1], c[2], int(255 * clamp(a)))


def fit(d, s, name, size, maxw, minsize=28):
    while size > minsize and d.textlength(s, font=F(name, size)) > maxw:
        size -= 2
    return F(name, size)


def text_c(d, cx, y, s, font, col, a):
    if a > 0:
        d.text((cx - d.textlength(s, font=font) / 2, y), s, font=font, fill=rgba(col, a))


def text_l(d, x, y, s, font, col, a):
    if a > 0:
        d.text((x, y), s, font=font, fill=rgba(col, a))


def text_r(d, x, y, s, font, col, a):
    if a > 0:
        d.text((x - d.textlength(s, font=font), y), s, font=font, fill=rgba(col, a))


def tag(d, s, y, col=ACC, a=1.0):
    f = fit(d, s, XB, 34, 900)
    w = d.textlength(s, font=f)
    pad = 26
    d.rounded_rectangle([CX - w / 2 - pad, y, CX + w / 2 + pad, y + 64], radius=32,
                        fill=rgba(col, 0.14 * a), outline=rgba(col, 0.9 * a), width=3)
    text_c(d, CX, y + 12, s, f, col, a)


def window_alpha(lt, dur, fin=0.35, fout=0.3):
    return min(prog(lt, 0, fin), 1 - prog(lt, dur - fout, fout))


# ------------------------------------------------------------------ achtergrond
def make_bg():
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(0, 1, W)[None, :]
    r = np.sqrt((x - 0.5) ** 2 * 1.3 + (y - 0.42) ** 2)
    glow = np.clip(1 - r * 1.6, 0, 1) ** 2
    base = np.zeros((H, W, 3), np.float32)
    for i, (b, g) in enumerate(zip(BG, (24, 38, 52))):
        base[..., i] = b + (g - b) * glow
    img = Image.fromarray(base.astype(np.uint8), "RGB").convert("RGBA")
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    lc = (255, 255, 255, 14)
    d.line([(0, 960), (W, 960)], fill=lc, width=4)
    d.ellipse([CX - 230, 730, CX + 230, 1190], outline=lc, width=4)
    d.ellipse([CX - 10, 950, CX + 10, 970], fill=lc)
    d.rectangle([CX - 330, -4, CX + 330, 300], outline=lc, width=4)
    d.rectangle([CX - 330, H - 300, CX + 330, H + 4], outline=lc, width=4)
    img.alpha_composite(lay)
    return img


def big_word(s, size, col, maxw=960):
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    while True:
        f = F(BLACK, size)
        bb = tmp.textbbox((0, 0), s, font=f)
        if bb[2] - bb[0] <= maxw or size <= 120:
            break
        size -= 10
    im = Image.new("RGBA", (bb[2] - bb[0] + 40, bb[3] - bb[1] + 40), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((20 - bb[0], 20 - bb[1]), s, font=f, fill=col + (255,))
    return im


# ------------------------------------------------------------------ scènes
class Scene:
    def __init__(self, spec, start):
        self.s = spec
        self.start = start
        self.dur = DURATION[spec["type"]]
        self.end = start + self.dur

    def draw(self, img, d, t):
        lt = t - self.start
        if lt < 0 or lt > self.dur:
            return
        a = window_alpha(lt, self.dur, fout=0.6 if self.s["type"] == "cta" else 0.3)
        getattr(self, "draw_" + self.s["type"])(img, d, lt, a)

    # -- 1. haak
    def draw_hook(self, img, d, lt, a):
        s = self.s
        if not hasattr(self, "_hook"):
            self._hook = big_word(s["big"], 300, ACC)
            self._glow = self._hook.filter(ImageFilter.GaussianBlur(28))
        if s.get("tag"):
            tag(d, s["tag"], 330, MUT, a * ease(prog(lt, 0.05, 0.4)))
        p = prog(lt, 0.15, 0.55)
        sc = 0.6 + 0.4 * back(p)
        if p > 0:
            for src, ga in ((self._glow, 0.55), (self._hook, 1.0)):
                im = src.resize((max(1, int(src.width * sc)), max(1, int(src.height * sc))), Image.LANCZOS)
                k = ga * a * ease(p)
                if k < 1:
                    im.putalpha(im.getchannel("A").point(lambda v, k=k: int(v * k)))
                img.alpha_composite(im, (int(CX - im.width / 2), int(820 - im.height / 2)))
        e2 = ease(prog(lt, 0.9, 0.45))
        text_c(d, CX, 1040 + (1 - e2) * 40, s["line1"], fit(d, s["line1"], BOLD, 62, 960), TXT, a * e2)
        e3 = ease(prog(lt, 1.5, 0.45))
        text_c(d, CX, 1130 + (1 - e3) * 40, s["line2"], fit(d, s["line2"], BOLD, 62, 960), ACC, a * e3)

    # -- 2. scorebord (rust → einde)
    def draw_score(self, img, d, lt, a):
        s = self.s
        tag(d, s["tag"], 300, ACC, a)
        hcol = FOC if s.get("focus") == "home" else OPP
        acol = FOC if s.get("focus") == "away" else OPP
        y0 = 410 + (1 - ease(prog(lt, 0, 0.4))) * 60
        d.rounded_rectangle([70, y0, W - 70, y0 + 330], radius=36, fill=rgba(PANEL, 0.92 * a))
        d.rounded_rectangle([70, y0, 82, y0 + 330], radius=6, fill=rgba(hcol, a))
        d.rounded_rectangle([W - 82, y0, W - 70, y0 + 330], radius=6, fill=rgba(acol, a))
        text_c(d, 260, y0 + 245, s["home"].upper(), fit(d, s["home"].upper(), XB, 40, 330), hcol, a)
        text_c(d, W - 260, y0 + 245, s["away"].upper(), fit(d, s["away"].upper(), XB, 40, 330), acol, a)
        ht = s.get("ht")
        ft_at = 1.7 if ht else 0.2
        show_ft = lt >= ft_at
        hs, as_ = (s["hs"], s["as"]) if (show_ft or not ht) else (ht[0], ht[1])
        pop = 1 + 0.18 * (1 - ease(prog(lt, ft_at, 0.3))) if show_ft else 1
        fsz = int(190 * pop)
        text_c(d, 260, y0 + 40 + (190 - fsz) / 2, str(hs), F(BLACK, fsz), TXT, a)
        text_c(d, CX, y0 + 70, "–", F(BLACK, 140), MUT, a)
        text_c(d, W - 260, y0 + 40 + (190 - fsz) / 2, str(as_), F(BLACK, fsz), TXT, a)
        rows = []
        if ht:
            rows.append(("HALF-TIME", f"{ht[0]}–{ht[1]}", 0.5))
        rows.append(("FULL-TIME", f"{s['hs']}–{s['as']}", ft_at))
        for i, (lab, sc, st) in enumerate(rows):
            ee = ease(prog(lt, st, 0.35))
            if ee <= 0:
                continue
            y = 830 + i * 120
            x = 140 - (1 - ee) * 60
            d.rounded_rectangle([x, y, x + 800, y + 96], radius=24, fill=rgba(PANEL, 0.85 * a * ee))
            text_l(d, x + 40, y + 24, lab, F(XB, 44), ACC if lab == "FULL-TIME" else MUT, a * ee)
            text_r(d, x + 760, y + 18, sc, F(BLACK, 54), TXT, a * ee)
        if s.get("note"):
            e4 = ease(prog(lt, ft_at + 0.9, 0.4))
            text_c(d, CX, 1110 + (1 - e4) * 30, s["note"], fit(d, s["note"], BOLD, 50, 940), MUT, a * e4)

    # -- 3. vergelijkingsbalken
    def draw_bars(self, img, d, lt, a):
        s = self.s
        tag(d, s["tag"], 300, ACC, a)
        text_l(d, 90, 430, s["left"].upper(), fit(d, s["left"].upper(), XB, 42, 430), FOC, a)
        text_r(d, W - 90, 430, s["right"].upper(), fit(d, s["right"].upper(), XB, 42, 430), OPP, a)
        for i, (lab, hv, av, unit) in enumerate(s["rows"][:3]):
            st = 0.3 + i * 0.9
            ee = ease(prog(lt, st, 0.4))
            if ee <= 0:
                continue
            y = 560 + i * 280
            bw = ease(prog(lt, st + 0.15, 0.9))
            text_c(d, CX, y + (1 - ee) * 30, lab, F(XB, 40), MUT, a * ee)
            text_l(d, 90, y + 50, f"{int(round(hv * bw))}{unit}", F(BLACK, 96), TXT, a * ee)
            text_r(d, W - 90, y + 50, f"{int(round(av * bw))}{unit}", F(BLACK, 96), TXT, a * ee)
            bx0, bx1, by = 90, W - 90, y + 180
            d.rounded_rectangle([bx0, by, bx1, by + 30], radius=15, fill=rgba(PANEL, a * ee))
            tot = max(hv + av, 1)
            split = bx0 + (bx1 - bx0) * (hv / tot if hv + av else 0.5)
            lw, rw = (split - bx0) * bw, (bx1 - split) * bw
            if lw > 30:
                d.rounded_rectangle([split - lw, by, split - 3, by + 30], radius=15, fill=rgba(FOC, a * ee))
            if rw > 30:
                d.rounded_rectangle([split + 3, by, split + rw, by + 30], radius=15, fill=rgba(OPP, a * ee))

    # -- 4. klassement
    def draw_table(self, img, d, lt, a):
        s = self.s
        tag(d, s["tag"], 300, ACC, a)
        text_c(d, CX, 390, s["sub"], fit(d, s["sub"], SB, 40, 900), MUT, a)
        for i, (rk, team, pts, hl) in enumerate(s["rows"][:5]):
            st = 0.25 + i * 0.3
            ee = ease(prog(lt, st, 0.4))
            if ee <= 0:
                continue
            y = 490 + i * 150
            x = 70 + (1 - ee) * 80
            d.rounded_rectangle([x, y, x + W - 140, y + 124], radius=28, fill=rgba(PANEL, 0.92 * a * ee),
                                outline=rgba(ACC, a * ee) if hl else None, width=4)
            text_l(d, x + 40, y + 30, str(rk), F(BLACK, 58), ACC if hl else MUT, a * ee)
            text_l(d, x + 150, y + 32, team, fit(d, team, BOLD, 52, 600), TXT, a * ee)
            pe = ease(prog(lt, st + 0.2, 0.8))
            text_r(d, x + W - 180, y + 26, str(int(round(pts * pe))), F(BLACK, 64), ACC if hl else TXT, a * ee)
        if s.get("badge"):
            ge = clamp(back(prog(lt, 2.8, 0.45)))
            if ge > 0:
                f = F(BLACK, 54)
                w = d.textlength(s["badge"], font=f)
                bx, by = W - 70 - w - 56, 1265
                d.rounded_rectangle([bx, by, bx + w + 56, by + 84], radius=42, fill=rgba(ACC, a * ge))
                text_l(d, bx + 28, by + 10, s["badge"], f, BG, a * ge)
                text_l(d, 90, by + 20, s.get("badge_text", ""), fit(d, s.get("badge_text", ""), BOLD, 46, bx - 120),
                       TXT, a * ease(prog(lt, 3.0, 0.4)))
        if s.get("foot"):
            text_l(d, 90, 1390, s["foot"], fit(d, s["foot"], SB, 36, 900), MUT, a * ease(prog(lt, 3.6, 0.4)))

    # -- 5. volgende match
    def draw_next(self, img, d, lt, a):
        s = self.s
        tag(d, s["tag"], 470, ACC, a)
        e1 = ease(prog(lt, 0.1, 0.45))
        text_c(d, CX, 600 + (1 - e1) * 40, s["a"], fit(d, s["a"], BLACK, 82, 960), TXT, a * e1)
        text_c(d, CX, 700 + (1 - e1) * 40, "–", F(BLACK, 70), MUT, a * e1)
        text_c(d, CX, 790 + (1 - e1) * 40, s["b"], fit(d, s["b"], BLACK, 82, 960), TXT, a * e1)
        e2 = ease(prog(lt, 0.9, 0.45))
        for k, ln in enumerate([s.get("l1", ""), s.get("l2", "")]):
            if ln:
                text_c(d, CX, 1000 + k * 76 + (1 - e2) * 30, ln, fit(d, ln, BOLD, 56, 960),
                       ACC if k == 1 else TXT, a * e2)

    # -- 6. uitslagen van de dag
    def draw_results(self, img, d, lt, a):
        s = self.s
        tag(d, s["tag"], 300, ACC, a)
        if s.get("sub"):
            text_c(d, CX, 390, s["sub"], fit(d, s["sub"], SB, 40, 900), MUT, a)
        for i, (home, sc, away) in enumerate(s["rows"][:6]):
            st = 0.25 + i * 0.35
            ee = ease(prog(lt, st, 0.4))
            if ee <= 0:
                continue
            y = 480 + i * 140
            x = 70 + (1 - ee) * 80
            d.rounded_rectangle([x, y, x + W - 140, y + 116], radius=28, fill=rgba(PANEL, 0.92 * a * ee))
            text_r(d, x + 380, y + 34, home, fit(d, home, BOLD, 46, 330), TXT, a * ee)
            text_c(d, x + (W - 140) / 2, y + 26, sc, F(BLACK, 56), ACC, a * ee)
            text_l(d, x + W - 140 - 380, y + 34, away, fit(d, away, BOLD, 46, 330), TXT, a * ee)

    # -- 7. afsluiter
    def draw_cta(self, img, d, lt, a):
        s = self.s
        e1 = clamp(back(prog(lt, 0.05, 0.5)))
        text_c(d, CX, 640 + (1 - e1) * 50, s["q1"], fit(d, s["q1"], BLACK, 112, 980), TXT, a * e1)
        text_c(d, CX, 770 + (1 - e1) * 50, s["q2"], fit(d, s["q2"], BLACK, 112, 980), ACC, a * e1)
        e2 = ease(prog(lt, 0.5, 0.45))
        text_c(d, CX, 950 + (1 - e2) * 30, s["q3"], fit(d, s["q3"], BOLD, 56, 960), TXT, a * e2)
        text_c(d, CX, 1025 + (1 - e2) * 30, s["q4"], fit(d, s["q4"], BOLD, 56, 960), MUT, a * e2)
        e3 = ease(prog(lt, 1.0, 0.45))
        f = fit(d, s["follow"], XB, 44, 860)
        w = d.textlength(s["follow"], font=f)
        y = 1190 + (1 - e3) * 30
        d.rounded_rectangle([CX - w / 2 - 40, y, CX + w / 2 + 40, y + 96], radius=48, fill=rgba(ACC, a * e3))
        text_c(d, CX, y + 22, s["follow"], f, BG, a * e3)


def build_timeline(story):
    scenes, t = [], 0.0
    for spec in story["scenes"]:
        sc = Scene(spec, t)
        scenes.append(sc)
        t = sc.end
    return scenes, t


def render(story, out_path, audio_path, frames_at=None):
    """Rendert de video. frames_at: lijst tijdstippen -> enkel PNG's (voor controle)."""
    scenes, dur = build_timeline(story)
    bg = make_bg()

    def frame(i):
        t = i / FPS
        img = bg.copy()
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        for sc in scenes:
            sc.draw(lay, d, t)
        d.rectangle([0, 0, W, 10], fill=(255, 255, 255, 30))
        d.rectangle([0, 0, int(W * t / dur), 10], fill=rgba(ACC, 1))
        img.alpha_composite(lay)
        return img.convert("RGB")

    if frames_at:
        paths = []
        for ts in frames_at:
            p = f"{out_path}_f{ts:05.1f}.png"
            frame(int(ts * FPS)).save(p)
            paths.append(p)
        return paths

    n = int(dur * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out_path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(frame(i).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg mislukt")
    return out_path


def scene_starts(story):
    scenes, dur = build_timeline(story)
    return [s.start for s in scenes], dur
