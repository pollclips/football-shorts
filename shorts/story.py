"""Kiest het sterkste verhaal van de dag en schrijft de Engelse teksten (beeld + voice-over)."""
import random
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .data import CL_BOOST, COMPETITIONS, team_name, tier

TZ = ZoneInfo("Europe/Brussels")
FOLLOW = ["Follow for daily football news", "Follow for a new story every day", "Follow for daily football stats"]

# hoe de stem een naam uitspreekt (de ondertitel toont de gewone naam)
SPOKEN = {
    "Atlético": "Atletico", "PSG": "P S G", "PSV": "P S V", "AZ": "A Z", "Nott'm Forest": "Nottingham Forest",
    "Sporting CP": "Sporting", "Bodø/Glimt": "Bodo Glimt", "Brasileirão": "Brasileirao",
    "LaLiga": "La Liga", "EURO": "Euros", "Inter": "Inter", "RB Leipzig": "Leipzig",
}

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
         "sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_ORD = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth",
        9: "ninth", 10: "tenth", 11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth",
        15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth", 19: "nineteenth", 20: "twentieth"}


def ordinal(n):
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def pick(rng, options):
    return options[rng.randrange(len(options))]


# ------------------------------------------------------------------ gesproken tekst
def words(n):
    if 0 <= n < 20:
        return _ONES[n]
    if 20 <= n < 100:
        t, o = divmod(n, 10)
        return _TENS[t] + ("" if o == 0 else " " + _ONES[o])
    return str(n)


def ord_words(n):
    if n in _ORD:
        return _ORD[n]
    if 20 < n < 100:
        t, o = divmod(n, 10)
        return _TENS[t] + " " + _ORD[o] if o else _TENS[t][:-1] + "ieth"
    return ordinal(n)


def T(name):
    """Token voor een teamnaam: (ondertitel, uitspraak)."""
    return (name, SPOKEN.get(name, name).replace("'", ""))


def N(n):
    return (str(n), words(n))


def ORD(n):
    return (ordinal(n), ord_words(n))


def SC(a, b):
    """Score als token: '3–2' wordt uitgesproken als 'three two', '2–0' als 'two nil', '1–1' als 'one all'."""
    if a == b:
        sp = "nil nil" if a == 0 else f"{words(a)} all"
    else:
        sp = f"{words(a)} {'nil' if b == 0 else words(b)}"
    return (f"{a}–{b}", sp)


def P(tok, punct):
    """Leesteken achter een token plakken (ondertitel én uitspraak)."""
    if isinstance(tok, str):
        tok = (tok, tok)
    return (tok[0] + punct, tok[1] + punct)


def L(*parts):
    """Eén zin = lijst tokens (ondertitel, uitspraak). Gewone tekst wordt per woord gesplitst."""
    out = []
    for p in parts:
        if isinstance(p, tuple):
            out.append(p)
        else:
            out += [(w, w) for w in p.split()]
    return out


def comp_token(comp):
    return (comp, SPOKEN.get(comp, comp))


# ------------------------------------------------------------------ kandidaten
NEUTRAL = ("goal_fest", "top_clash", "big_game", "result")


