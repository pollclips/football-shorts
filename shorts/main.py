"""Run: data ophalen -> formaat kiezen -> video maken -> payload voor Make klaarzetten.

Twee video's per dag ("slots"):
- slot 13 (online 13:00): VOORBESCHOUWING + POLL van de grootste wedstrijd van vandaag (topclubs, CL voorrang).
  Op maandag een QUIZ. Geen grote wedstrijd vandaag? Dan het beste nog niet gebruikte verhaal van gisteren.
- slot 23 (run ±23:15, online meteen): VERSLAG van het beste verhaal van vandaag, ook de avondmatchen
  (Champions League, 21:00-wedstrijden). Geen topclub gespeeld? Dan een quiz.
Lukt niets, dan een klassement-verhaal (titelstrijd).

MODE=auto     (standaard) nieuwe video, wordt doorgestuurd naar Make
MODE=test     stuurt de voorbeeldvideo samples/test_short.mp4 (koppeltest met Make)
MODE=dry-run  maakt de video maar stuurt niets door (download onder de run, 'Artifacts')
MODE=preview  maakt de video, bewaart hem in previews/ in de repository en stuurt niets door
SLOT=13|23    (optioneel) slot kiezen; anders volgens het uur
FORMAT=auto|recap|preview|quiz   (optioneel) formaat forceren
DAY=JJJJ-MM-DD  (enkel bij dry-run/preview) een andere dag gebruiken
"""
import json
import os
import random
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import broadcast, encode, music, render, theme, voice
from .data import COMPETITIONS, Api, table_rows
from .story import (TZ, build_preview_story, build_quiz_story, build_story, build_table_story, candidates,
                    pick_preview, publish_time)

ROOT = Path(__file__).resolve().parent.parent
VIDEOS = ROOT / "videos"
PREVIEWS = ROOT / "previews"
OUT = ROOT / "out"
HISTORY = ROOT / "history.json"
KEEP_DAYS = 14
KEEP_PREVIEWS = 6
SLOTS = ("13", "23")
TOP5 = ("PL", "PD", "BL1", "SA", "FL1")
NEW_SHOTS = {"preview", "form", "poll", "quiz_q", "quiz_reveal"}


def video_url(name):
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    branch = os.environ.get("MEDIA_BRANCH", "media")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/videos/{name}"


