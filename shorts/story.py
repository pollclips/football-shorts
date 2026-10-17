"""Kiest het sterkste verhaal van de dag en schrijft de Engelse teksten."""
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .data import COMPETITIONS, team_name

TZ = ZoneInfo("Europe/Brussels")
FOLLOW = ["Follow for daily football news", "Follow for a new story every day", "Follow for daily football stats"]


def ordinal(n):
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def pick(rng, options):
    return options[rng.randrange(len(options))]


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

    # --- haak + titel per invalshoek
    if angle == "perfect_run":
        big = f"{n} FROM {n}"
        l1 = pick(rng, [f"{F} win again.", f"{F} just keep winning.", f"{F} do it again."])
        l2 = f"{n} games. {n} wins."
        note = pick(rng, ["Another three points.", "Still perfect.", "Nobody has stopped them yet."])
        q = (pick(rng, ["Can anyone", "Who can"]), "stop them?", f"Who ends {F}'s run?")
        title = f"{F}: {n} from {n} 🔥 Can anyone stop them? #Shorts"
    elif angle == "first_win":
        big = "FINALLY"
        l1 = f"{F} win for the first time this season."
        l2 = f"It took {n} games."
        note = pick(rng, ["The wait is over.", "First three points of the season."])
        q = ("Is this", "the turnaround?", f"Can {F} build on this?")
        title = f"{F} finally win! First victory after {n} games #Shorts"
    elif angle == "upset":
        big = pick(rng, ["UPSET", "SHOCK"])
        l1 = f"{F} ({ordinal(Fr['pos'])}) beat {O} ({ordinal(Or['pos'])})."
        l2 = pick(rng, ["Nobody saw this coming.", "The table means nothing.", "What just happened?"])
        note = f"{ordinal(Fr['pos'])} beats {ordinal(Or['pos'])}"
        q = ("Biggest upset", "of the season?", f"Did you see this coming from {F}?")
        title = f"SHOCK: {F} beat {O} {fs}–{os_} 😳 #Shorts"
    elif angle == "comeback":
        fh, oh = (ht_pair if focus == "home" else ht_pair[::-1])
        big = "COMEBACK"
        l1 = f"{F} were {fh}–{oh} down at half-time."
        l2 = f"They won {fs}–{os_}."
        note = pick(rng, ["What a second half.", "Never give up.", "A different team after the break."])
        q = ("Comeback of", "the week?", f"What changed for {F} at half-time?")
        title = f"{F} come from behind to beat {O} {fs}–{os_} 🔥 #Shorts"
    elif angle == "thrashing":
        big = f"{fs}–{os_}"
        l1 = f"{F} destroy {O}."
        l2 = pick(rng, ["A statement win.", f"{fs - os_}-goal margin.", "Total domination."])
        note = pick(rng, ["One-way traffic.", "No mercy."])
        q = ("Statement", "of the season?", f"How good are {F} right now?")
        title = f"{F} {fs}–{os_} {O}: what a statement 💥 #Shorts"
    elif angle == "goal_fest":
        tot = hs + as_
        big = f"{tot} GOALS"
        l1 = f"{home} {hs}–{as_} {away}"
        l2 = pick(rng, ["What a game.", "Defending was optional.", "Pure chaos."])
        note = f"{tot} goals in one game"
        q = ("Game of", "the weekend?", "Which goal was the best?")
        title = f"{home} {hs}–{as_} {away}: {tot} goals of chaos 🤯 #Shorts"
    elif angle == "top_clash":
        big = "TOP CLASH"
        l1 = f"{home} vs {away}"
        l2 = "Top four. Big points."
        note = "A direct duel at the top"
        q = ("Who wins", "the league?", f"{home} or {away}?")
        title = f"{home} {hs}–{as_} {away}: big result at the top #Shorts"
    elif angle == "leader":
        big = "STILL TOP"
        l1 = f"{F} win again."
        l2 = f"{Fr['pts']} points from {n} games."
        note = pick(rng, ["The leaders keep winning.", "Top of the table."])
        q = ("Who wins", "the title?", f"Can anyone catch {F}?")
        title = f"{F} stay top after beating {O} #Shorts"
    elif angle == "winless":
        big = f"{Fr['played']} GAMES"
        l1 = f"Still no win for {F}."
        l2 = f"{Fr['draw']} draws. {Fr['lost']} defeats."
        note = "The wait goes on."
        q = ("Will they", "stay up?", f"What should {F} change?")
        title = f"{F} still winless after {Fr['played']} games 😬 #Shorts"
    else:
        big = "FULL-TIME"
        l1 = f"{home} {hs}–{as_} {away}"
        l2 = pick(rng, ["The big result of the day.", "Here are the numbers."])
        note = comp
        q = ("Who impressed", "you most?", "Drop your man of the match.")
        title = f"{home} {hs}–{as_} {away} | {comp} #Shorts"

    scenes = [{"type": "hook", "tag": date_tag, "big": big, "line1": l1, "line2": l2}]
    scenes.append({"type": "score", "tag": "TODAY", "home": home, "away": away, "hs": hs, "as": as_,
                   "ht": ht_pair, "focus": focus, "note": note})

    # --- seizoensvergelijking
    if Fr and Or:
        label = "THIS SEASON" if code != "CL" else "LEAGUE PHASE"
        rows = [["POINTS", Fr["pts"], Or["pts"], ""], ["GOALS SCORED", Fr["gf"], Or["gf"], ""]]
        rows.append(["WINS", Fr["won"], Or["won"], ""] if angle in ("perfect_run", "winless", "first_win")
                    else ["GOALS CONCEDED", Fr["ga"], Or["ga"], ""])
        scenes.append({"type": "bars", "tag": label, "left": F, "right": O, "rows": rows})

    # --- stand
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
        scenes.append({"type": "table", "tag": "THE TABLE", "sub": f"{comp} · after today",
                       "rows": rows, "badge": badge, "badge_text": badge_text, "foot": foot})
    elif angle == "result":
        same = [x for x in all_matches if x["competition"]["code"] == code and x.get("status") == "FINISHED"]
        res = [[team_name(x["homeTeam"]), f"{x['score']['fullTime']['home']}–{x['score']['fullTime']['away']}",
                team_name(x["awayTeam"])] for x in same[:6]]
        if len(res) > 1:
            scenes.append({"type": "results", "tag": "TODAY'S RESULTS", "sub": comp, "rows": res})

    # --- volgende match
    if next_match:
        nh, na = team_name(next_match["homeTeam"]), team_name(next_match["awayTeam"])
        when = datetime.fromisoformat(next_match["utcDate"].replace("Z", "+00:00")).astimezone(TZ)
        if angle == "perfect_run":
            l1, l2 = "Next up:", f"can they make it {n + 1} from {n + 1}?"
        elif angle == "winless":
            l1, l2 = "Next chance", f"for a first win."
        else:
            l1, l2 = "Next up for", f"{F}."
        scenes.append({"type": "next", "tag": f"NEXT UP · {when.strftime('%a %d %b').upper()}",
                       "a": nh, "b": na, "l1": l1, "l2": l2})

    scenes.append({"type": "cta", "q1": q[0], "q2": q[1], "q3": q[2],
                   "q4": pick(rng, ["Drop it in the comments", "Tell me in the comments", "Comment below"]),
                   "follow": pick(rng, FOLLOW)})

    tags = [comp_tag, "#football", "#soccer", "#" + "".join(ch for ch in F if ch.isalnum())]
    desc = (f"{home} {hs}–{as_} {away} ({comp}). "
            f"{l1} {l2} {q[2]}\n\n" + " ".join(["#Shorts"] + tags))
    title = title if len(title) <= 100 else title[:97] + "…"
    meta = {"title": title, "description": desc,
            "tags": ["football", "soccer", comp, F, O, "shorts"],
            "angle": angle, "teams": [m["homeTeam"]["id"], m["awayTeam"]["id"]], "competition": code}
    return {"scenes": scenes}, meta


