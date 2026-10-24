"""Broadcast-stijl renderer (v3): elke 1–2 s een nieuw shot, grote condensed koppen die binnenslaan,
clubkleuren over het hele beeld, schuine kleurvlakken, camera-bewegingen, flits/schok op impact
en kleur-wipes tussen de shots.

Werkt met hetzelfde verhaal (story) en dezelfde stem als v2; de stem bepaalt de timing van elk woord.
"""
import colorsys
import math
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"
W, H, FPS = 1080, 1920, 30
ANTON = "Anton-Regular.ttf"
INTER = "InterDisplay-ExtraBold.otf"
WHITE = (250, 250, 250)
INK = (10, 12, 16)
SLANT = 0.21          # helling van de schuine vlakken/labels (~12°)
CAP_Y = 1340          # ondertitels (enkel bij data-shots)
WIPE_IN, WIPE_OUT = 0.24, 0.30
LIME = (200, 255, 70)


# ------------------------------------------------------------------ basis
_fonts = {}


def font(size, name=ANTON):
    key = (name, int(size))
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(str(FONTS / name), int(size))
    return _fonts[key]


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(t, s, d):
    return clamp((t - s) / d) if d > 0 else (1.0 if t >= s else 0.0)


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_io(t):
    t = clamp(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def back(t, k=1.9):
    t = clamp(t)
    return 1 + (k + 1) * (t - 1) ** 3 + k * (t - 1) ** 2


# ------------------------------------------------------------------ kleuren
def _hsv(c):
    return colorsys.rgb_to_hsv(*(v / 255 for v in c))


def _rgb(h, s, v):
    return tuple(int(round(x * 255)) for x in colorsys.hsv_to_rgb(h, clamp(s), clamp(v)))


def _neutral(c):
    return c is None or _hsv(c)[1] < 0.2


def _lum(c):
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255


class Palette:
    def __init__(self, th):
        th = th or {}
        fp = th.get("fprim") or th.get("stripe_a")
        op = th.get("oprim")
        if fp and not _neutral(fp):
            h, s, v = _hsv(fp)
            self.acc = _rgb(h, max(s, 0.8), 1.0)
            self.prim = _rgb(h, max(s, 0.75), 0.62)
            self.deep = _rgb(h, max(s, 0.7), 0.15)
            self.mid = _rgb(h, max(s, 0.7), 0.32)
        else:
            self.acc, self.prim, self.deep, self.mid = LIME, (46, 50, 60), (12, 14, 19), (28, 31, 38)
        if op and not _neutral(op):
            h, s, v = _hsv(op)
            self.opp = _rgb(h, max(s, 0.75), 0.95)
            self.opp_deep = _rgb(h, max(s, 0.7), 0.24)
        else:
            self.opp, self.opp_deep = (225, 228, 235), (34, 36, 44)
        if abs(_hsv(self.opp)[0] - _hsv(self.acc)[0]) < 0.06 and not _neutral(op):
            self.opp, self.opp_deep = (225, 228, 235), (34, 36, 44)
        self.ink = INK if _lum(self.acc) > 0.45 else WHITE


# ------------------------------------------------------------------ tekst als beeld
@lru_cache(maxsize=768)
def txt(text, size, color, name=ANTON, shadow=True):
    f = font(size, name)
    bb = f.getbbox(text)
    pad = 40 if shadow else 6
    w, h = bb[2] - bb[0] + 2 * pad, bb[3] - bb[1] + 2 * pad
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:   # zachte donkere schaduw: leesbaar op elke achtergrond
        sh = Image.new("L", (w, h), 0)
        ImageDraw.Draw(sh).text((pad - bb[0], pad - bb[1] + 12), text, font=f, fill=170)
        im.putalpha(sh.filter(ImageFilter.GaussianBlur(14)))
    ImageDraw.Draw(im).text((pad - bb[0], pad - bb[1]), text, font=f, fill=color + (255,))
    return im


@lru_cache(maxsize=128)
def outline(text, size, color, width=4):
    f = font(size)
    bb = f.getbbox(text, stroke_width=width)
    w, h = bb[2] - bb[0] + 8, bb[3] - bb[1] + 8
    m1 = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m1).text((4 - bb[0], 4 - bb[1]), text, font=f, fill=255, stroke_width=width, stroke_fill=255)
    m2 = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m2).text((4 - bb[0], 4 - bb[1]), text, font=f, fill=255)
    im = Image.new("RGBA", (w, h), color + (255,))
    im.putalpha(ImageChops.subtract(m1, m2))
    return im


