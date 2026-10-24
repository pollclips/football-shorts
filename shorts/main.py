"""Run: data ophalen -> verhaal kiezen -> stem + video maken -> payload voor Make klaarzetten.

Twee video's per dag ("slots"), online om 13:00 en 22:00 Brusselse tijd:
- slot 22 (run ±21:20): beste verhaal van de wedstrijden van vandaag die al gedaan zijn
- slot 13 (run ±12:20): beste nog niet gebruikte verhaal van gisteren (ook de late avondmatchen)
Geen wedstrijden? Dan een klassement-verhaal, elke keer een andere competitie.

MODE=auto     (standaard) nieuwe video, wordt doorgestuurd naar Make
MODE=test     stuurt de voorbeeldvideo samples/test_short.mp4 (eerste koppeltest met Make)
MODE=dry-run  maakt de video maar stuurt niets door (download onder de run, 'Artifacts')
MODE=preview  maakt de video, bewaart hem in previews/ in de repository en stuurt niets door
SLOT=13|22    (optioneel) slot kiezen; anders volgens het uur
DAY=JJJJ-MM-DD  (enkel bij dry-run/preview) een andere wedstrijddag gebruiken
"""
import json
import os
import random
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import broadcast, music, render, theme, voice
from .data import COMPETITIONS, Api, table_rows
from .story import TZ, build_story, build_table_story, candidates, publish_time

ROOT = Path(__file__).resolve().parent.parent
VIDEOS = ROOT / "videos"
PREVIEWS = ROOT / "previews"
OUT = ROOT / "out"
HISTORY = ROOT / "history.json"
KEEP_DAYS = 14
KEEP_PREVIEWS = 6
SLOTS = ("13", "22")
FALLBACK_COMPS = ("PL", "PD", "BL1", "SA", "FL1")


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
        "publish_at": publish_time(now, slot),  # 13:00 of 22:00 Brussel, in UTC
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
    if s in SLOTS:
        return s
    if local.hour in (12, 13):
        return "13"
    if local.hour in (21, 22):
        return "22"
    if scheduled:
        return None        # de 'andere' tijdzone-start (zomer/winter): niets doen
    return "13" if local.hour < 17 else "22"