def candidates(matches, tables, recent_team_ids):
    """Alle mogelijke verhalen, sterkste eerst. Enkel wedstrijden met minstens één bekende club:
    een internationaal publiek swipet weg bij clubs die het niet kent."""
    out = []
    for m in matches:
        if m.get("status") != "FINISHED":
            continue
        code = m["competition"]["code"]
        if code not in COMPETITIONS:
            continue
        ft = m["score"]["fullTime"]
        if ft.get("home") is None:
            continue
        th, ta = tier(m["homeTeam"]), tier(m["awayTeam"])
        if max(th, ta) == 0:
            continue
        ht = m["score"].get("halfTime") or {}
        hs, as_ = ft["home"], ft["away"]
        hid, aid = m["homeTeam"]["id"], m["awayTeam"]["id"]
        rows = {r["id"]: r for r in tables.get(code, {}).get(hid, [])}
        H, A = rows.get(hid), rows.get(aid)
        side = "home" if hs > as_ else "away" if as_ > hs else None
        Wr, Lr = (H, A) if side == "home" else (A, H) if side == "away" else (None, None)
        total, margin = hs + as_, abs(hs - as_)
        ang = []
        if side:
            loser = "away" if side == "home" else "home"
            w_t, l_t = (th, ta) if side == "home" else (ta, th)
            if l_t >= 0.75 and l_t > w_t:                       # grote club verliest van een kleinere
                ang.append(("big_loss", 5.5 + 2 * l_t, loser))
            if Wr and Wr["played"] >= 4 and Wr["won"] == Wr["played"]:
                ang.append(("perfect_run", 6 + 0.3 * Wr["played"], side))
            if Wr and Wr["won"] == 1 and Wr["played"] >= 5:
                ang.append(("first_win", 4.2, side))
            if Wr and Lr and Wr["pos"] - Lr["pos"] >= 8:
                ang.append(("upset", 4 + 0.2 * (Wr["pos"] - Lr["pos"]), side))
            if ht.get("home") is not None:
                hh, ha = ht["home"], ht["away"]
                if (side == "home" and hh < ha) or (side == "away" and ha < hh):
                    ang.append(("comeback", 5.0, side))
            if margin >= 4:
                ang.append(("thrashing", 3 + 0.3 * margin, side))
            if Wr and Wr["pos"] == 1:
                ang.append(("leader", 2.6, side))
            if Lr and Lr["won"] == 0 and Lr["played"] >= 5:
                ang.append(("winless", 2.6, loser))
        if H and A and H["pos"] <= 4 and A["pos"] <= 4:
            ang.append(("top_clash", 3.6, side or "home"))
        if th and ta:                                           # twee bekende clubs: altijd interessant
            ang.append(("big_game", 3.2 + 0.6 * min(th, ta), side or "home"))
        if total >= 6:
            ang.append(("goal_fest", 3 + 0.3 * (total - 6), side or "home"))
        if not ang:
            ang.append(("result", 1 + 0.2 * total, side or "home"))
        weight = COMPETITIONS[code][2] * (CL_BOOST if code == "CL" else 1.0)
        for name, score, focus in ang:
            f_t, o_t = (th, ta) if focus == "home" else (ta, th)
            if name in NEUTRAL:
                f_t, o_t = max(th, ta), min(th, ta)
            elif f_t == 0:
                continue        # verhaal over een onbekende club (bv. die een grote club klopt): dan big_loss
            s = score * weight * (0.35 + f_t + 0.4 * o_t)
            if hid in recent_team_ids or aid in recent_team_ids:
                s *= 0.4
            out.append({"score": s, "angle": name, "focus": focus, "match": m, "code": code,
                        "H": H, "A": A, "table": tables.get(code, {}).get(hid, [])})
    out.sort(key=lambda c: c["score"], reverse=True)
    return out


def choose(rng, options, recent_tpls):
    """Kiest een titelvariant die de laatste tijd niet gebruikt is. options: [(sleutel, titel)]."""
    fresh = [o for o in options if o[0] not in recent_tpls] or options
    return fresh[rng.randrange(len(fresh))]


def hashtag(name):
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "#" + "".join(ch for ch in plain if ch.isalnum())


# ------------------------------------------------------------------ teksten
def _result_line(home, away, hs, as_):
    if hs > as_:
        return L(T(home), "beat", T(away), P(SC(hs, as_), "."))
    if as_ > hs:
        return L(T(away), "win", P(SC(as_, hs), ""), "away at", P(T(home), "."))
    return L(T(home), "and", T(away), "draw", P(SC(hs, as_), "."))