def fit_size(text, size, maxw, name=ANTON, minsize=60):
    while size > minsize and font(size, name).getlength(text) > maxw:
        size -= 6
    return size


@lru_cache(maxsize=256)
def chip(text, size, fg, bg, name=ANTON, padx=30, pady=14):
    f = font(size, name)
    bb = f.getbbox(text)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    h = th + 2 * pady
    sk = int(h * SLANT)
    w = tw + 2 * padx + sk
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(sk, 0), (w, 0), (w - sk, h), (0, h)], fill=bg + (255,))
    d.text(((w - tw) / 2 - bb[0], pady - bb[1]), text, font=f, fill=fg + (255,))
    return im


def put(dst, im, cx, cy, sc=1.0, rot=0.0, a=1.0, anchor="c"):
    """Plakt im (RGBA) op dst met schaal/rotatie/alpha; mag buiten beeld vallen."""
    if a <= 0.01 or im is None:
        return
    if abs(sc - 1) > 1e-3:
        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
    if abs(rot) > 0.05:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    if a < 0.999:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v, k=a: int(v * k)))
    if anchor == "c":
        x, y = int(cx - im.width / 2), int(cy - im.height / 2)
    elif anchor == "l":
        x, y = int(cx), int(cy - im.height / 2)
    else:
        x, y = int(cx - im.width), int(cy - im.height / 2)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst.width, x + im.width), min(dst.height, y + im.height)
    if x1 <= x0 or y1 <= y0:
        return
    dst.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def band(d, cy, thick, color, a=1.0, slope=-SLANT):
    """Schuin vlak over de volle breedte, gecentreerd op y=cy (in het midden van het beeld)."""
    xl, xr = -300, W + 300
    yl, yr = cy + slope * (xl - W / 2), cy + slope * (xr - W / 2)
    d.polygon([(xl, yl - thick / 2), (xr, yr - thick / 2), (xr, yr + thick / 2), (xl, yl + thick / 2)],
              fill=color + (int(255 * clamp(a)),))


def region(d, y_top, y_bot, color, a=1.0, slope=-SLANT):
    """Vlak tussen twee schuine lijnen (y gemeten in het midden van het beeld)."""
    xl, xr = -300, W + 300
    d.polygon([(xl, y_top + slope * (xl - W / 2)), (xr, y_top + slope * (xr - W / 2)),
               (xr, y_bot + slope * (xr - W / 2)), (xl, y_bot + slope * (xl - W / 2))],
              fill=color + (int(255 * clamp(a)),))


def is_num(s):
    return any(ch.isdigit() for ch in s)