def main():
    mode = os.environ.get("MODE", "auto").strip() or "auto"
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
    day = local.date() if slot == "22" else local.date() - timedelta(days=1)
    if trial and os.environ.get("DAY", "").strip():
        day = date.fromisoformat(os.environ["DAY"].strip())
    pub_day = local.date()
    print(f"slot {slot}:00 · wedstrijddag {day} · online op {pub_day}")

    if mode == "test":
        name = f"{pub_day.isoformat()}-{slot}u-test.mp4"
        shutil.copy(ROOT / "samples" / "test_short.mp4", VIDEOS / name)
        (OUT / "video_name").write_text(name)
        meta = {"title": "Man City: 7 from 7 🔥 Can anyone stop them? #Shorts",
                "description": "Manchester City beat Ipswich 3–2 and are 6 points clear of Arsenal. "
                               "Who wins the title?\n\n#Shorts #PremierLeague #football #soccer #ManCity",
                "tags": ["football", "soccer", "Premier League", "Man City", "Ipswich", "shorts"]}
        write_payload(name, meta, now, slot)
        return

    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    done = any(h.get("pub") == pub_day.isoformat() and h.get("slot") == slot for h in history)
    if not trial and done and not os.environ.get("FORCE"):
        return skip(f"Voor {pub_day} {slot}:00 is er al een video; stop (FORCE=1 om toch opnieuw te maken).")
    recent = set() if trial else {t for h in history[-4:] for t in h.get("teams", [])}
    used_ids = {h["match"] for h in history[-16:] if h.get("match")}
    used_pairs = {(h.get("date"), tuple(h.get("teams", []))) for h in history[-16:]}

    # De gratis data zet uitslagen soms pas uren later op 'afgelopen'. Daarom kijken we ook naar de dag ervoor
    # (iets lager gewaardeerd): zo is er altijd een echt wedstrijdverhaal als dat er is.
    api = Api()
    days = [day, day - timedelta(days=1)]
    weight = {days[0]: 1.0, days[1]: 0.75}
    finished_by_day, fresh = {}, []
    for d in days:
        raw = api.matches(d.isoformat(), (d + timedelta(days=1)).isoformat())
        ms = [m for m in raw
              if datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).astimezone(TZ).date() == d]
        fin = [m for m in ms if m.get("status") == "FINISHED" and m["competition"]["code"] in COMPETITIONS]
        fr = [m for m in fin if m["id"] not in used_ids
              and (d.isoformat(), (m["homeTeam"]["id"], m["awayTeam"]["id"])) not in used_pairs]
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

    rng = random.Random(f"{day.isoformat()}-{slot}")
    # volgende match: vanaf morgen (de data van vandaag kan nog achterlopen)
    nxt_from, nxt_to = (local.date() + timedelta(days=1)).isoformat(), (local.date() + timedelta(days=21)).isoformat()
    cands = []
    for d in days:
        for c in candidates([m for dd, m in fresh if dd == d], tables, recent):
            c["score"] *= weight[d]
            c["day"] = d
            cands.append(c)
    cands.sort(key=lambda c: c["score"], reverse=True)
    if cands:
        best = cands[0]
        day = best["day"]
        print("gekozen:", day, best["angle"], best["match"]["homeTeam"]["name"], "-",
              best["match"]["awayTeam"]["name"], f"(score {best['score']:.2f})")
        focus_team = best["match"]["homeTeam" if best["focus"] == "home" else "awayTeam"]["id"]
        nxt = api.next_match(focus_team, nxt_from, nxt_to)
        story, meta = build_story(best, day, nxt, finished_by_day[day], rng)
        meta["match"] = best["match"]["id"]
    else:
        start = (day.toordinal() * 2 + (0 if slot == "13" else 1)) % len(FALLBACK_COMPS)
        story = meta = None
        for k in range(len(FALLBACK_COMPS)):
            code = FALLBACK_COMPS[(start + k) % len(FALLBACK_COMPS)]
            table = table_rows(api.standings(code))
            if len(table) >= 2:
                print(f"Geen nieuwe afgelopen wedstrijden -> klassement-verhaal {code}")
                nxt = api.next_match(table[0]["id"], nxt_from, nxt_to)
                story, meta = build_table_story(code, table, day, nxt, rng)
                meta["match"] = None
                break
        if story is None:
            return skip("Geen wedstrijden en geen klassement beschikbaar; geen video.")

    # --- clubkleuren -> thema (wisselt per video)
    fc_text = api.team_colors(meta["focus_team"])
    oc_text = api.team_colors(meta["opp_team"])
    th = theme.build(theme.team_palette(fc_text, meta["focus_name"]),
                     theme.team_palette(oc_text, meta["opp_name"]), rng)
    print(f"kleuren: {meta['focus_name']}='{fc_text}' {meta['opp_name']}='{oc_text}' -> stijl {th['style']}")

    # --- vormgeving: 'broadcast' (v3, standaard) of 'classic' (v2)
    style = (os.environ.get("STYLE", "") or "broadcast").strip()
    R = broadcast if style == "broadcast" else render

    # --- stem + ondertitels (bepaalt ook de duur van elke scène)
    narrator = voice.Narrator()
    voice_wav = OUT / "voice.wav"
    voice.narrate(story, narrator, voice_wav, R.build_timeline)
    print("stem:", narrator.describe())

    name = f"{pub_day.isoformat()}-{slot}u.mp4"
    (OUT / "story.json").write_text(json.dumps({"story": story, "meta": meta, "theme": th},
                                               indent=2, ensure_ascii=False))
    music_wav, mix_wav, sfx_wav = OUT / "music.wav", OUT / "mix.wav", None
    key = f"{day.isoformat()}-{slot}"
    if R is broadcast:
        _, shots, dur, cuts, impacts = broadcast.plan(story, th)
        starts = [s.t0 for s in shots]
        used = music.make_music(key, dur, [0.0], music_wav)   # whooshes zitten in de effecten
        sfx_wav = music.sfx(key, dur, impacts, cuts, OUT / "sfx.wav")
    else:
        starts, dur = render.scene_starts(story)
        used = music.make_music(key, dur, starts, music_wav)
    music.mix(music_wav, voice_wav, mix_wav, with_voice=narrator.active, sfx_wav=sfx_wav)
    print(f"stijl: {style} · muziek: {used} · duur {dur:.1f} s · shots {len(starts)}")

    if "--frames" in sys.argv:
        print(R.render(story, str(OUT / "preview"), mix_wav, th, frames_at=[s + 0.6 for s in starts] + [0.0]))
        return
    if mode == "dry-run":
        R.render(story, OUT / "latest.mp4", mix_wav, th)
        print("proefvideo (niet verstuurd):", OUT / "latest.mp4")
        return
    if mode == "preview":
        PREVIEWS.mkdir(exist_ok=True)
        target = PREVIEWS / f"{day.isoformat()}-{slot}u-{narrator.voice if narrator.active else 'novoice'}.mp4"
        R.render(story, target, mix_wav, th)
        shutil.copy(target, OUT / "latest.mp4")
        shutil.copy(OUT / "story.json", PREVIEWS / f"{day.isoformat()}-{slot}u-story.json")
        cleanup(day)
        print("preview:", target, f"{target.stat().st_size / 1e6:.1f} MB")
        return

    R.render(story, VIDEOS / name, mix_wav, th)
    shutil.copy(VIDEOS / name, OUT / "latest.mp4")
    print("video:", VIDEOS / name, f"{(VIDEOS / name).stat().st_size / 1e6:.1f} MB")
    (OUT / "video_name").write_text(name)

    history.append({"date": day.isoformat(), "pub": pub_day.isoformat(), "slot": slot, "angle": meta["angle"],
                    "teams": meta["teams"], "match": meta.get("match"), "title": meta["title"]})
    HISTORY.write_text(json.dumps(history[-80:], indent=2, ensure_ascii=False))
    cleanup(day)
    write_payload(name, meta, now, slot)


if __name__ == "__main__":
    main()
