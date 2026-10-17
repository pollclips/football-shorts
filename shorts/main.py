"""Dagelijkse run: data ophalen -> verhaal kiezen -> video maken -> payload voor Make klaarzetten.

MODE=auto     (standaard) nieuwe video van vandaag
MODE=test     stuurt de voorbeeldvideo samples/test_short.mp4 (eerste koppeltest met Make)
MODE=dry-run  maakt de video maar stuurt niets door (de workflow slaat het verzenden over)
"""
import json
import os
import random
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import music, render
from .data import COMPETITIONS, Api, table_rows
from .story import TZ, build_story, build_table_story, candidates, publish_time

ROOT = Path(__file__).resolve().parent.parent
VIDEOS = ROOT / "videos"
OUT = ROOT / "out"
HISTORY = ROOT / "history.json"
KEEP_DAYS = 14


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


def main():
    mode = os.environ.get("MODE", "auto").strip() or "auto"
    now = datetime.now(timezone.utc)
    if os.environ.get("FAKE_NOW"):
        now = datetime.fromisoformat(os.environ["FAKE_NOW"])
    local = now.astimezone(TZ)
    OUT.mkdir(exist_ok=True)
    VIDEOS.mkdir(exist_ok=True)

    # GitHub kent geen tijdzones: er staan twee geplande starts (zomer- en winteruur).
    # Enkel de start die rond 23u20 Brusselse tijd valt, gaat door.
    if os.environ.get("SCHEDULED") and not (local.hour == 23 or local.hour < 2):
        print(f"Geplande start om {local:%H:%M} Brusselse tijd valt buiten het venster; overslaan.")
        (OUT / "skip").write_text("1")
        return
    # een vertraagde run na middernacht hoort nog bij de vorige dag
    day = (local - timedelta(hours=3)).date() if local.hour < 3 else local.date()

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
    if any(h.get("date") == day.isoformat() for h in history) and not os.environ.get("FORCE"):
        print("Vandaag is er al een video gemaakt; stop (zet FORCE=1 om toch opnieuw te maken).")
        Path(OUT).mkdir(exist_ok=True)
        (OUT / "skip").write_text("1")
        return
    recent = {t for h in history[-3:] for t in h.get("teams", [])}

    api = Api()
    raw = api.matches(day.isoformat(), (day + timedelta(days=1)).isoformat())
    matches = [m for m in raw
               if datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).astimezone(TZ).date() == day]
    finished = [m for m in matches if m.get("status") == "FINISHED" and m["competition"]["code"] in COMPETITIONS]
    print(f"{len(matches)} wedstrijden vandaag, {len(finished)} afgelopen")

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
            print("Ook geen klassement beschikbaar; vandaag geen video.")
            OUT.mkdir(exist_ok=True)
            (OUT / "skip").write_text("1")
            return
        nxt = api.next_match(table[0]["id"], nxt_from, nxt_to)
        story, meta = build_table_story("PL", table, day, nxt, rng)

    name = f"{day.isoformat()}.mp4"
    OUT.mkdir(exist_ok=True)
    (OUT / "story.json").write_text(json.dumps({"story": story, "meta": meta}, indent=2, ensure_ascii=False))
    starts, dur = render.scene_starts(story)
    wav = OUT / "music.wav"
    used = music.make_music(day.isoformat(), dur, starts, wav)
    print("muziek:", used)
    if "--frames" in sys.argv:
        print(render.render(story, str(OUT / "preview"), wav, frames_at=[s + 2.2 for s in starts]))
        return
    if mode == "dry-run":
        render.render(story, OUT / "latest.mp4", wav)
        print("proefvideo (niet verstuurd):", OUT / "latest.mp4")
        return
    render.render(story, VIDEOS / name, wav)
    shutil.copy(VIDEOS / name, OUT / "latest.mp4")
    print("video:", VIDEOS / name, f"{(VIDEOS / name).stat().st_size / 1e6:.1f} MB")

    history.append({"date": day.isoformat(), "angle": meta["angle"], "teams": meta["teams"],
                    "title": meta["title"]})
    HISTORY.write_text(json.dumps(history[-60:], indent=2, ensure_ascii=False))
    cleanup(day)
    write_payload(name, meta, now)


if __name__ == "__main__":
    main()