def _table_lines(F, Fr, table, comp):
    ct = comp_token(comp)
    lead = table[0]
    last = table[-1]["pos"] if table else None
    if Fr["pos"] == 1 and len(table) > 1:
        sec = table[1]
        gap = Fr["pts"] - sec["pts"]
        if gap == 0:
            return [L(T(F), "are top of the", P(ct, ",")), L("level on points with", P(T(sec["name"]), "."))]
        return [L(T(F), "are top of the", P(ct, ",")),
                L(N(gap), "point" if gap == 1 else "points", "clear of", P(T(sec["name"]), "."))]
    gap = lead["pts"] - Fr["pts"]
    first = (L(T(F), "are still bottom of the", P(ct, ".")) if Fr["pos"] == last
             else L(T(F), "are", ORD(Fr["pos"]), "in the", P(ct, ",")))
    if gap == 0:
        return [first, L("level on points with", P(T(lead["name"]), "."))]
    return [first, L(N(gap), "point" if gap == 1 else "points", "behind", P(T(lead["name"]), "."))]


def build_story(c, day, next_match, all_matches, rng, recent_tpls=()):
    m, code, angle, focus = c["match"], c["code"], c["angle"], c["focus"]
    comp, comp_tag, _ = COMPETITIONS[code]
    home, away = team_name(m["homeTeam"]), team_name(m["awayTeam"])
    hs, as_ = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
    ht = m["score"].get("halfTime") or {}
    ht_pair = [ht["home"], ht["away"]] if ht.get("home") is not None else None
    F, O = (home, away) if focus == "home" else (away, home)
    Fr, Or = (c["H"], c["A"]) if focus == "home" else (c["A"], c["H"])
    fs, os_ = (hs, as_) if focus == "home" else (as_, hs)
    date_tag = f"{comp.upper()} · {day.strftime('%a %d %b').upper()}"
    n = Fr["played"] if Fr else None
    scoreline = f"{home.upper()} {hs}–{as_} {away.upper()}"
    team_big = F.upper()
    res = f"{home} {hs}–{as_} {away}"

    # --- haak + titel per invalshoek (titels: clubnaam vooraan, telkens een andere variant)
    if angle == "big_loss":
        big = pick(rng, ["BEATEN", "STUNNED", "UPSET"])
        sub = f"lost {os_}–{fs} to {O}"
        say = [L(T(F), "lose!"), L(T(O), "beat them", P(SC(os_, fs), "."))]
        q, q_say = ("Crisis", "or blip?"), L("Crisis or just a blip?")
        note = pick(rng, ["Nobody saw that coming.", "A night to forget.", "Big points dropped."])
        titles = [("bl1", f"{F} lose to {O} 😳"), ("bl2", f"{O} stun {F} {os_}–{fs}"),
                  ("bl3", f"Nobody saw this coming: {F} beaten by {O}"), ("bl4", f"What happened to {F}? {res}")]
    elif angle == "perfect_run":
        big = f"{n} FROM {n}"
        sub = f"{n} games. {n} wins."
        say = [L(T(F), "make it", N(n), "from", P(N(n), "!"))]
        q, q_say = ("Can anyone", "stop them?"), L("Can anyone stop them?")
        note = pick(rng, ["Another three points.", "Still perfect.", "Nobody has stopped them yet."])
        titles = [("pr1", f"{F} make it {n} from {n} 🔥"), ("pr2", f"{n} games, {n} wins: can anyone stop {F}?"),
                  ("pr3", f"{F} are still perfect ({n}/{n})")]
    elif angle == "first_win":
        big = "FINALLY"
        sub = "First win of the season"
        say = [L(T(F), "finally win!"), L("It took them", N(n), "games.")]
        q, q_say = ("Is this", "the turnaround?"), L("Is this the turnaround?")
        note = pick(rng, ["The wait is over.", "First three points of the season."])
        titles = [("fw1", f"{F} finally win after {n} games"), ("fw2", f"The wait is over for {F}")]
    elif angle == "upset":
        big = pick(rng, ["UPSET", "GIANT KILLING"])
        sub = f"{ordinal(Fr['pos'])} beat {ordinal(Or['pos'])}"
        say = [L("Upset!"), L(T(F), "just beat", P(T(O), "!"))]
        q, q_say = ("Biggest upset", "of the season?"), L("Biggest upset of the season?")
        note = f"{ordinal(Fr['pos'])} beats {ordinal(Or['pos'])}"
        titles = [("up1", f"{F} beat {O} {fs}–{os_} 😳"), ("up2", f"Did you see {F} vs {O}?")]
    elif angle == "comeback":
        fh, oh = (ht_pair if focus == "home" else ht_pair[::-1])
        big = "COMEBACK"
        sub = f"{fh}–{oh} down at half-time"
        say = [L(T(F), "were losing at the break."), L("Then this happened.")]
        q, q_say = ("Comeback of", "the week?"), L("Comeback of the week?")
        note = pick(rng, ["What a second half.", "Never give up.", "A different team after the break."])
        titles = [("cb1", f"{F} were losing at half-time… then this happened"),
                  ("cb2", f"From {fh}–{oh} down to a {fs}–{os_} win: {F} 🔥"),
                  ("cb3", f"{F} turn it around against {O}")]
    elif angle == "thrashing":
        big = f"{fs}–{os_}"
        sub = f"{F} vs {O}"
        say = [L(T(F), "just destroyed", P(T(O), "!")), L(P(SC(fs, os_), "."))]
        q, q_say = ("Statement", "of the season?"), L("Statement win of the season?")
        note = pick(rng, ["One-way traffic.", "No mercy."])
        titles = [("th1", f"{F} {fs}–{os_} {O} 💥"), ("th2", f"{F} put {fs} past {O}"),
                  ("th3", f"{O} had no answer: {F} win {fs}–{os_}")]
    elif angle == "goal_fest":
        tot = hs + as_
        big = f"{tot} GOALS"
        sub = "in one game"
        team_big = None
        say = [L(N(tot), "goals in one game!"), _result_line(home, away, hs, as_)]
        q, q_say = ("Game of", "the weekend?"), L("Game of the weekend?")
        note = f"{tot} goals in one game"
        titles = [("gf1", f"{res}: {tot} goals 🤯"), ("gf2", f"{tot} goals between {home} and {away}")]
    elif angle in ("top_clash", "big_game"):
        big = "TOP CLASH" if angle == "top_clash" else pick(rng, ["BIG GAME", "FULL-TIME"])
        sub = "Top four. Big points." if angle == "top_clash" else comp
        team_big = None
        say = [L("Big game in the", P(comp_token(comp), "!")), _result_line(home, away, hs, as_)]
        q, q_say = ("Who was", "the best player?"), L("Who was the best player?")
        note = comp
        titles = [("bg1", f"{res} | {comp}"), ("bg2", f"Full-time: {res}"),
                  ("bg3", f"{home} vs {away}: who won the big one?")]
    elif angle == "leader":
        big = "STILL TOP"
        sub = f"{Fr['pts']} points from {n} games"
        say = [L(T(F), "win again and stay top!")]
        q, q_say = ("Who wins", "the title?"), L("Can anyone catch them?")
        note = pick(rng, ["The leaders keep winning.", "Top of the table."])
        titles = [("ld1", f"{F} win again and stay top of the {comp}"), ("ld2", f"{F} are still top: {fs}–{os_} vs {O}")]
    elif angle == "winless":
        big = f"{Fr['played']} GAMES"
        sub = "Still no win"
        say = [L(N(Fr["played"]), "games."), L("Still no win for", P(T(F), "."))]
        q, q_say = ("What has", "gone wrong?"), L("What has gone wrong?")
        note = "The wait goes on."
        titles = [("wl1", f"{F} still haven't won in {Fr['played']} games 😬"), ("wl2", f"What is going on at {F}?")]
    else:
        big = "FULL-TIME"
        sub = comp
        team_big = None
        say = [L("Full-time in the", P(comp_token(comp), ".")), _result_line(home, away, hs, as_)]
        q, q_say = ("Who impressed", "you most?"), L("Who impressed you most?")
        note = comp
        titles = [("rs1", f"{res} | {comp}"), ("rs2", f"Full-time: {res}")]
    tpl, title = choose(rng, titles, recent_tpls)
    title = f"{title} #Shorts"

    scenes = [{"type": "hook", "tag": date_tag, "team": team_big, "big": big, "score": scoreline,
               "sub": sub, "say": say}]

    # --- scorebord
    if angle == "comeback":
        fh, oh = (ht_pair if focus == "home" else ht_pair[::-1])
        score_say = [L(T(F), "were", SC(fh, oh), "down at halftime."), L("They won", P(SC(fs, os_), "."))]
    else:
        score_say = []
        if ht_pair and ht_pair != [hs, as_] and angle not in ("goal_fest", "top_clash", "big_game", "result",
                                                               "thrashing"):
            score_say.append(L(SC(*ht_pair), "at halftime."))
        score_say.append(L("Final score,", T(home), P(N(hs), ","), T(away), P(N(as_), ".")))
    scenes.append({"type": "score", "tag": "FULL-TIME", "home": home, "away": away, "hs": hs, "as": as_,
                   "ht": ht_pair, "focus": focus, "note": note, "say": score_say})

    # --- stand (of, als die er niet is, seizoensvergelijking)
    table = c["table"]
    idx = next((i for i, r in enumerate(table) if Fr and r["id"] == Fr["id"]), None)
    if Fr and table and idx is not None:
        lo = max(0, min(idx - 2, len(table) - 5))
        win = table[lo:lo + 5]
        rows = [[r["pos"], r["name"], r["pts"], r["id"] == Fr["id"]] for r in win]
        badge = badge_text = foot = None
        if Fr["pos"] == 1 and len(table) > 1:
            sec = table[1]
            gap = Fr["pts"] - sec["pts"]
            badge, badge_text = f"+{gap}", f"points clear of {sec['name']}"
            diff = Fr["played"] - sec["played"]
            if diff > 0:
                foot = f"* {sec['name']} have {'a game' if diff == 1 else f'{diff} games'} in hand"
                for r in rows:
                    if r[1] == sec["name"]:
                        r[1] += "*"
        elif Fr["pos"] > 1:
            lead = table[0]
            badge, badge_text = f"-{lead['pts'] - Fr['pts']}", f"points behind {lead['name']}"
        scenes.append({"type": "table", "tag": "THE TABLE", "sub": f"{comp} · latest",
                       "rows": rows, "badge": badge, "badge_text": badge_text, "foot": foot,
                       "say": _table_lines(F, Fr, table, comp)})
    elif Fr and Or:
        label = "THIS SEASON" if code != "CL" else "LEAGUE PHASE"
        rows = [["POINTS", Fr["pts"], Or["pts"], ""], ["GOALS SCORED", Fr["gf"], Or["gf"], ""],
                ["WINS", Fr["won"], Or["won"], ""]]
        scenes.append({"type": "bars", "tag": label, "left": F, "right": O, "rows": rows,
                       "say": [L("This season,", T(F), "have", N(Fr["won"]), "wins from", N(Fr["played"]), "games.")]})

    # --- volgende match: enkel als die het verhaal afmaakt (korter = meer mensen kijken tot het einde)
    if next_match and angle in ("perfect_run", "winless", "first_win"):
        nh, na = team_name(next_match["homeTeam"]), team_name(next_match["awayTeam"])
        when = datetime.fromisoformat(next_match["utcDate"].replace("Z", "+00:00")).astimezone(TZ)
        focus_id = m["homeTeam" if focus == "home" else "awayTeam"]["id"]
        at_home = next_match["homeTeam"]["id"] == focus_id
        opp_next = na if at_home else nh
        if angle == "perfect_run":
            l1, l2 = "Next up:", f"can they make it {n + 1} from {n + 1}?"
        elif angle == "winless":
            l1, l2 = "Next chance", "for a first win."
        else:
            l1, l2 = "Next up for", f"{F}."
        scenes.append({"type": "next", "tag": f"NEXT UP · {when.strftime('%a %d %b').upper()}",
                       "a": nh, "b": na, "l1": l1, "l2": l2,
                       "say": [L("Next up,", P(T(opp_next), ","), "at home" if at_home else "away",
                                 "on", P(when.strftime("%A"), "."))]})

    scenes.append({"type": "cta", "q1": q[0], "q2": q[1], "q3": f"{F}: what do you think?" if F else "",
                   "q4": pick(rng, ["Drop it in the comments", "Tell me in the comments", "Comment below"]),
                   "follow": pick(rng, FOLLOW), "captions": False,
                   "say": [q_say, L(pick(rng, ["Comment below!", "Let me know in the comments!"]))]})

    opp_team = m["awayTeam" if focus == "home" else "homeTeam"]
    tags = ["#Shorts", hashtag(F)] + ([hashtag(O)] if tier(opp_team) else []) + [comp_tag, "#football", "#soccer"]
    desc = (f"{res} ({comp}). {' '.join(t[0] for t in say[0])} {sub[:1].upper() + sub[1:].rstrip(".")}. "
            f"{q[0]} {q[1]} Comment below!\n\n" + " ".join(tags))
    title = title if len(title) <= 100 else title[:97] + "…"
    meta = {"title": title, "description": desc, "tpl": tpl,
            "tags": ["football", "soccer", comp, F, O, f"{F} vs {O}", "shorts"],
            "angle": angle, "teams": [m["homeTeam"]["id"], m["awayTeam"]["id"]], "competition": code,
            "focus_team": m["homeTeam" if focus == "home" else "awayTeam"]["id"],
            "opp_team": opp_team["id"], "focus_name": F, "opp_name": O}
    return {"scenes": scenes}, meta