# ------------------------------------------------------------------ achtergrond
class Backdrop:
    def __init__(self, pal, seed=0):
        self.p = pal
        rng = np.random.default_rng(seed)
        y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
        x = np.linspace(0, 1, W, dtype=np.float32)[None, :]
        deep, mid = np.array(pal.deep, np.float32), np.array(pal.mid, np.float32)
        g = np.clip(1 - np.sqrt((x - 0.5) ** 2 * 1.1 + (y - 0.3) ** 2) * 1.45, 0, 1) ** 1.6
        base = deep[None, None, :] + (mid - deep)[None, None, :] * g[..., None]
        # twee zachte schijnwerpers van boven
        for sx, ang in ((0.12, 0.55), (0.88, -0.55)):
            dx = (x - sx) - (y * ang * 0.35)
            beam = np.exp(-(dx ** 2) / (0.006 + 0.03 * y)) * np.clip(1.1 - y * 1.1, 0, 1)
            base += beam[..., None] * 34
        # lichte, vaste korrel in de achtergrond (bewegende korrel maakt het bestand 5x groter)
        grain = rng.integers(-5, 6, (H // 2, W // 2)).astype(np.float32)
        base += np.repeat(np.repeat(grain, 2, 0), 2, 1)[..., None]
        self.base = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        # fijne schuine lijntjes (scrollen)
        tex = Image.new("RGBA", (W + 400, H + 400), (0, 0, 0, 0))
        d = ImageDraw.Draw(tex)
        for k in range(-60, 120):
            x0 = k * 34
            d.line([(x0, 0), (x0 + (H + 400) * 0.45, H + 400)], fill=(255, 255, 255, 9), width=3)
        self.tex = tex
        # vignet
        vig = 1 - 0.42 * np.clip(((x - 0.5) ** 2 * 1.3 + (y - 0.47) ** 2) * 1.7, 0, 1)
        self.vig = vig.astype(np.float32)[..., None]

    def frame(self, t, variant):
        img = self.base.copy()
        ox = int((t * 40) % 34)
        img.alpha_composite(self.tex.crop((200 - ox, 200, 200 - ox + W, 200 + H)))
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        p = self.p
        drift = math.sin(t * 0.7) * 40
        if variant % 3 == 0:
            band(d, 1230 + drift, 520, p.prim, 0.92)
            band(d, 955 + drift, 22, p.acc, 1.0)
            band(d, 1520 + drift, 60, p.deep, 0.8)
        elif variant % 3 == 1:
            band(d, 300 - drift, 420, p.prim, 0.85, slope=SLANT)
            band(d, 525 - drift, 18, p.acc, 1.0, slope=SLANT)
        else:
            band(d, 760 + drift, 900, p.prim, 0.55)
            band(d, 300 + drift, 14, p.acc, 0.9)
            band(d, 1230 + drift, 14, p.acc, 0.9)
        img.alpha_composite(lay)
        return img

    def finish(self, arr, i):
        """Vignet op een uint8-array (H, W, 3)."""
        return (arr.astype(np.float32) * self.vig).astype(np.uint8)


# ------------------------------------------------------------------ shots
class Shot:
    captions = False
    variant = 0

    def __init__(self, t0, t1, data, pal):
        self.t0, self.t1, self.d, self.p = t0, t1, data, pal
        self.impacts = []          # (tijd, sterkte)
        self.setup()

    def setup(self):
        pass

    def draw(self, img, t):
        raise NotImplementedError


class TitleShot(Shot):
    """Eerste beeld: club + haakwoord + uitslag, alles meteen zichtbaar."""
    variant = 0

    def setup(self):
        d, p = self.d, self.p
        self.team = d.get("team")
        self.ts = fit_size(self.team, 330, 960) if self.team else None
        ws = fit_size(d["big"], 170, 760)
        self.word = chip(d["big"], ws, p.ink, p.acc, padx=40, pady=18)
        self.score = chip(d["score"], 62, WHITE, INK, padx=34, pady=16) if d.get("score") else None
        tags = d.get("tag", "").split(" · ")
        self.tag1 = chip(tags[0], 46, p.ink, p.acc, padx=24, pady=10) if tags and tags[0] else None
        self.tag2 = chip(tags[1], 46, WHITE, INK, padx=24, pady=10) if len(tags) > 1 else None
        self.sub = d.get("sub", "").upper()
        self.impacts = [(self.t0 + 0.02, 0.6)]

    def draw(self, img, t):
        lt = t - self.t0
        p = self.p
        if self.team:
            ol = outline(self.team, self.ts, WHITE, 3)
            for k, (y, dirn) in enumerate(((345, 1), (1105, -1))):
                put(img, ol, W / 2 + dirn * (lt * 70 - 60), y, 1.0, 0, 0.16)
            # al leesbaar op beeld 1: enkel een kleine 'punch', geen inzoom van buiten beeld
            sc = 1 + 0.08 * (1 - ease_out(lt / 0.16)) + 0.015 * math.sin(lt * 4)
            put(img, txt(self.team, self.ts, WHITE), W / 2, 630, sc)
        rot = -5 - 4 * (1 - back(lt / 0.28))
        sc = 1 + 0.16 * (1 - ease_out(lt / 0.16))
        put(img, self.word, W / 2 + 10, 870 if self.team else 700, sc, rot)
        if self.score is not None:
            put(img, self.score, W / 2 - 90 * (1 - ease_out(lt / 0.25)), 1040)
        if self.sub:
            ss = fit_size(self.sub, 64, 900)
            put(img, txt(self.sub, ss, WHITE), W / 2 + 90 * (1 - ease_out(lt / 0.25)), 1150)
        if self.tag1:
            x = 70 - 40 * (1 - ease_out(lt / 0.25))
            put(img, self.tag1, x, 215, anchor="l")
            if self.tag2:
                put(img, self.tag2, x + self.tag1.width - 8, 215, anchor="l")


class KineticShot(Shot):
    """De gesproken zin zelf als beeld: woorden slaan binnen op het moment dat ze gezegd worden."""
    variant = 1

    def setup(self):
        d, p = self.d, self.p
        words = d["words"]               # [(tekst, start, einde)] absolute tijden
        self.cta = d.get("cta", False)
        hero_i = next((i for i, w in enumerate(words) if is_num(w[0])), None) if d.get("hero", True) else None
        accent_words = set(d.get("accent", []))
        items, lines, cur, curw = [], [], [], 0.0
        size = d.get("size", 168)
        maxw = 960
        # opmaak: held (getal) op een eigen regel, rest gewoon doorlopend
        for i, (w, s, e) in enumerate(words):
            up = w.upper()
            col = p.acc if (i == hero_i or is_num(w) or up.strip(".,!?:") in accent_words) else WHITE
            if i == hero_i:
                if cur:
                    lines.append(cur)
                hs = fit_size(up.rstrip(".,"), 520, maxw)
                lines.append([(up.rstrip(".,"), hs, col, s, True)])
                cur, curw = [], 0.0
                continue
            fs = fit_size(up, size, maxw)
            wl = font(fs).getlength(up + " ")
            if cur and curw + wl > maxw:
                lines.append(cur)
                cur, curw = [], 0.0
            cur.append((up, fs, col, s, False))
            curw += wl
        if cur:
            lines.append(cur)
        # verticaal centreren
        heights = [max(font(it[1]).getbbox("H")[3] - font(it[1]).getbbox("H")[1] for it in ln) * 1.18 for ln in lines]
        total = sum(heights)
        top = (740 if not self.cta else 680) - total / 2
        y = top
        for ln, lh in zip(lines, heights):
            widths = [font(it[1]).getlength(it[0]) for it in ln]
            gap = font(ln[0][1]).getlength(" ")
            x = W / 2 - (sum(widths) + gap * (len(ln) - 1)) / 2
            for it, wdt in zip(ln, widths):
                appear = max(self.t0, it[3] - 0.05)
                items.append({"t": it[0], "size": it[1], "col": it[2], "x": x + wdt / 2, "y": y + lh / 2,
                              "at": appear, "hero": it[4]})
                self.impacts.append((appear, 1.0 if it[4] else 0.25))
                x += wdt + gap
            y += lh
        if items:
            items[0]["at"] = self.t0
        self.items = items
        self.bottom = y
        if self.cta:
            self.c1 = chip(d.get("chip1", "COMMENT BELOW"), 64, p.ink, p.acc, padx=34, pady=16)
            self.c2 = chip(d.get("chip2", "FOLLOW FOR DAILY FOOTBALL"), 50, WHITE, INK, padx=30, pady=14)
            self.c_at = d.get("chip_at", self.t0 + 0.8)

    def draw(self, img, t):
        for it in self.items:
            lt = t - it["at"]
            if lt < 0:
                continue
            im = txt(it["t"], it["size"], it["col"])
            if it["hero"]:
                ol = outline(it["t"], it["size"], self.p.acc, 4)
                put(img, ol, it["x"] + 26, it["y"] + 22, 1.0 + 0.04 * math.sin(t * 3), 0, 0.35)
            sc = 1 + (0.9 if it["hero"] else 0.55) * (1 - ease_out(lt / 0.14))
            a = ease_out(lt / 0.06)
            if lt < 0.14:   # spoortje
                put(img, im, it["x"], it["y"], sc * 1.25, 0, 0.18 * a)
            put(img, im, it["x"], it["y"], sc, 0, a)
        if self.cta:
            lt = t - self.c_at
            if lt >= 0:
                put(img, self.c1, W / 2 - 300 * (1 - ease_out(lt / 0.25)), self.bottom + 90)
                put(img, self.c2, W / 2 + 300 * (1 - ease_out((lt - 0.15) / 0.25)), self.bottom + 205,
                    1, 0, ease_out((lt - 0.15) / 0.1))


class ScoreShot(Shot):
    """Gesplitst scherm in de kleuren van beide clubs; cijfers slaan binnen wanneer ze gezegd worden."""
    captions = True

    def setup(self):
        d, p = self.d, self.p
        self.home_col = p.prim if d["focus"] == "home" else p.opp_deep
        self.away_col = p.prim if d["focus"] == "away" else p.opp_deep
        self.ht = d.get("ht")
        self.hs, self.as_ = d["hs"], d["as"]
        nums = [w for w in d["words"] if is_num(w[0]) and "–" not in w[0]]
        ft_word = next((w for w in d["words"] if w[0].lower().startswith("final")), None)
        self.ft_at = ft_word[1] if ft_word else self.t0 + 0.3
        self.h_at = nums[-2][1] if len(nums) >= 2 else self.ft_at + 0.6
        self.a_at = nums[-1][1] if len(nums) >= 1 else self.ft_at + 1.0
        self.impacts = [(self.t0 + 0.02, 0.4), (self.h_at, 0.9), (self.a_at, 1.0)]
        hn, an = d["home"].upper(), d["away"].upper()
        self.hn = txt(hn, fit_size(hn, 128, 560), WHITE)
        self.an = txt(an, fit_size(an, 128, 560), WHITE)
        self.win = "home" if self.hs > self.as_ else "away" if self.as_ > self.hs else None

    def draw(self, img, t):
        lt = t - self.t0
        p = self.p
        lay = ImageDraw.Draw(img)
        split = 800
        region(lay, -900, split, self.home_col, 0.92)
        region(lay, split, H + 900, self.away_col, 0.92)
        band(lay, split, 16, p.acc, 1.0)
        ft = t >= self.ft_at
        show_h = self.hs if t >= self.h_at else (self.ht[0] if self.ht else None)
        show_a = self.as_ if t >= self.a_at else (self.ht[1] if self.ht else None)
        lab = chip("FULL-TIME" if ft else ("HALF-TIME" if self.ht else "FULL-TIME"), 54, p.ink, p.acc, padx=28,
                   pady=12)
        put(img, lab, 70, split + 2, anchor="l")
        slide = 1 - ease_out(lt / 0.3)
        put(img, self.hn, 70 - 300 * slide, 545, anchor="l")
        put(img, self.an, 70 - 300 * slide, 1075, anchor="l")
        for val, at, cy, side in ((show_h, self.h_at, 520, "home"), (show_a, self.a_at, 1050, "away")):
            if val is None:
                continue
            k = (t - at) if t >= at else 1.0
            sc = 1 + 0.7 * (1 - ease_out(k / 0.15))
            dim = 0.45 if (ft and t >= self.a_at and self.win and self.win != side) else 1.0
            col = p.acc if (ft and t >= self.a_at and self.win == side) else WHITE
            put(img, txt(str(val), 430, col), 840, cy, sc, 0, dim)


class TableShot(Shot):
    captions = True
    variant = 2

    def setup(self):
        d = self.d
        self.rows = d["rows"][:5]
        self.head = chip(d.get("tag", "THE TABLE"), 58, self.p.ink, self.p.acc, padx=30, pady=12)
        self.sub = d.get("sub", "").upper()
        hl_i = next((i for i, r in enumerate(self.rows) if r[3]), 0)
        self.impacts = [(self.t0 + 0.02, 0.3), (self.t0 + 0.25 + hl_i * 0.07, 0.6)]

    def draw(self, img, t):
        lt = t - self.t0
        p = self.p
        put(img, self.head, 70 - 300 * (1 - ease_out(lt / 0.25)), 285, anchor="l")
        if self.sub:
            put(img, txt(self.sub, 46, WHITE, INTER, False), 70 + self.head.width + 18, 288, anchor="l")
        for i, (pos, name, pts, hl) in enumerate(self.rows):
            st = 0.05 + i * 0.07
            e = ease_out((lt - st) / 0.28)
            if e <= 0:
                continue
            y = 420 + i * 158
            x0 = 60 + (1 - e) * 900
            h = 128
            sk = h * SLANT
            row = Image.new("RGBA", (W, h + 20), (0, 0, 0, 0))
            rd = ImageDraw.Draw(row)
            col = p.acc if hl else (18, 20, 26)
            rd.polygon([(sk, 0), (960, 0), (960 - sk, h), (0, h)], fill=col + (235,))
            rd.polygon([(sk, 0), (sk + 130, 0), (130, h), (0, h)], fill=(INK if hl else p.prim) + (255,))
            tc = p.ink if hl else WHITE
            pf = font(70)
            pw = pf.getlength(str(pos))
            rd.text((sk / 2 + 65 - pw / 2, 18), str(pos), font=pf, fill=(p.acc if hl else WHITE) + (255,))
            nf = font(fit_size(name.upper(), 72, 560))
            rd.text((175, 18), name.upper(), font=nf, fill=tc + (255,))
            sf = font(80)
            pts_s = str(pts)
            rd.text((900 - sf.getlength(pts_s), 12), pts_s, font=sf, fill=tc + (255,))
            sc = 1.0 + (0.03 * (0.5 + 0.5 * math.sin(t * 6)) if hl and e >= 1 else 0)
            put(img, row, x0 + W / 2, y + h / 2, sc)


class VersusShot(Shot):
    captions = True
    variant = 1

    def setup(self):
        d = self.d
        a, b = d["a"].upper(), d["b"].upper()
        self.a = txt(a, fit_size(a, 210, 960), WHITE)
        self.b = txt(b, fit_size(b, 210, 960), WHITE)
        self.vs = outline("VS", 300, self.p.acc, 5)
        self.tag = chip(d.get("tag", "NEXT UP"), 54, self.p.ink, self.p.acc, padx=30, pady=12)
        self.impacts = [(self.t0 + 0.02, 0.5), (self.t0 + 0.3, 0.7)]

    def draw(self, img, t):
        lt = t - self.t0
        put(img, self.tag, W / 2, 330, 1 + 0.4 * (1 - ease_out(lt / 0.18)))
        put(img, self.vs, W / 2, 810, 1 + 0.05 * math.sin(t * 3), 0, 0.9)
        put(img, self.a, W / 2 - 500 * (1 - ease_out(lt / 0.22)), 610)
        lb = lt - 0.3
        if lb >= 0:
            put(img, self.b, W / 2 + 500 * (1 - ease_out(lb / 0.22)), 1010)


# ------------------------------------------------------------------ regie: van verhaal naar shots
class _Seg:
    def __init__(self, start, dur):
        self.start, self.dur, self.end = start, dur, start + dur


def build_timeline(story):
    """Scènes achter elkaar zonder overlap (de wipes doen de overgang)."""
    segs, t = [], 0.0
    for spec in story["scenes"]:
        dur = spec.get("dur") or 3.0
        segs.append(_Seg(t, dur))
        t += dur
    return segs, t


def _abs_lines(sc, start):
    return [[(w[0], start + w[1], start + w[2]) for w in ln["words"]] for ln in sc.get("lines", [])]


def direct(story, pal):
    """Maakt de shotlijst uit de scènes en de stemtiming."""
    segs, total = build_timeline(story)
    shots = []
    names = set()
    for sc in story["scenes"]:
        if sc["type"] == "score":
            names |= {sc["home"].upper(), sc["away"].upper()}
        if sc["type"] == "hook" and sc.get("team"):
            names.add(sc["team"].upper())
    acc = sorted(names)
    for seg, sc in zip(segs, story["scenes"]):
        lines = _abs_lines(sc, seg.start)
        ty = sc["type"]
        cut = (lines[1][0][1] - 0.08) if len(lines) > 1 else None
        if ty == "hook":
            end = cut if cut else seg.end
            shots.append(TitleShot(seg.start, end, sc, pal))
            if cut:
                shots.append(KineticShot(cut, seg.end, {"words": lines[1], "accent": acc}, pal))
        elif ty == "score":
            words = [w for ln in lines for w in ln]
            shots.append(ScoreShot(seg.start, seg.end, dict(sc, words=words), pal))
        elif ty == "table":
            end = cut if cut else seg.end
            shots.append(TableShot(seg.start, end, sc, pal))
            if cut:
                shots.append(KineticShot(cut, seg.end, {"words": lines[1], "accent": acc}, pal))
        elif ty == "next":
            shots.append(VersusShot(seg.start, seg.end, sc, pal))
        elif ty == "cta":
            words = lines[0] if lines else [(sc.get("q1", "") + " " + sc.get("q2", ""), seg.start, seg.end)]
            chip_at = lines[1][0][1] if len(lines) > 1 else seg.start + 1.2
            shots.append(KineticShot(seg.start, seg.end, {"words": words, "cta": True, "hero": False, "size": 200,
                                                          "chip_at": chip_at, "accent": acc,
                                                          "chip2": sc.get("follow", "Follow for daily football").upper()},
                                     pal))
        else:
            words = [w for ln in lines for w in ln] or [(sc.get("tag", ty).upper(), seg.start, seg.end)]
            shots.append(KineticShot(seg.start, seg.end, {"words": words, "accent": acc}, pal))
    for i, s in enumerate(shots):
        s.variant = (s.variant + i) % 3
    return shots, total


# ------------------------------------------------------------------ camera, wipes, effecten
def camera_state(t, impacts, shot):
    zoom = 1.0 + 0.045 * prog(t, shot.t0, max(0.5, shot.t1 - shot.t0))
    sx = sy = 0.0
    flash = chroma = 0.0
    for ti, k in impacts:
        dt = t - ti
        if dt < 0 or dt > 0.6:
            continue
        zoom += 0.035 * k * math.exp(-dt / 0.12)
        amp = 16 * k * math.exp(-dt / 0.09)
        sx += amp * math.sin(dt * 90 + ti * 7)
        sy += amp * math.cos(dt * 77 + ti * 3)
        if ti > 0.1:
            flash = max(flash, 0.32 * k * math.exp(-dt / 0.06))
        chroma = max(chroma, 9 * k * math.exp(-dt / 0.1))
    return zoom, sx, sy, flash, chroma


def apply_camera(img, zoom, sx, sy):
    if abs(zoom - 1) < 1e-3 and abs(sx) < 0.3 and abs(sy) < 0.3:
        return img
    a = 1 / zoom
    cx, cy = W / 2, H / 2
    # bron = a*(doel - c) + c - shift
    return img.transform((W, H), Image.AFFINE, (a, 0, cx - a * cx - sx, 0, a, cy - a * cy - sy),
                         resample=Image.BILINEAR)


def draw_wipe(img, t, cuts, pal):
    """Kleur-wipe van onder naar boven rond elke knip."""
    for tc in cuts:
        if not (tc - WIPE_IN <= t <= tc + WIPE_OUT):
            continue
        span = H + 900 + W * SLANT
        lead = H + 450 - span * ease_io(prog(t, tc - WIPE_IN, WIPE_IN + 0.02))
        trail = H + 450 - span * ease_io(prog(t, tc, WIPE_OUT))
        d = ImageDraw.Draw(img)
        region(d, lead, trail, pal.prim, 1.0)
        region(d, lead - 10, lead + 70, pal.acc, 1.0)
        if trail < H + 400:
            region(d, trail - 40, trail, pal.acc, 1.0)


def chroma_shift(arr, px):
    if px < 1:
        return arr
    k = int(round(px))
    out = arr.copy()
    out[:, k:, 0] = arr[:, :-k, 0]
    out[:, :-k, 2] = arr[:, k:, 2]
    return out


def draw_captions(img, t, captions, pal):
    d = ImageDraw.Draw(img)
    for c in captions:
        if not (c["t0"] - 0.04 <= t < c["t_end"]):
            continue
        words = [(w[0].upper(), w[1], w[2]) for w in c["words"]]
        size = 92
        f = font(size)
        space = f.getlength(" ")
        widths = [f.getlength(w[0]) for w in words]
        while sum(widths) + space * (len(words) - 1) > 900 and size > 56:
            size -= 6
            f = font(size)
            space = f.getlength(" ")
            widths = [f.getlength(w[0]) for w in words]
        started = [w for w in words if w[1] - 0.03 <= t]
        cur = started[-1] if started and t < started[-1][2] + 0.25 else None
        x = W / 2 - (sum(widths) + space * (len(words) - 1)) / 2
        for w, wl in zip(words, widths):
            if w is cur:
                pad = 12
                sk = (size + 20) * SLANT
                d.polygon([(x - pad + sk, CAP_Y - 6), (x + wl + pad + sk, CAP_Y - 6), (x + wl + pad, CAP_Y + size * 1.14),
                           (x - pad, CAP_Y + size * 1.14)], fill=pal.acc + (255,))
                d.text((x, CAP_Y), w[0], font=f, fill=pal.ink + (255,))
            else:
                d.text((x, CAP_Y), w[0], font=f, fill=WHITE + (255,), stroke_width=7, stroke_fill=(0, 0, 0, 230))
            x += wl + space
        break


# ------------------------------------------------------------------ render
def plan(story, th):
    pal = Palette(th)
    shots, total = direct(story, pal)
    cuts = [s.t0 for s in shots[1:]]
    impacts = sorted({(round(ti, 3), k) for s in shots for ti, k in s.impacts})
    return pal, shots, total, cuts, impacts


def render(story, out_path, audio_path, th=None, frames_at=None):
    pal, shots, total, cuts, impacts = plan(story, th)
    bd = Backdrop(pal)
    caps = story.get("captions", [])
    cap_windows = [(s.t0, s.t1) for s in shots if s.captions]
    caps = [c for c in caps if any(a - 0.05 <= c["t0"] < b for a, b in cap_windows)]

    def shot_at(t):
        for s in shots:
            if s.t0 <= t < s.t1:
                return s
        return shots[-1]

    def frame(i):
        t = i / FPS
        s = shot_at(t)
        img = bd.frame(t, s.variant)
        s.draw(img, t)
        zoom, sx, sy, flash, chroma = camera_state(t, impacts, s)
        img = apply_camera(img, zoom, sx, sy)
        draw_wipe(img, t, cuts, pal)
        draw_captions(img, t, caps, pal)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 9], fill=(255, 255, 255, 40))
        d.rectangle([0, 0, int(W * t / total), 9], fill=pal.acc + (255,))
        arr = np.asarray(img.convert("RGB"))
        if chroma >= 1:
            arr = chroma_shift(arr, chroma)
        if flash > 0.01:
            arr = np.clip(arr.astype(np.float32) + 255 * flash, 0, 255).astype(np.uint8)
        return bd.finish(arr, i)

    if frames_at:
        paths = []
        for ts in frames_at:
            p = f"{out_path}_b{ts:05.2f}.png"
            Image.fromarray(frame(int(round(ts * FPS)))).save(p)
            paths.append(p)
        return paths

    n = int(total * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-maxrate", "10M", "-bufsize", "20M",
           "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out_path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(frame(i).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg mislukt")
    return out_path
