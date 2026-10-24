"""Kiest het sterkste verhaal van de dag en schrijft de Engelse teksten (beeld + voice-over)."""
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .data import COMPETITIONS, team_name

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
def candidates(matches, tables, recent_team_ids):
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
                ang.append(("winless", 2.6, "away" if side == "home" else "home"))
        if H and A and H["pos"] <= 4 and A["pos"] <= 4:
            ang.append(("top_clash", 3.6, side or "home"))
        if total >= 6:
            ang.append(("goal_fest", 3 + 0.3 * (total - 6), side or "home"))
        if not ang:
            ang.append(("result", 1 + 0.2 * total, side or "home"))
        weight = COMPETITIONS[code][2]
        for name, score, focus in ang:
            s = score * weight
            if hid in recent_team_ids or aid in recent_team_ids:
                s *= 0.4
            out.append({"score": s, "angle": name, "focus": focus, "match": m, "code": code,
                        "H": H, "A": A, "table": tables.get(code, {}).get(hid, [])})
    out.sort(key=lambda c: c["score"], reverse=True)
    return out


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


def build_story(c, day, next_match, all_matches, rng):
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

    # --- haak + titel per invalshoek
    if angle == "perfect_run":
        big = f"{n} FROM {n}"
        sub = f"{n} games. {n} wins."
        say = [L(T(F), "make it", N(n), "from", P(N(n), "!"))]
        q, q_say = ("Can anyone", "stop them?"), L("Can anyone stop them?")
        note = pick(rng, ["Another three points.", "Still perfect.", "Nobody has stopped them yet."])
        title = f"{F}: {n} from {n} 🔥 Can anyone stop them? #Shorts"
    elif angle == "first_win":
        big = "FINALLY"
        sub = f"First win of the season"
        say = [L(T(F), "finally win!"), L("It took them", N(n), "games.")]
        q, q_say = ("Is this", "the turnaround?"), L("Is this the turnaround?")
        note = pick(rng, ["The wait is over.", "First three points of the season."])
        title = f"{F} finally win! First victory after {n} games #Shorts"
    elif angle == "upset":
        big = pick(rng, ["UPSET", "SHOCK"])
        sub = f"{ordinal(Fr['pos'])} beat {ordinal(Or['pos'])}"
        say = [L("Shock result!"), L(T(F), "just beat", P(T(O), "!"))]
        q, q_say = ("Biggest upset", "of the season?"), L("Biggest upset of the season?")
        note = f"{ordinal(Fr['pos'])} beats {ordinal(Or['pos'])}"
        title = f"SHOCK: {F} beat {O} {fs}–{os_} 😳 #Shorts"
    elif angle == "comeback":
        fh, oh = (ht_pair if focus == "home" else ht_pair[::-1])
        big = "COMEBACK"
        sub = f"{fh}–{oh} down at half-time"
        say = [L(T(F), "were losing at the break."), L("Then this happened.")]
        q, q_say = ("Comeback of", "the week?"), L("Comeback of the week?")
        note = pick(rng, ["What a second half.", "Never give up.", "A different team after the break."])
        title = f"{F} come from behind to beat {O} {fs}–{os_} 🔥 #Shorts"
    elif angle == "thrashing":
        big = f"{fs}–{os_}"
        sub = f"{F} vs {O}"
        say = [L(T(F), "just destroyed", P(T(O), "!")), L(P(SC(fs, os_), "."))]
        q, q_say = ("Statement", "of the season?"), L("Statement win of the season?")
        note = pick(rng, ["One-way traffic.", "No mercy."])
        title = f"{F} {fs}–{os_} {O}: what a statement 💥 #Shorts"
    elif angle == "goal_fest":
        tot = hs + as_
        big = f"{tot} GOALS"
        sub = "in one game"
        team_big = None
        say = [L(N(tot), "goals in one game!"), _result_line(home, away, hs, as_)]
        q, q_say = ("Game of", "the weekend?"), L("Game of the weekend?")
        note = f"{tot} goals in one game"
        title = f"{home} {hs}–{as_} {away}: {tot} goals of chaos 🤯 #Shorts"
    elif angle == "top_clash":
        big = "TOP CLASH"
        sub = "Top four. Big points."
        team_big = None
        say = [L("Top of the table clash in the", P(comp_token(comp), "!")), _result_line(home, away, hs, as_)]
        q, q_say = ("Who wins", "the league?"), L("Who wins the league?")
        note = "A direct duel at the top"
        title = f"{home} {hs}–{as_} {away}: big result at the top #Shorts"
    elif angle == "leader":
        big = "STILL TOP"
        sub = f"{Fr['pts']} points from {n} games"
        say = [L(T(F), "win again and stay top!")]
        q, q_say = ("Who wins", "the title?"), L("Can anyone catch them?")
        note = pick(rng, ["The leaders keep winning.", "Top of the table."])
        title = f"{F} stay top after beating {O} #Shorts"
    elif angle == "winless":
        big = f"{Fr['played']} GAMES"
        sub = "Still no win"
        say = [L(N(Fr["played"]), "games."), L("Still no win for", P(T(F), "."))]
        q, q_say = ("Will they", "stay up?"), L("Will they stay up?")
        note = "The wait goes on."
        title = f"{F} still winless after {Fr['played']} games 😬 #Shorts"
    else:
        big = "FULL-TIME"
        sub = comp
        team_big = None
        say = [L("Full-time in the", P(comp_token(comp), ".")), _result_line(home, away, hs, as_)]
        q, q_say = ("Who impressed", "you most?"), L("Who impressed you most?")
        note = comp
        title = f"{home} {hs}–{as_} {away} | {comp} #Shorts"

    scenes = [{"type": "hook", "tag": date_tag, "team": team_big, "big": big, "score": scoreline,
               "sub": sub, "say": say}]

    # --- scorebord
    if angle == "comeback":
        fh, oh = (ht_pair if focus == "home" else ht_pair[::-1])
        score_say = [L(T(F), "were", SC(fh, oh), "down at halftime."), L("They won", P(SC(fs, os_), "."))]
    else:
        score_say = []
        if ht_pair and ht_pair != [hs, as_] and angle not in ("goal_fest", "top_clash", "result", "thrashing"):
            score_say.append(L(SC(*ht_pair), "at halftime."))
        score_say.append(L("Final score,", T(home), P(N(hs), ","), T(away), P(N(as_), ".")))
    scenes.append({"type": "score", "tag": "FULL-TIME", "home": home, "away": away, "hs": hs, "as": as_,
                   "ht": ht_pair, "focus": focus, "note": note, "say": score_say})

    # --- stand (of, als die er niet is, seizoensvergelijking / uitslagen)
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
    elif angle == "result":
        same = [x for x in all_matches if x["competition"]["code"] == code and x.get("status") == "FINISHED"]
        res = [[team_name(x["homeTeam"]), f"{x['score']['fullTime']['home']}–{x['score']['fullTime']['away']}",
                team_name(x["awayTeam"])] for x in same[:5]]
        if len(res) > 1:
            scenes.append({"type": "results", "tag": "TODAY'S RESULTS", "sub": comp, "rows": res,
                           "say": [L("Here are today's", comp_token(comp), "results.")]})

    # --- volgende match
    if next_match:
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

    tags = [comp_tag, "#football", "#soccer", "#" + "".join(ch for ch in F if ch.isalnum())]
    desc = (f"{home} {hs}–{as_} {away} ({comp}). "
            f"{' '.join(t[0] for t in say[0])} {sub}.\n\n" + " ".join(["#Shorts"] + tags))
    title = title if len(title) <= 100 else title[:97] + "…"
    meta = {"title": title, "description": desc,
            "tags": ["football", "soccer", comp, F, O, "shorts"],
            "angle": angle, "teams": [m["homeTeam"]["id"], m["awayTeam"]["id"]], "competition": code,
            "focus_team": m["homeTeam" if focus == "home" else "awayTeam"]["id"],
            "opp_team": m["awayTeam" if focus == "home" else "homeTeam"]["id"],
            "focus_name": F, "opp_name": O}
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


def publish_time(now_utc, slot="22"):
    """Vandaag om 13:00 of 22:00 Brussel (volgens het slot); te dichtbij of voorbij -> binnen 20 minuten."""
    local = now_utc.astimezone(TZ)
    target = local.replace(hour=int(slot), minute=0, second=0, microsecond=0)
    if target - local < timedelta(minutes=20):
        target = local + timedelta(minutes=20)
    return target.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