def build_table_story(code, table, day, next_match, rng):
    """Reserveverhaal voor dagen zonder wedstrijden: de titelstrijd."""
    comp, comp_tag, _ = COMPETITIONS[code]
    lead, sec = table[0], table[1]
    gap = lead["pts"] - sec["pts"]
    scenes = [{"type": "hook", "tag": f"{comp.upper()} · {day.strftime('%a %d %b').upper()}",
               "big": "TITLE RACE", "line1": f"{lead['name']} lead the {comp}.",
               "line2": f"{gap} point{'s' if gap != 1 else ''} ahead of {sec['name']}."},
              {"type": "table", "tag": "THE TABLE", "sub": comp,
               "rows": [[r["pos"], r["name"], r["pts"], i == 0] for i, r in enumerate(table[:5])],
               "badge": f"+{gap}", "badge_text": f"points clear of {sec['name']}", "foot": None},
              {"type": "bars", "tag": "TOP TWO", "left": lead["name"], "right": sec["name"],
               "rows": [["POINTS", lead["pts"], sec["pts"], ""], ["GOALS SCORED", lead["gf"], sec["gf"], ""],
                        ["GOALS CONCEDED", lead["ga"], sec["ga"], ""]]}]
    if next_match:
        when = datetime.fromisoformat(next_match["utcDate"].replace("Z", "+00:00")).astimezone(TZ)
        scenes.append({"type": "next", "tag": f"NEXT UP · {when.strftime('%a %d %b').upper()}",
                       "a": team_name(next_match["homeTeam"]), "b": team_name(next_match["awayTeam"]),
                       "l1": "Next test for", "l2": f"{lead['name']}."})
    scenes.append({"type": "cta", "q1": "Who wins", "q2": "the title?", "q3": f"{lead['name']} or {sec['name']}?",
                   "q4": "Drop it in the comments", "follow": pick(rng, FOLLOW)})
    meta = {"title": f"{comp} title race: {lead['name']} {gap} points clear 🏆 #Shorts",
            "description": f"{lead['name']} lead the {comp} by {gap} points. Who wins the title?\n\n"
                           f"#Shorts {comp_tag} #football #soccer",
            "tags": ["football", "soccer", comp, lead["name"], sec["name"], "shorts"],
            "angle": "title_race", "teams": [lead["id"], sec["id"]], "competition": code}
    return {"scenes": scenes}, meta


def publish_time(now_utc):
    """Volgende 00:00 in Brussel; te dichtbij of voorbij -> binnen 20 minuten."""
    local = now_utc.astimezone(TZ)
    nxt = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if nxt - local < timedelta(minutes=20):
        nxt = local + timedelta(minutes=20)
    return nxt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