def build_table_story(code, table, day, next_match, rng):
    """Reserveverhaal voor dagen zonder wedstrijden: de titelstrijd."""
    comp, comp_tag, _ = COMPETITIONS[code]
    lead, sec = table[0], table[1]
    gap = lead["pts"] - sec["pts"]
    ct = comp_token(comp)
    scenes = [{"type": "hook", "tag": f"{comp.upper()} · {day.strftime('%a %d %b').upper()}",
               "team": lead["name"].upper(), "big": "TITLE RACE", "score": None,
               "sub": f"{gap} point{'s' if gap != 1 else ''} ahead of {sec['name']}",
               "say": [L("The", ct, "title race!"),
                       L(T(lead["name"]), "are", N(gap), "point" if gap == 1 else "points", "clear.")]},
              {"type": "table", "tag": "THE TABLE", "sub": comp,
               "rows": [[r["pos"], r["name"], r["pts"], i == 0] for i, r in enumerate(table[:5])],
               "badge": f"+{gap}", "badge_text": f"points clear of {sec['name']}", "foot": None,
               "say": [L(T(sec["name"]), "are second,", "on", N(sec["pts"]), "points.")]},
              {"type": "bars", "tag": "TOP TWO", "left": lead["name"], "right": sec["name"],
               "rows": [["POINTS", lead["pts"], sec["pts"], ""], ["GOALS SCORED", lead["gf"], sec["gf"], ""],
                        ["GOALS CONCEDED", lead["ga"], sec["ga"], ""]],
               "say": [L(T(lead["name"]), "have scored", N(lead["gf"]), "goals so far.")]}]
    if next_match:
        when = datetime.fromisoformat(next_match["utcDate"].replace("Z", "+00:00")).astimezone(TZ)
        at_home = next_match["homeTeam"]["id"] == lead["id"]
        opp = team_name(next_match["awayTeam"] if at_home else next_match["homeTeam"])
        scenes.append({"type": "next", "tag": f"NEXT UP · {when.strftime('%a %d %b').upper()}",
                       "a": team_name(next_match["homeTeam"]), "b": team_name(next_match["awayTeam"]),
                       "l1": "Next test for", "l2": f"{lead['name']}.",
                       "say": [L("Next up,", P(T(opp), ","), "at home" if at_home else "away",
                                 "on", P(when.strftime("%A"), "."))]})
    scenes.append({"type": "cta", "q1": "Who wins", "q2": "the title?", "q3": f"{lead['name']} or {sec['name']}?",
                   "q4": "Drop it in the comments", "follow": pick(rng, FOLLOW), "captions": False,
                   "say": [L("Who wins the title?"), L("Comment below!")]})
    meta = {"title": f"{comp} title race: {lead['name']} {gap} points clear 🏆 #Shorts",
            "description": f"{lead['name']} lead the {comp} by {gap} points. Who wins the title?\n\n"
                           f"#Shorts {comp_tag} #football #soccer",
            "tags": ["football", "soccer", comp, lead["name"], sec["name"], "shorts"],
            "angle": "title_race", "teams": [lead["id"], sec["id"]], "competition": code,
            "focus_team": lead["id"], "opp_team": sec["id"], "focus_name": lead["name"], "opp_name": sec["name"]}
    return {"scenes": scenes}, meta


