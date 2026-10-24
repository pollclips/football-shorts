"""Zet een verhaal (dict met scènes) om in een verticale Short van 1080x1920.

Versie 2:
- het eerste beeld is meteen volledig: club, haakwoord, uitslag en context (geen fade uit zwart);
- kleuren en achtergrondstijl komen uit het thema (clubkleuren, wisselt per video);
- grote ondertitels die woord per woord oplichten met de stem;
- scènes lopen in elkaar over, zodat er nergens een leeg beeld is.

Veilige zone voor Shorts: belangrijke inhoud tussen y≈220 en y≈1500, rechts wat ruimte voor de knoppen.
"""
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from . import theme as themes

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"
W, H, FPS = 1080, 1920, 30
CX = W / 2
PAN = 160            # achtergrond is breder dan het beeld en schuift traag
XF = 0.22            # overlap tussen scènes (s)
CAP_Y = 1300         # bovenkant ondertitels
CAP_W = 860

BLACK, XB, BOLD, SB = ("InterDisplay-Black.otf", "InterDisplay-ExtraBold.otf",
                       "InterDisplay-Bold.otf", "InterDisplay-SemiBold.otf")
TXT = (244, 246, 250)
MUT = (150, 160, 180)

# worden per video ingevuld door set_theme()
BG = (9, 13, 22)
PANEL = (22, 29, 44)
ACC = (200, 255, 70)
FOC = ACC
OPP = (112, 122, 142)
ON_ACC = (9, 13, 22)
TH = None

DURATION = {"hook": 3.6, "score": 5.4, "bars": 5.6, "table": 6.6, "next": 4.2, "results": 6.4, "cta": 3.4}

_fc = {}


def F(name, size):
    key = (name, int(size))
    if key not in _fc:
        _fc[key] = ImageFont.truetype(str(FONTS / name), int(size))
    return _fc[key]


def set_theme(th):
    global BG, PANEL, ACC, FOC, OPP, ON_ACC, TH
    TH = th or themes.build([], [], __import__("random").Random(0))
    BG = TH["bg"]
    PANEL = themes.mix(BG, (255, 255, 255), 0.09)
    ACC, FOC, OPP, ON_ACC = TH["acc"], TH["foc"], TH["opp"], TH["on_acc"]


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


def text_c(d, cx, y, s, font, col, a, stroke=0):
    if a > 0:
        d.text((cx - d.textlength(s, font=font) / 2, y), s, font=font, fill=rgba(col, a),
               stroke_width=stroke, stroke_fill=rgba((0, 0, 0), 0.85 * a) if stroke else None)


def text_l(d, x, y, s, font, col, a):
    if a > 0:
        d.text((x, y), s, font=font, fill=rgba(col, a))


def text_r(d, x, y, s, font, col, a):
    if a > 0:
        d.text((x - d.textlength(s, font=font), y), s, font=font, fill=rgba(col, a))


def tag(d, s, y, col=None, a=1.0):
    col = col or ACC
    f = fit(d, s, XB, 34, 900)
    w = d.textlength(s, font=f)
    pad = 26
    d.rounded_rectangle([CX - w / 2 - pad, y, CX + w / 2 + pad, y + 64], radius=32,
                        fill=rgba(col, 0.16 * a), outline=rgba(col, 0.9 * a), width=3)
    text_c(d, CX, y + 12, s, f, col, a)


def window_alpha(lt, dur, fin=XF, fout=XF):
    a_in = 1.0 if fin <= 0 else prog(lt, 0, fin)
    return min(a_in, 1 - prog(lt, dur - fout, fout))


