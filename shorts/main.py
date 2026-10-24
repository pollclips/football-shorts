"""Dagelijkse run: data ophalen -> verhaal kiezen -> stem + video maken -> payload voor Make klaarzetten.

MODE=auto     (standaard) nieuwe video van vandaag, wordt doorgestuurd naar Make
MODE=test     stuurt de voorbeeldvideo samples/test_short.mp4 (eerste koppeltest met Make)
MODE=dry-run  maakt de video maar stuurt niets door (download onder de run, 'Artifacts')
MODE=preview  maakt de video, bewaart hem in previews/ in de repository en stuurt niets door
DAY=JJJJ-MM-DD  (enkel bij dry-run/preview) een andere dag gebruiken, bv. om te vergelijken
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


def video_url(name):
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/videos/{name}"


def write_payload(name, meta, now):
    OUT.mkdir(exist_ok=True)
    payload = {
        "video_url": video_url(name),
        "title": meta["title"],
        "description": meta["description"],
        "tags": ",".join(meta["tags"]),
        "privacy": "private",            # verplicht bij ingepland publiceren
        "publish_at": publish_time(now),  # volgende 00:00 Brussel, in UTC
        "category_id": "17",              # YouTube-categorie Sports
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


def main():
    mode = os.environ.get("MODE", "auto").strip() or "auto"
    now = datetime.now(timezone.utc)
    if os.environ.get("FAKE_NOW"):
        now = datetime.fromisoformat(os.environ["FAKE_NOW"])
    local = now.astimezone(TZ)
    OUT.mkdir(exist_ok=True)
    VIDEOS.mkdir(exist_ok=True)
    trial = mode in ("dry-run", "preview")

    # GitHub kent geen tijdzones: er staan twee geplande starts (zomer- en winteruur).
    # Enkel de start die rond 23u20 Brusselse tijd valt, gaat door.
    if os.environ.get("SCHEDULED") and not (local.hour == 23 or local.hour < 2):
        return skip(f"Geplande start om {local:%H:%M} Brusselse tijd valt buiten het venster; overslaan.")
    # een vertraagde run na middernacht hoort nog bij de vorige dag
    day = (local - timedelta(hours=3)).date() if local.hour < 3 else local.date()
    if trial and os.environ.get("DAY", "").strip():
        day = date.fromisoformat(os.environ["DAY"].strip())

    if mode == "test":
        name = f"{day.isoformat()}-test.mp4"
        shutil.copy(ROOT / "samples" / "test_short.mp4", VIDEOS / name)
        meta = {"title": "Man City: 7 from 7 🔥 Can anyone stop them? #Shorts",
                "description": "Manchester City beat Ipswich 3–2 and are 6 points clear of Arsenal. "
                               "Who wins the title?\n\n#Shorts #PremierLeague #football #soccer #ManCity",
                "tags": ["football", "soccer", "Premier League", "Man City", "Ipswich", "shorts"]}
        write_payload(name, meta, now)
        return

    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    if not trial and any(h.get("date") == day.isoformat() for h in history) and not os.environ.get("FORCE"):
        return skip("Vandaag is er al een video gemaakt; stop (zet FORCE=1 om toch opnieuw te maken).")
    recent = set() if trial else {t for h in history[-3:] for t in h.get("teams", [])}

    api = Api()
    raw = api.matches(day.isoformat(), (day + timedelta(days=1)).isoformat())
    matches = [m for m in raw
               if datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).astimezone(TZ).date() == day]
    finished = [m for m in matches if m.get("status") == "FINISHED" and m["competition"]["code"] in COMPETITIONS]
    print(f"{day}: {len(matches)} wedstrijden, {len(finished)} afgelopen")

    codes = sorted({m["competition"]["code"] for m in finished}, key=lambda c: -COMPETITIONS[c][2])[:6]
    tables = {}
    for code in codes:
        st = api.standings(code)
        ids = {m[s]["id"] for m in finished if m["competition"]["code"] == code for s in ("homeTeam", "awayTeam")}
        tables[code] = {tid: table_rows(st, tid) for tid in ids}

    rng = random.Random(day.isoformat())
    nxt_from, nxt_to = (day + timedelta(days=1)).isoformat(), (day + timedelta(days=21)).isoformat()
    cands = candidates(finished, tables, recent)
    if cands:
        best = cands[0]
        print("gekozen:", best["angle"], best["match"]["homeTeam"]["name"], "-", best["match"]["awayTeam"]["name"],
              f"(score {best['score']:.2f})")
        focus_team = best["match"]["homeTeam" if best["focus"] == "home" else "awayTeam"]["id"]
        nxt = api.next_match(focus_team, nxt_from, nxt_to)
        story, meta = build_story(best, day, nxt, finished, rng)
    else:
        print("Geen afgelopen wedstrijden vandaag -> reserveverhaal over de titelstrijd")
        table = table_rows(api.standings("PL"))
        if len(table) < 2:
            return skip("Ook geen klassement beschikbaar; vandaag geen video.")
        nxt = api.next_match(table[0]["id"], nxt_from, nxt_to)
        story, meta = build_story_fallback(table, day, nxt, rng)

    # --- clubkleuren -> thema (wisselt per video)
    fc_text = api.team_colors(meta["focus_team"])
    oc_text = api.team_colors(meta["opp_team"])
    th = theme.build(theme.team_palette(fc_text, meta["focus_name"]),
                     theme.team_palette(oc_text, meta["opp_name"]), rng)
    print(f"kleuren: {meta['focus_name']}='{fc_text}' {meta['opp_name']}='{oc_text}' -> stijl {th['style']}, "
          f"accent {th['acc']}, opening {th['hook_layout']}")

    # --- vormgeving: 'broadcast' (v3, standaard) of 'classic' (v2)
    style = (os.environ.get("STYLE", "") or "broadcast").strip()
    R = broadcast if style == "broadcast" else render

    # --- stem + ondertitels (bepaalt ook de duur van elke scène)
    narrator = voice.Narrator()
    voice_wav = OUT / "voice.wav"
    voice.narrate(story, narrator, voice_wav, R.build_timeline)
    print("stem:", narrator.describe())

    name = f"{day.isoformat()}.mp4"
    (OUT / "story.json").write_text(json.dumps({"story": story, "meta": meta, "theme": th},
                                               indent=2, ensure_ascii=False))
    music_wav, mix_wav, sfx_wav = OUT / "music.wav", OUT / "mix.wav", None
    if R is broadcast:
        _, shots, dur, cuts, impacts = broadcast.plan(story, th)
        starts = [s.t0 for s in shots]
        used = music.make_music(day.isoformat(), dur, [0.0], music_wav)   # whooshes zitten in de effecten
        sfx_wav = music.sfx(day.isoformat(), dur, impacts, cuts, OUT / "sfx.wav")
    else:
        starts, dur = render.scene_starts(story)
        used = music.make_music(day.isoformat(), dur, starts, music_wav)
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
        target = PREVIEWS / f"{day.isoformat()}-{narrator.voice if narrator.active else 'novoice'}.mp4"
        R.render(story, target, mix_wav, th)
        shutil.copy(target, OUT / "latest.mp4")
        shutil.copy(OUT / "story.json", PREVIEWS / f"{day.isoformat()}-story.json")
        cleanup(day)
        print("preview:", target, f"{target.stat().st_size / 1e6:.1f} MB")
        return

    R.render(story, VIDEOS / name, mix_wav, th)
    shutil.copy(VIDEOS / name, OUT / "latest.mp4")
    print("video:", VIDEOS / name, f"{(VIDEOS / name).stat().st_size / 1e6:.1f} MB")

    history.append({"date": day.isoformat(), "angle": meta["angle"], "teams": meta["teams"],
                    "title": meta["title"]})
    HISTORY.write_text(json.dumps(history[-60:], indent=2, ensure_ascii=False))
    cleanup(day)
    write_payload(name, meta, now)


def build_story_fallback(table, day, nxt, rng):
    return build_table_story("PL", table, day, nxt, rng)


if __name__ == "__main__":
    main()