# ------------------------------------------------------------------ voorbeschouwing + poll (13:00)
def pick_preview(matches, after_utc, rng=None):
    """Grootste wedstrijd van vandaag die nog moet beginnen, met minstens één bekende club."""
    best, best_s = None, 0.0
    for m in matches:
        if m.get("status") not in ("SCHEDULED", "TIMED"):
            continue
        code = m["competition"]["code"]
        if code not in COMPETITIONS:
            continue
        ko = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
        if ko < after_utc:
            continue
        th, ta = tier(m["homeTeam"]), tier(m["awayTeam"])
        if max(th, ta) < 0.75:
            continue
        s = (max(th, ta) + 1.2 * min(th, ta)) * COMPETITIONS[code][2] * (CL_BOOST if code == "CL" else 1.0)
        if s > best_s:
            best, best_s = m, s
    return best


def build_preview_story(m, table, form_h, form_a, rng, recent_tpls=()):
    code = m["competition"]["code"]
    comp, comp_tag, _ = COMPETITIONS[code]
    home, away = team_name(m["homeTeam"]), team_name(m["awayTeam"])
    ko = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).astimezone(TZ)
    when = "TONIGHT" if ko.hour >= 18 else "TODAY"
    rows = {r["id"]: r for r in table}
    Hr, Ar = rows.get(m["homeTeam"]["id"]), rows.get(m["awayTeam"]["id"])

    scenes = [{"type": "preview", "tag": f"{when} · {comp.upper()}", "a": home, "b": away,
               "chip": "WHO WINS?", "min_dur": 2.6}]
    k = min(len(form_h), len(form_a), 5)
    if k >= 4:      # gratis data kent enkel de grote competities: te weinig uitslagen = niet tonen
        scenes.append({"type": "form", "tag": f"LAST {k} GAMES", "rows": [[home, form_h[-k:]], [away, form_a[-k:]]],
                       "min_dur": 3.4})
    if Hr and Ar:
        label = "LEAGUE PHASE" if code == "CL" else "THIS SEASON"
        scenes.append({"type": "bars", "tag": label, "left": home, "right": away,
                       "rows": [["POSITION", Hr["pos"], Ar["pos"], "pos"], ["POINTS", Hr["pts"], Ar["pts"], ""],
                                ["GOALS SCORED", Hr["gf"], Ar["gf"], ""]],
                       "min_dur": 3.6})
    scenes.append({"type": "poll", "q": "WHO WINS?", "home": home, "away": away,
                   "follow": pick(rng, FOLLOW).upper(), "min_dur": 4.2})

    titles = [("pv1", f"{home} vs {away} {when.lower()}: who wins? 🤔"),
              ("pv2", f"{home} or {away}? Make your prediction 👇"),
              ("pv3", f"Who wins {home} vs {away}?")]
    tpl, title = choose(rng, titles, recent_tpls)
    tags = ["#Shorts", hashtag(home), hashtag(away), comp_tag, "#football", "#soccer"]
    desc = (f"{home} vs {away} ({comp}), {when.lower()}. Who wins? "
            f"Comment 1 for {home}, X for a draw or 2 for {away}!\n\n" + " ".join(tags))
    meta = {"title": f"{title} #Shorts", "description": desc, "tpl": tpl,
            "tags": ["football", "soccer", comp, home, away, f"{home} vs {away}", "prediction", "shorts"],
            "angle": "preview", "teams": [m["homeTeam"]["id"], m["awayTeam"]["id"]], "competition": code,
            "focus_team": m["homeTeam"]["id"], "opp_team": m["awayTeam"]["id"],
            "focus_name": home, "opp_name": away, "match": m["id"], "kind": "preview"}
    return {"scenes": scenes}, meta