# ------------------------------------------------------------------ achtergrond
def make_bg(th):
    """Achtergrond in de clubkleuren; stijl wisselt per video (glow / stripes / diag / split)."""
    ww = W + PAN
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(0, 1, ww)[None, :]
    base = np.empty((H, ww, 3), np.float32)
    base[:] = np.array(th["bg"], np.float32)
    style = th["style"]

    def blend(mask, col, k):
        m = (np.clip(mask, 0, 1) * k)[..., None]
        base[:] = base * (1 - m) + np.array(col, np.float32) * m

    r = np.sqrt((x - 0.5) ** 2 * 1.3 + (y - 0.36) ** 2)
    glow = np.clip(1 - r * 1.5, 0, 1) ** 2
    blend(glow, th["glow"], 0.9 if style == "glow" else 0.55)

    xp = x * ww
    yp = y * H
    if style == "stripes":
        period = 180
        band = ((xp // (period / 2)) % 2 == 0)
        stripes = np.where(band, 1.0, 0.0) * np.ones_like(yp)
        fade = np.clip(1.1 - y * 1.1, 0.25, 1)
        blend(stripes * fade, th["stripe_a"], 0.13)
        blend((1 - stripes) * fade, th["stripe_b"], 0.06)
    elif style == "diag":
        d1 = np.abs(xp * 0.55 + yp - 520) < 150
        d2 = np.abs(xp * 0.55 + yp - 760) < 40
        blend(d1.astype(np.float32), th["stripe_a"], 0.22)
        blend(d2.astype(np.float32), th["stripe_b"], 0.16)
    elif style == "split":
        line = 980 + (xp - ww / 2) * 0.22
        top = (yp < line).astype(np.float32)
        blend(top, th["glow"], 0.35)
        blend(1 - top, th["opp_tint"], 0.75)
        edge = np.abs(yp - line) < 5
        blend(edge.astype(np.float32), th["acc"], 0.55)

    vig = np.clip(((x - 0.5) ** 2 * 1.2 + (y - 0.45) ** 2) * 1.5, 0, 1)
    base *= (1 - 0.45 * vig)[..., None]
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").convert("RGBA")

    if style == "glow":    # vage lijnen van een veld
        lay = Image.new("RGBA", (ww, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        lc = (255, 255, 255, 12)
        cx = ww / 2
        d.line([(0, 960), (ww, 960)], fill=lc, width=4)
        d.ellipse([cx - 230, 730, cx + 230, 1190], outline=lc, width=4)
        d.rectangle([cx - 330, -4, cx + 330, 300], outline=lc, width=4)
        d.rectangle([cx - 330, H - 300, cx + 330, H + 4], outline=lc, width=4)
        img.alpha_composite(lay)
    return img


def big_word(s, size, col, maxw=960, minsize=110):
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    while True:
        f = F(BLACK, size)
        bb = tmp.textbbox((0, 0), s, font=f)
        if bb[2] - bb[0] <= maxw or size <= minsize:
            break
        size -= 8
    im = Image.new("RGBA", (bb[2] - bb[0] + 40, bb[3] - bb[1] + 40), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((20 - bb[0], 20 - bb[1]), s, font=f, fill=col + (255,))
    return im


def paste_scaled(img, src, cx, cy, sc, alpha):
    im = src if abs(sc - 1) < 1e-3 else src.resize((max(1, int(src.width * sc)), max(1, int(src.height * sc))),
                                                   Image.BILINEAR)
    if alpha < 1:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v, k=alpha: int(v * k)))
    img.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


# ------------------------------------------------------------------ scènes
class Scene:
    def __init__(self, spec, start, first=False):
        self.s = spec
        self.start = start
        self.first = first
        self.dur = spec.get("dur") or DURATION[spec["type"]]
        self.end = start + self.dur

    def draw(self, img, d, t, last=False):
        lt = t - self.start
        if lt < 0 or lt > self.dur:
            return
        a = window_alpha(lt, self.dur, fin=0 if self.first else XF, fout=0.6 if last else XF)
        getattr(self, "draw_" + self.s["type"])(img, d, lt, a)

    # -- 1. haak: alles staat er vanaf het eerste beeld
    def draw_hook(self, img, d, lt, a):
        s = self.s
        if not hasattr(self, "_big"):
            self._big = big_word(s["big"], 280, ACC, maxw=820)
            self._glow = self._big.filter(ImageFilter.GaussianBlur(26))
            self._team = big_word(s["team"], 170, TXT, maxw=900, minsize=90) if s.get("team") else None
        lay_top = TH.get("hook_layout", "team_top") == "team_top"
        punch = 1 + 0.1 * (1 - ease(lt / 0.4))                 # kleine 'punch-in', geen fade
        pulse = 0.55 + 0.25 * (0.5 + 0.5 * math.sin(lt * 5.5))
        if s.get("tag"):
            tag(d, s["tag"], 236, MUT, a)
        if self._team is not None:
            ty, by = (470, 735) if lay_top else (760, 520)
        else:
            ty, by = None, 640
        if self._team is not None:
            paste_scaled(img, self._team, CX, ty + (1 - ease(lt / 0.35)) * 24, 1.0, a)
        paste_scaled(img, self._glow, CX, by, punch, a * pulse)
        paste_scaled(img, self._big, CX, by, punch, a)
        y = 905
        if s.get("score"):
            f = fit(d, s["score"], XB, 50, 860)
            w = d.textlength(s["score"], font=f)
            d.rounded_rectangle([CX - w / 2 - 34, y, CX + w / 2 + 34, y + 88], radius=44,
                                fill=rgba(PANEL, 0.92 * a), outline=rgba(ACC, 0.8 * a), width=3)
            text_c(d, CX, y + 16, s["score"], f, TXT, a)
            y += 118
        if s.get("sub"):
            text_c(d, CX, y, s["sub"], fit(d, s["sub"], BOLD, 60, 920), ACC, a)

    # -- 2. scorebord (rust → einde)
    def draw_score(self, img, d, lt, a):
        s = self.s
        tag(d, s["tag"], 300, ACC, a)
        hcol = FOC if s.get("focus") == "home" else OPP
        acol = FOC if s.get("focus") == "away" else OPP
        y0 = 410 + (1 - ease(prog(lt, 0, 0.4))) * 60
        d.rounded_rectangle([70, y0, W - 70, y0 + 330], radius=36, fill=rgba(PANEL, 0.92 * a))
        d.rounded_rectangle([70, y0, 84, y0 + 330], radius=6, fill=rgba(hcol, a))
        d.rounded_rectangle([W - 84, y0, W - 70, y0 + 330], radius=6, fill=rgba(acol, a))
        text_c(d, 260, y0 + 245, s["home"].upper(), fit(d, s["home"].upper(), XB, 40, 330), hcol, a)
        text_c(d, W - 260, y0 + 245, s["away"].upper(), fit(d, s["away"].upper(), XB, 40, 330), acol, a)
        ht = s.get("ht")
        ft_at = 1.5 if ht else 0.2
        show_ft = lt >= ft_at
        hs, as_ = (s["hs"], s["as"]) if (show_ft or not ht) else (ht[0], ht[1])
        pop = 1 + 0.18 * (1 - ease(prog(lt, ft_at, 0.3))) if show_ft else 1
        fsz = int(190 * pop)
        text_c(d, 260, y0 + 40 + (190 - fsz) / 2, str(hs), F(BLACK, fsz), TXT, a)
        text_c(d, CX, y0 + 70, "–", F(BLACK, 140), MUT, a)
        text_c(d, W - 260, y0 + 40 + (190 - fsz) / 2, str(as_), F(BLACK, fsz), TXT, a)
        rows = []
        if ht:
            rows.append(("HALF-TIME", f"{ht[0]}–{ht[1]}", 0.3))
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
            text_c(d, CX, 1100 + (1 - e4) * 30, s["note"], fit(d, s["note"], BOLD, 50, 940), MUT, a * e4)

    # -- 3. vergelijkingsbalken
    def draw_bars(self, img, d, lt, a):
        s = self.s
        tag(d, s["tag"], 290, ACC, a)
        text_l(d, 90, 400, s["left"].upper(), fit(d, s["left"].upper(), XB, 42, 430), FOC, a)
        text_r(d, W - 90, 400, s["right"].upper(), fit(d, s["right"].upper(), XB, 42, 430), OPP, a)
        for i, (lab, hv, av, unit) in enumerate(s["rows"][:3]):
            st = 0.3 + i * 0.8
            ee = ease(prog(lt, st, 0.4))
            if ee <= 0:
                continue
            y = 500 + i * 245
            bw = ease(prog(lt, st + 0.15, 0.9))
            text_c(d, CX, y + (1 - ee) * 30, lab, F(XB, 40), MUT, a * ee)
            text_l(d, 90, y + 46, f"{int(round(hv * bw))}{unit}", F(BLACK, 92), TXT, a * ee)
            text_r(d, W - 90, y + 46, f"{int(round(av * bw))}{unit}", F(BLACK, 92), TXT, a * ee)
            bx0, bx1, by = 90, W - 90, y + 170
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
        tag(d, s["tag"], 260, ACC, a)
        text_c(d, CX, 348, s["sub"], fit(d, s["sub"], SB, 40, 900), MUT, a)
        for i, (rk, team, pts, hl) in enumerate(s["rows"][:5]):
            st = 0.2 + i * 0.22
            ee = ease(prog(lt, st, 0.4))
            if ee <= 0:
                continue
            y = 430 + i * 138
            x = 70 + (1 - ee) * 80
            d.rounded_rectangle([x, y, x + W - 140, y + 118], radius=28,
                                fill=rgba(ACC, 0.18 * a * ee) if hl else rgba(PANEL, 0.92 * a * ee),
                                outline=rgba(ACC, a * ee) if hl else None, width=5)
            text_l(d, x + 40, y + 28, str(rk), F(BLACK, 58), ACC if hl else MUT, a * ee)
            text_l(d, x + 150, y + 30, team, fit(d, team, BOLD, 52, 600), TXT, a * ee)
            pe = ease(prog(lt, st + 0.2, 0.8))
            text_r(d, x + W - 180, y + 24, str(int(round(pts * pe))), F(BLACK, 64), ACC if hl else TXT, a * ee)
        if s.get("badge"):
            ge = clamp(back(prog(lt, 1.9, 0.45)))
            if ge > 0:
                f = F(BLACK, 54)
                w = d.textlength(s["badge"], font=f)
                bx, by = W - 70 - w - 56, 1135
                d.rounded_rectangle([bx, by, bx + w + 56, by + 84], radius=42, fill=rgba(ACC, a * ge))
                text_l(d, bx + 28, by + 10, s["badge"], f, ON_ACC, a * ge)
                text_l(d, 90, by + 20, s.get("badge_text", ""), fit(d, s.get("badge_text", ""), BOLD, 46, bx - 120),
                       TXT, a * ease(prog(lt, 2.1, 0.4)))
        if s.get("foot"):
            text_l(d, 90, 1236, s["foot"], fit(d, s["foot"], SB, 34, 900), MUT, a * ease(prog(lt, 2.6, 0.4)))

    # -- 5. volgende match
    def draw_next(self, img, d, lt, a):
        s = self.s
        tag(d, s["tag"], 430, ACC, a)
        e1 = ease(prog(lt, 0.05, 0.4))
        text_c(d, CX, 560 + (1 - e1) * 40, s["a"], fit(d, s["a"], BLACK, 92, 960), TXT, a * e1)
        text_c(d, CX, 670 + (1 - e1) * 40, "vs", F(XB, 54), MUT, a * e1)
        text_c(d, CX, 750 + (1 - e1) * 40, s["b"], fit(d, s["b"], BLACK, 92, 960), TXT, a * e1)
        e2 = ease(prog(lt, 0.6, 0.4))
        for k, ln in enumerate([s.get("l1", ""), s.get("l2", "")]):
            if ln:
                text_c(d, CX, 960 + k * 76 + (1 - e2) * 30, ln, fit(d, ln, BOLD, 56, 960),
                       ACC if k == 1 else TXT, a * e2)

    # -- 6. uitslagen van de dag
    def draw_results(self, img, d, lt, a):
        s = self.s
        tag(d, s["tag"], 260, ACC, a)
        if s.get("sub"):
            text_c(d, CX, 348, s["sub"], fit(d, s["sub"], SB, 40, 900), MUT, a)
        for i, (home, sc, away) in enumerate(s["rows"][:5]):
            st = 0.2 + i * 0.3
            ee = ease(prog(lt, st, 0.4))
            if ee <= 0:
                continue
            y = 440 + i * 140
            x = 70 + (1 - ee) * 80
            d.rounded_rectangle([x, y, x + W - 140, y + 116], radius=28, fill=rgba(PANEL, 0.92 * a * ee))
            text_r(d, x + 380, y + 34, home, fit(d, home, BOLD, 46, 330), TXT, a * ee)
            text_c(d, x + (W - 140) / 2, y + 26, sc, F(BLACK, 56), ACC, a * ee)
            text_l(d, x + W - 140 - 380, y + 34, away, fit(d, away, BOLD, 46, 330), TXT, a * ee)

    # -- 7. afsluiter
    def draw_cta(self, img, d, lt, a):
        s = self.s
        e1 = clamp(back(prog(lt, 0.0, 0.45)))
        text_c(d, CX, 600 + (1 - e1) * 50, s["q1"], fit(d, s["q1"], BLACK, 118, 980), TXT, a * e1)
        text_c(d, CX, 735 + (1 - e1) * 50, s["q2"], fit(d, s["q2"], BLACK, 118, 980), ACC, a * e1)
        e2 = ease(prog(lt, 0.5, 0.45))
        if s.get("q3"):
            text_c(d, CX, 920 + (1 - e2) * 30, s["q3"], fit(d, s["q3"], BOLD, 56, 960), TXT, a * e2)
        text_c(d, CX, 995 + (1 - e2) * 30, s["q4"], fit(d, s["q4"], BOLD, 56, 960), MUT, a * e2)
        e3 = ease(prog(lt, 0.9, 0.45))
        f = fit(d, s["follow"], XB, 44, 860)
        w = d.textlength(s["follow"], font=f)
        y = 1160 + (1 - e3) * 30
        d.rounded_rectangle([CX - w / 2 - 40, y, CX + w / 2 + 40, y + 96], radius=48, fill=rgba(ACC, a * e3))
        text_c(d, CX, y + 22, s["follow"], f, ON_ACC, a * e3)


# ------------------------------------------------------------------ ondertitels
def _cap_layout(d, words, size):
    f = F(BLACK, size)
    space = d.textlength(" ", font=f)
    lines, cur, x = [], [], 0.0
    for w in words:
        wl = d.textlength(w[0], font=f)
        if cur and x + wl > CAP_W:
            lines.append((cur, x - space))
            cur, x = [], 0.0
        cur.append((w, x, wl))
        x += wl + space
    if cur:
        lines.append((cur, x - space))
    return f, lines


def draw_captions(d, t, captions):
    for c in captions:
        if not (c["t0"] - 0.04 <= t < c["t_end"]):
            continue
        size = 96
        f, lines = _cap_layout(d, c["words"], size)
        while (len(lines) > 2 or any(lw > CAP_W for _, lw in lines)) and size > 60:
            size -= 6
            f, lines = _cap_layout(d, c["words"], size)
        pop = ease(prog(t, c["t0"] - 0.04, 0.1))
        lh = size * 1.18
        started = [w for w in c["words"] if w[1] - 0.03 <= t]
        cur = started[-1] if started and t < started[-1][2] + 0.25 else None
        for li, (ln, lw) in enumerate(lines):
            x0 = CX - lw / 2
            y = CAP_Y + li * lh + (1 - pop) * 14
            for (w, x, wl) in ln:
                col = ACC if w is cur else TXT
                d.text((x0 + x, y), w[0], font=f, fill=rgba(col, pop),
                       stroke_width=9, stroke_fill=rgba((0, 0, 0), 0.9 * pop))
        break


# ------------------------------------------------------------------ tijdlijn + render
def build_timeline(story):
    scenes, t = [], 0.0
    for i, spec in enumerate(story["scenes"]):
        start = 0.0 if i == 0 else max(0.0, t - XF)
        sc = Scene(spec, start, first=(i == 0))
        scenes.append(sc)
        t = sc.end
    return scenes, t


def render(story, out_path, audio_path, th=None, frames_at=None):
    """Rendert de video. frames_at: lijst tijdstippen -> enkel PNG's (voor controle)."""
    set_theme(th)
    scenes, dur = build_timeline(story)
    bg = make_bg(TH)
    captions = story.get("captions", [])

    def frame(i):
        t = i / FPS
        off = int(PAN / 2 + (PAN / 2 - 4) * math.sin(t / 3.2))
        img = bg.crop((off, 0, off + W, H))
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        for k, sc in enumerate(scenes):
            sc.draw(lay, d, t, last=(k == len(scenes) - 1))
        draw_captions(d, t, captions)
        d.rectangle([0, 0, W, 10], fill=(255, 255, 255, 30))
        d.rectangle([0, 0, int(W * t / dur), 10], fill=rgba(ACC, 1))
        img.alpha_composite(lay)
        return img.convert("RGB")

    if frames_at:
        paths = []
        for ts in frames_at:
            p = f"{out_path}_f{ts:05.2f}.png"
            frame(int(round(ts * FPS))).save(p)
            paths.append(p)
        return paths

    n = int(dur * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
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