def write_payload(name, meta, now, slot):
    OUT.mkdir(exist_ok=True)
    payload = {
        "video_url": video_url(name),
        "title": meta["title"],
        "description": meta["description"],
        "tags": ",".join(meta["tags"]),
        "privacy": "private",                 # verplicht bij ingepland publiceren
        "publish_at": publish_time(now, slot),
        "category_id": "17",                   # YouTube-categorie Sports
        "made_for_kids": False,
    }
    (OUT / "payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cleanup(today):
    for p in VIDEOS.glob("*.mp4"):
        try:
            d = datetime.strptime(p.name[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if (today - d).days > KEEP_DAYS:
            p.unlink()
            print("opgeruimd:", p.name)
    old = sorted(PREVIEWS.glob("*.mp4"), key=lambda p: p.stat().st_mtime)[:-KEEP_PREVIEWS] if PREVIEWS.exists() else []
    for p in old:
        p.unlink()


def skip(msg):
    print(msg)
    OUT.mkdir(exist_ok=True)
    (OUT / "skip").write_text("1")


def choose_slot(local, scheduled):
    s = os.environ.get("SLOT", "").strip()
    if s == "22":
        s = "23"
    if s in SLOTS:
        return s
    if local.hour in (12, 13):
        return "13"
    if local.hour in (23, 0, 1):
        return "23"
    if scheduled:
        return None        # de 'andere' tijdzone-start (zomer/winter) of te vroeg: niets doen
    return "13" if 5 <= local.hour < 17 else "23"


def local_day(m):
    return datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).astimezone(TZ).date()


# ------------------------------------------------------------------ formaten
def make_recap(api, days, history, rng, recent_tpls, trial):
    recent = set() if trial else {t for h in history[-4:] if h.get("kind", "recap") == "recap"
                                  for t in h.get("teams", [])}
    used_ids = {h["match"] for h in history[-24:] if h.get("match") and h.get("kind", "recap") == "recap"}
    weight = {days[0]: 1.0, days[1]: 0.7} if len(days) > 1 else {days[0]: 1.0}
    finished_by_day, fresh = {}, []
    for d in days:
        raw = api.matches(d.isoformat(), (d + timedelta(days=1)).isoformat())
        ms = [m for m in raw if local_day(m) == d]
        fin = [m for m in ms if m.get("status") == "FINISHED" and m["competition"]["code"] in COMPETITIONS]
        fr = [m for m in fin if m["id"] not in used_ids]
        st = {}
        for m in ms:
            st[m.get("status")] = st.get(m.get("status"), 0) + 1
        print(f"{d}: {len(ms)} wedstrijden {st}, {len(fin)} afgelopen, {len(fr)} nog niet gebruikt")
        finished_by_day[d] = fin
        fresh += [(d, m) for m in fr]

    codes = sorted({m["competition"]["code"] for _, m in fresh}, key=lambda c: -COMPETITIONS[c][2])[:6]
    tables = {}
    for code in codes:
        st = api.standings(code)
        ids = {m[s]["id"] for _, m in fresh if m["competition"]["code"] == code for s in ("homeTeam", "awayTeam")}
        tables[code] = {tid: table_rows(st, tid) for tid in ids}

    cands = []
    for d in days:
        for c in candidates([m for dd, m in fresh if dd == d], tables, recent):
            c["score"] *= weight[d]
            c["day"] = d
            cands.append(c)
    cands.sort(key=lambda c: c["score"], reverse=True)
    if not cands:
        return None, None, None
    best = cands[0]
    day = best["day"]
    print("verslag:", day, best["angle"], best["match"]["homeTeam"]["name"], "-",
          best["match"]["awayTeam"]["name"], f"(score {best['score']:.2f})")
    focus_team = best["match"]["homeTeam" if best["focus"] == "home" else "awayTeam"]["id"]
    nxt = None
    if best["angle"] in ("perfect_run", "winless", "first_win"):
        nxt = api.next_match(focus_team, (day + timedelta(days=1)).isoformat(), (day + timedelta(days=21)).isoformat())
    story, meta = build_story(best, day, nxt, finished_by_day[day], rng, recent_tpls)
    meta["match"] = best["match"]["id"]
    meta["kind"] = "recap"
    return story, meta, day


def make_preview(api, today, now, rng, recent_tpls):
    raw = api.matches(today.isoformat(), (today + timedelta(days=1)).isoformat())
    ms = [m for m in raw if local_day(m) == today]
    pub = now.astimezone(TZ).replace(hour=13, minute=0, second=0, microsecond=0)
    after = max(now, pub.astimezone(timezone.utc)) + timedelta(minutes=30)
    m = pick_preview(ms, after)
    if m is None:
        print(f"{today}: {len(ms)} wedstrijden, geen grote wedstrijd met een topclub om voor te beschouwen")
        return None, None
    code = m["competition"]["code"]
    print("voorbeschouwing:", m["homeTeam"]["name"], "-", m["awayTeam"]["name"], code, m["utcDate"])
    table = table_rows(api.standings(code), m["homeTeam"]["id"])
    f0, f1 = (today - timedelta(days=45)).isoformat(), today.isoformat()
    form_h = api.form(m["homeTeam"]["id"], f0, f1)
    form_a = api.form(m["awayTeam"]["id"], f0, f1)
    print("vorm:", "".join(form_h), "".join(form_a))
    return build_preview_story(m, table, form_h, form_a, rng, recent_tpls)


def make_quiz(api, today, rng, recent_tpls):
    rows = {code: table_rows(api.standings(code)) for code in TOP5}
    story, meta = build_quiz_story({c: r for c, r in rows.items() if r}, today, rng, recent_tpls)
    if story:
        print("quiz:", meta["title"])
    return story, meta


def make_table(api, day, slot, rng):
    start = (day.toordinal() * 2 + (0 if slot == "13" else 1)) % len(TOP5)
    for k in range(len(TOP5)):
        code = TOP5[(start + k) % len(TOP5)]
        table = table_rows(api.standings(code))
        if len(table) >= 2:
            print(f"klassement-verhaal {code}")
            nxt = api.next_match(table[0]["id"], (day + timedelta(days=1)).isoformat(),
                                 (day + timedelta(days=21)).isoformat())
            story, meta = build_table_story(code, table, day, nxt, rng)
            meta["match"] = None
            meta["kind"] = "table"
            return story, meta
    return None, None


# ------------------------------------------------------------------ run
def main():
    mode = os.environ.get("MODE", "auto").strip() or "auto"
    fmt = os.environ.get("FORMAT", "auto").strip() or "auto"
    now = datetime.now(timezone.utc)
    if os.environ.get("FAKE_NOW"):
        now = datetime.fromisoformat(os.environ["FAKE_NOW"])
    local = now.astimezone(TZ)
    OUT.mkdir(exist_ok=True)
    VIDEOS.mkdir(exist_ok=True)
    trial = mode in ("dry-run", "preview")

    # GitHub kent geen tijdzones: per slot staan er twee geplande starts (zomer- en winteruur).
    slot = choose_slot(local, bool(os.environ.get("SCHEDULED")))
    if slot is None:
        return skip(f"Geplande start om {local:%H:%M} Brusselse tijd valt buiten de vensters; overslaan.")
    today = local.date() if local.hour >= 5 else local.date() - timedelta(days=1)
    if trial and os.environ.get("DAY", "").strip():
        today = date.fromisoformat(os.environ["DAY"].strip())
    key_day = today
    print(f"slot {slot}:00 · dag {today} · formaat {fmt}")

    if mode == "test":
        name = f"{key_day.isoformat()}-{slot}u-test.mp4"
        shutil.copy(ROOT / "samples" / "test_short.mp4", VIDEOS / name)
        (OUT / "video_name").write_text(name)
        meta = {"title": "Man City: 7 from 7 🔥 Can anyone stop them? #Shorts",
                "description": "Manchester City beat Ipswich 3–2 and are 6 points clear of Arsenal. "
                               "Who wins the title?\n\n#Shorts #PremierLeague #football #soccer #ManCity",
                "tags": ["football", "soccer", "Premier League", "Man City", "Ipswich", "shorts"]}
        write_payload(name, meta, now, slot)
        return

    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    done = any(h.get("pub") == key_day.isoformat() and h.get("slot") == slot for h in history)
    if not trial and done and not os.environ.get("FORCE"):
        return skip(f"Voor {key_day} slot {slot} is er al een video; stop (FORCE=1 om toch opnieuw te maken).")
    recent_tpls = set() if trial else {h.get("tpl") for h in history[-10:] if h.get("tpl")}

    if fmt == "auto":
        fmt = ("quiz" if today.weekday() == 0 else "preview") if slot == "13" else "recap"
    order = {"preview": ["preview", "recap", "quiz", "table"],
             "recap": ["recap", "quiz", "table"],
             "quiz": ["quiz", "recap", "table"]}.get(fmt, ["recap", "quiz", "table"])

    api = Api()
    rng = random.Random(f"{today.isoformat()}-{slot}")
    story = meta = None
    day = today
    for f in order:
        if f == "preview":
            story, meta = make_preview(api, today, now, rng, recent_tpls)
        elif f == "recap":
            days = [today, today - timedelta(days=1)] if slot == "23" else [today - timedelta(days=1),
                                                                           today - timedelta(days=2)]
            story, meta, d = make_recap(api, days, history, rng, recent_tpls, trial)
            day = d or day
        elif f == "quiz":
            story, meta = make_quiz(api, today, rng, recent_tpls)
        else:
            story, meta = make_table(api, today, slot, rng)
        if story:
            break
    if story is None:
        return skip("Geen wedstrijden, geen quiz en geen klassement beschikbaar; geen video.")

    # --- clubkleuren -> thema (wisselt per video)
    fc_text = api.team_colors(meta["focus_team"])
    oc_text = api.team_colors(meta["opp_team"])
    th = theme.build(theme.team_palette(fc_text, meta["focus_name"]),
                     theme.team_palette(oc_text, meta["opp_name"]), rng)
    print(f"kleuren: {meta['focus_name']}='{fc_text}' {meta['opp_name']}='{oc_text}' -> stijl {th['style']}")

    # --- vormgeving: 'broadcast' (standaard) of 'classic'; de nieuwe formaten bestaan enkel in broadcast
    style = (os.environ.get("STYLE", "") or "broadcast").strip()
    if any(sc["type"] in NEW_SHOTS for sc in story["scenes"]):
        style = "broadcast"
    R = broadcast if style == "broadcast" else render

    # --- (stille) vertelling: bepaalt de duur van elke scène en de woordtiming van de tekst
    narrator = voice.Narrator()
    voice_wav = OUT / "voice.wav"
    voice.narrate(story, narrator, voice_wav, R.build_timeline)
    print("stem:", narrator.describe())

    name = f"{key_day.isoformat()}-{slot}u.mp4"
    (OUT / "story.json").write_text(json.dumps({"story": story, "meta": meta, "theme": th},
                                               indent=2, ensure_ascii=False))
    music_wav, mix_wav, sfx_wav = OUT / "music.wav", OUT / "mix.wav", None
    key = f"{day.isoformat()}-{slot}"
    if R is broadcast:
        _, shots, dur, cuts, impacts = broadcast.plan(story, th)
        starts = [s.t0 for s in shots]
        used = music.make_music(key, dur, [0.0], music_wav)
        sfx_wav = music.sfx(key, dur, impacts, cuts, OUT / "sfx.wav")
    else:
        starts, dur = render.scene_starts(story)
        used = music.make_music(key, dur, starts, music_wav)
    music.mix(music_wav, voice_wav, mix_wav, with_voice=narrator.active, sfx_wav=sfx_wav)
    print(f"formaat: {meta.get('kind')} · stijl: {style} · muziek: {used} · duur {dur:.1f} s · shots {len(starts)}")

    if "--frames" in sys.argv:
        print(R.render(story, str(OUT / "preview"), mix_wav, th, frames_at=[s + 0.6 for s in starts] + [0.0]))
        return
    if mode == "dry-run":
        R.render(story, OUT / "latest.mp4", mix_wav, th)
        encode.fit(OUT / "latest.mp4")
        print("proefvideo (niet verstuurd):", OUT / "latest.mp4")
        return
    if mode == "preview":
        PREVIEWS.mkdir(exist_ok=True)
        target = PREVIEWS / f"{today.isoformat()}-{slot}u-{meta.get('kind')}.mp4"
        R.render(story, target, mix_wav, th)
        encode.fit(target)
        shutil.copy(target, OUT / "latest.mp4")
        shutil.copy(OUT / "story.json", PREVIEWS / f"{today.isoformat()}-{slot}u-story.json")
        cleanup(today)
        print("preview:", target, f"{target.stat().st_size / 1e6:.1f} MB")
        return

    R.render(story, VIDEOS / name, mix_wav, th)
    encode.fit(VIDEOS / name)          # Make (gratis) weigert bestanden boven 5 MB
    shutil.copy(VIDEOS / name, OUT / "latest.mp4")
    print("video:", VIDEOS / name, f"{(VIDEOS / name).stat().st_size / 1e6:.1f} MB")
    (OUT / "video_name").write_text(name)

    history.append({"date": day.isoformat(), "pub": key_day.isoformat(), "slot": slot, "kind": meta.get("kind"),
                    "angle": meta["angle"], "tpl": meta.get("tpl"), "teams": meta["teams"],
                    "match": meta.get("match"), "title": meta["title"]})
    HISTORY.write_text(json.dumps(history[-80:], indent=2, ensure_ascii=False))
    cleanup(today)
    write_payload(name, meta, now, slot)


if __name__ == "__main__":
    main()
