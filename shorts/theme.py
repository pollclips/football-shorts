"""Kleuren per video: afgeleid van de clubkleuren, zodat niet elke Short er hetzelfde uitziet.

football-data.org geeft per club een tekst als "Sky Blue / White" of "Black / White / Green".
We zetten die om in RGB en bouwen er een thema mee: achtergrondtint, accentkleur, kleur tegenstander
en een achtergrondstijl (die per dag wisselt).
"""
import colorsys

NAMED = {
    "red": (214, 32, 39), "scarlet": (220, 20, 40), "crimson": (196, 18, 48),
    "white": (245, 245, 245), "black": (17, 17, 17), "grey": (140, 140, 140), "gray": (140, 140, 140),
    "silver": (190, 190, 190),
    "blue": (0, 87, 184), "royal blue": (0, 56, 168), "dark blue": (16, 40, 96), "navy": (16, 32, 72),
    "navy blue": (16, 32, 72), "sky blue": (108, 171, 221), "light blue": (108, 171, 221),
    "cyan": (0, 170, 220), "turquoise": (0, 170, 170), "azure": (0, 127, 255),
    "claret": (122, 38, 58), "maroon": (128, 0, 32), "burgundy": (128, 0, 32), "bordeaux": (110, 22, 40),
    "garnet": (130, 20, 40), "wine": (114, 47, 55),
    "yellow": (253, 208, 0), "gold": (212, 175, 55), "amber": (255, 191, 0),
    "green": (0, 135, 68), "dark green": (0, 90, 50), "light green": (100, 200, 90), "lime": (160, 210, 40),
    "orange": (245, 130, 32), "purple": (93, 46, 140), "violet": (93, 46, 140), "lilac": (180, 150, 210),
    "pink": (240, 120, 170), "brown": (120, 72, 40),
}

# reserve als de API geen kleuren geeft (op naam zoals team_name() hem teruggeeft)
FALLBACK = {
    "Man City": "Sky Blue / White", "Man United": "Red / White", "Liverpool": "Red / White",
    "Arsenal": "Red / White", "Chelsea": "Royal Blue / White", "Tottenham": "Navy Blue / White",
    "Newcastle": "Black / White", "Aston Villa": "Claret / Sky Blue", "Everton": "Royal Blue / White",
    "Brighton": "Blue / White", "Crystal Palace": "Red / Blue", "West Ham": "Claret / Sky Blue",
    "Real Madrid": "White / Gold", "Barcelona": "Garnet / Royal Blue", "Atlético": "Red / White",
    "Bayern": "Red / White", "Dortmund": "Yellow / Black", "Leverkusen": "Red / Black",
    "Gladbach": "Black / White / Green", "Stuttgart": "White / Red",
    "Juventus": "Black / White", "Inter": "Blue / Black", "Milan": "Red / Black", "Napoli": "Sky Blue / White",
    "Roma": "Maroon / Orange", "PSG": "Navy Blue / Red", "Marseille": "Sky Blue / White",
    "Ajax": "Red / White", "PSV": "Red / White", "Feyenoord": "Red / White",
    "Benfica": "Red / White", "Porto": "Blue / White", "Sporting CP": "Green / White",
}

DEFAULT_ACC = (200, 255, 70)  # kanaalkleur
DEFAULT_OPP = (112, 122, 142)
STYLES = ("glow", "stripes", "diag", "split")


def parse(colors):
    out = []
    for part in (colors or "").replace(",", "/").split("/"):
        p = part.strip().lower()
        if not p:
            continue
        if p in NAMED:
            out.append(NAMED[p])
        elif p.split()[-1] in NAMED:
            out.append(NAMED[p.split()[-1]])
    return out


def lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def sat(c):
    return colorsys.rgb_to_hsv(*(v / 255 for v in c))[1]


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def neutral(c):
    return sat(c) < 0.2   # wit, zwart, grijs, zilver


def bright(c, min_lum=0.22):
    """Maakt een kleur licht genoeg om als tekst op een donkere achtergrond te lezen."""
    t = 0.0
    out = c
    while lum(out) < min_lum and t < 0.8:
        t += 0.1
        out = mix(c, (255, 255, 255), t)
    return out


def close(a, b):
    return sum(abs(a[i] - b[i]) for i in range(3)) < 120


def team_palette(colors_text, name=None):
    cols = parse(colors_text) or parse(FALLBACK.get(name or "", ""))
    return cols


def build(focus_cols, opp_cols, rng):
    """focus_cols / opp_cols: lijsten RGB (mogen leeg zijn). Geeft een thema-dict."""
    vivid = [c for c in focus_cols if not neutral(c)]
    primary = vivid[0] if vivid else (focus_cols[0] if focus_cols else None)
    second = next((c for c in focus_cols if c != primary), None)

    if vivid:
        acc = bright(max(vivid, key=lambda c: sat(c) * 0.6 + lum(c)))
    else:
        acc = DEFAULT_ACC                               # zwart-wit club: kanaalkleur als accent

    base_dark = (9, 12, 20)
    tint_src = primary if primary and not neutral(primary) else (40, 48, 64)
    bg = mix(tint_src, base_dark, 0.84)
    glow = mix(tint_src, base_dark, 0.45)

    opp_vivid = [c for c in opp_cols if not neutral(c)]
    opp = bright(opp_vivid[0], 0.18) if opp_vivid else DEFAULT_OPP
    if close(opp, acc):
        opp = DEFAULT_OPP

    stripe_a = primary or (60, 70, 90)
    stripe_b = second or mix(stripe_a, (255, 255, 255), 0.5)
    opp_tint = mix(opp_vivid[0] if opp_vivid else (40, 48, 64), base_dark, 0.84)
    on_acc = (9, 13, 22) if lum(acc) > 0.3 else (250, 250, 250)
    return {
        "fprim": primary, "fsec": second, "oprim": opp_vivid[0] if opp_vivid else (opp_cols[0] if opp_cols else None),
        "bg": bg, "glow": glow, "acc": acc, "foc": acc, "opp": opp, "on_acc": on_acc,
        "stripe_a": stripe_a, "stripe_b": stripe_b, "opp_tint": opp_tint,
        "style": STYLES[rng.randrange(len(STYLES))],
        "hook_layout": rng.choice(["team_top", "word_top"]),
    }
