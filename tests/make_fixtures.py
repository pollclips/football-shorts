"""Bootst football-data.org-antwoorden na met de Premier League-data van 17/10/2026 (enkel om lokaal te testen)."""
import json, sys
from pathlib import Path

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
T = {65: "Man City", 349: "Ipswich Town", 64: "Liverpool", 402: "Brentford", 62: "Everton", 61: "Chelsea",
     63: "Fulham", 322: "Hull City", 67: "Newcastle", 58: "Aston Villa", 57: "Arsenal", 397: "Brighton Hove",
     341: "Leeds United", 354: "Crystal Palace", 66: "Man United", 1076: "Coventry City", 351: "Nottingham",
     71: "Sunderland", 1044: "Bournemouth", 73: "Tottenham"}
def team(i): return {"id": i, "name": T[i] + " FC", "shortName": T[i], "tla": T[i][:3].upper()}
def match(h, a, ft, ht, utc):
    return {"id": h * 1000 + a, "utcDate": utc, "status": "FINISHED", "matchday": 8,
            "competition": {"id": 2021, "name": "Premier League", "code": "PL"},
            "homeTeam": team(h), "awayTeam": team(a),
            "score": {"winner": None, "fullTime": {"home": ft[0], "away": ft[1]},
                      "halfTime": {"home": ht[0], "away": ht[1]}}}
ms = [match(62, 61, (0, 2), (0, 1), "2026-10-17T11:30:00Z"), match(402, 64, (1, 2), (1, 0), "2026-10-17T14:00:00Z"),
      match(63, 322, (1, 0), (0, 0), "2026-10-17T14:00:00Z"), match(65, 349, (3, 2), (2, 1), "2026-10-17T14:00:00Z"),
      match(67, 58, (0, 1), (0, 0), "2026-10-17T16:30:00Z")]
(out / "matches.json").write_text(json.dumps({"matches": ms}))
rows = [(65, 7, 7, 0, 0, 21, 19, 6), (57, 6, 5, 0, 1, 15, 13, 4), (397, 6, 4, 1, 1, 13, 11, 6), (61, 7, 4, 1, 2, 13, 12, 8),
        (64, 7, 3, 3, 1, 12, 11, 9), (402, 7, 2, 4, 1, 10, 9, 8), (62, 7, 2, 4, 1, 10, 8, 8), (341, 6, 2, 3, 1, 9, 8, 7),
        (322, 7, 2, 3, 2, 9, 10, 11), (349, 7, 3, 0, 4, 9, 9, 12), (67, 7, 2, 2, 3, 8, 7, 9), (58, 7, 2, 2, 3, 8, 6, 8),
        (354, 6, 2, 1, 3, 7, 8, 9), (66, 6, 1, 3, 2, 6, 7, 9), (1076, 6, 2, 0, 4, 6, 9, 13), (63, 7, 1, 2, 4, 5, 5, 10),
        (351, 6, 1, 2, 3, 5, 6, 10), (71, 6, 1, 1, 4, 4, 5, 11), (1044, 6, 0, 3, 3, 3, 4, 9), (73, 6, 0, 3, 3, 3, 5, 10)]
table = [{"position": i + 1, "team": team(r[0]), "playedGames": r[1], "won": r[2], "draw": r[3], "lost": r[4],
          "points": r[5], "goalsFor": r[6], "goalsAgainst": r[7], "goalDifference": r[6] - r[7]} for i, r in enumerate(rows)]
(out / "standings_PL.json").write_text(json.dumps({"standings": [{"stage": "REGULAR_SEASON", "type": "TOTAL", "table": table}]}))
nxt = {"id": 1, "utcDate": "2026-10-24T11:30:00Z", "status": "TIMED", "homeTeam": team(58), "awayTeam": team(65),
       "competition": {"code": "PL"}, "score": {"fullTime": {"home": None, "away": None}}}
(out / "next_65.json").write_text(json.dumps({"matches": [nxt]}))
print("fixtures in", out)