# ------------------------------------------------------------------ quiz (wekelijks en als reserve)
QUIZ_TYPES = [
    # sleutel, vraag, veld, hoger is beter?, eenheid
    ("most_scored", "Which club has scored the most goals?", "gf", True, "GOALS"),
    ("fewest_conceded", "Which club has conceded the fewest goals?", "ga", False, "CONCEDED"),
    ("most_points", "Which club has the most points?", "pts", True, "POINTS"),
    ("most_wins", "Which club has won the most games?", "won", True, "WINS"),
    ("most_lost", "Which club has lost the most games?", "lost", True, "DEFEATS"),
]


def build_quiz_story(rows_by_comp, day, rng, recent_tpls=()):
    """rows_by_comp: {code: tabelrijen}. Vier bekende clubs, één vraag, aftellen, antwoord."""
    pool = []
    for code, rows in rows_by_comp.items():
        for r in rows:
            t = tier({"shortName": r["name"], "id": r["id"]})
            if t >= 0.75 and r["played"] >= 3:
                pool.append(dict(r, code=code, tier=t))
    if len(pool) < 4:
        return None, None
    types = [q for q in QUIZ_TYPES if q[0] not in recent_tpls] or QUIZ_TYPES
    rng.shuffle(types)
    for key, question, field, higher, unit in types:
        for _ in range(30):
            opts = rng.sample(pool, 4)
            vals = [o[field] for o in opts]
            best = max(vals) if higher else min(vals)
            if vals.count(best) == 1 and len(set(vals)) >= 3:
                break
        else:
            continue
        ans = vals.index(best)
        q_up = question.upper()
        comps = sorted({COMPETITIONS[o["code"]][0] for o in opts})
        scenes = [
            {"type": "quiz_q", "q": q_up, "sub": "LEAGUE GAMES THIS SEASON", "opts": [o["name"] for o in opts],
             "min_dur": 7.2},
            {"type": "quiz_reveal", "q": q_up, "answer": ans, "unit": unit,
             "opts": [[o["name"], o[field], o["played"]] for o in opts], "min_dur": 4.4},
            {"type": "cta", "q1": "How many", "q2": "got it right?", "q3": "", "q4": "Comment below",
             "follow": pick(rng, FOLLOW), "captions": False,
             "say": [L("Did you get it right?"), L("Comment your answer!")]},
        ]
        titles = [(key + "_a", f"Football quiz: {question[0].lower() + question[1:]} 🤔"),
                  (key + "_b", f"Only real fans get this right: {question}"),
                  (key + "_c", f"Can you guess? {question}")]
        tpl, title = choose(rng, titles, recent_tpls)
        tags = ["#Shorts", "#footballquiz", "#quiz"] + [hashtag(o["name"]) for o in opts] + ["#football", "#soccer"]
        desc = (f"{question} {', '.join(o['name'] for o in opts)} — league games this season "
                f"({', '.join(comps)}). Comment your answer before the reveal!\n\n" + " ".join(tags))
        meta = {"title": f"{title} #Shorts", "description": desc, "tpl": key,
                "tags": ["football", "soccer", "football quiz", "quiz"] + [o["name"] for o in opts] + ["shorts"],
                "angle": "quiz", "teams": [o["id"] for o in opts], "competition": opts[ans]["code"],
                "focus_team": opts[0]["id"], "opp_team": opts[1]["id"],
                "focus_name": opts[0]["name"], "opp_name": opts[1]["name"], "match": None, "kind": "quiz"}
        return {"scenes": scenes}, meta
    return None, None


def publish_time(now_utc, slot="13"):
    """Slot 13: vandaag om 13:00 Brussel (te dichtbij of voorbij -> binnen 15 minuten).
    Slot 23 (laat op de avond, na de laatste wedstrijden): zo snel mogelijk, binnen 10 minuten."""
    local = now_utc.astimezone(TZ)
    if slot == "23":
        target = local + timedelta(minutes=10)
    else:
        target = local.replace(hour=int(slot), minute=0, second=0, microsecond=0)
        if target - local < timedelta(minutes=15):
            target = local + timedelta(minutes=15)
    return target.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
