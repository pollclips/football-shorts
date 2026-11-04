"""Testdata (verzonnen uitslagen!) in het formaat van football-data.org, om alle formaten lokaal te testen.

python tests/make_fixtures_v2.py <map>
FIXTURES_DIR=<map> FAKE_NOW=2026-11-04T11:25:00+00:00 python -m shorts.main --frames   # voorbeschouwing
FIXTURES_DIR=<map> FAKE_NOW=2026-11-04T22:20:00+00:00 python -m shorts.main --frames   # verslag (avond)
FIXTURES_DIR=<map> FAKE_NOW=2026-11-09T11:25:00+00:00 python -m shorts.main --frames   # maandag: quiz
"""
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
T = {64: "Liverpool", 86: "Real Madrid", 5: "Bayern", 851: "Club Brugge", 610: "Galatasaray", 678: "Ajax",
     102: "Atalanta", 930: "Slavia Praha", 524: "PSG", 65: "Man City", 57: "Arsenal", 61: "Chelsea",
     66: "Man United", 73: "Tottenham", 81: "Barça", 78: "Atleti", 109: "Juventus", 108: "Inter", 98: "Milan",
     113: "Napoli", 4: "Dortmund", 3: "Leverkusen", 516: "Marseille", 67: "Newcastle", 58: "Aston Villa",
     397: "Brighton Hove", 263: "Alavés", 94: "Villarreal", 99: "Fiorentina", 11: "Wolfsburg", 521: "Lille"}
CL = {"id": 2001, "name": "UEFA Champions League", "code": "CL"}


def team(i):
    return {"id": i, "name": T[i] + " FC", "shortName": T[i], "tla": T[i][:3].upper()}


def match(mid, h, a, utc, status="TIMED", ft=(None, None), ht=(None, None), comp=CL):
    return {"id": mid, "utcDate": utc, "status": status, "competition": comp,
            "homeTeam": team(h), "awayTeam": team(a),
            "score": {"fullTime": {"home": ft[0], "away": ft[1]}, "halfTime": {"home": ht[0], "away": ht[1]}}}


def row(pos, tid, p, w, d, l, gf, ga):
    return {"position": pos, "team": team(tid), "playedGames": p, "won": w, "draw": d, "lost": l,
            "points": 3 * w + d, "goalsFor": gf, "goalsAgainst": ga, "goalDifference": gf - ga}


def standings(rows):
    return {"standings": [{"stage": "REGULAR_SEASON", "type": "TOTAL", "table": rows}]}


def write(name, obj):
    (out / name).write_text(json.dumps(obj))


# woensdag 4 november: Champions League (voorbeschouwing om 13:00, verslag om 23:00)
day = "2026-11-04"
timed = [match(1, 64, 86, f"{day}T20:00:00Z"), match(2, 5, 851, f"{day}T20:00:00Z"),
         match(3, 610, 678, f"{day}T17:45:00Z"), match(4, 102, 930, f"{day}T17:45:00Z")]
finished = [match(1, 64, 86, f"{day}T20:00:00Z", "FINISHED", (2, 3), (2, 1)),
            match(2, 5, 851, f"{day}T20:00:00Z", "FINISHED", (1, 2), (0, 1)),
            match(3, 610, 678, f"{day}T17:45:00Z", "FINISHED", (1, 1), (0, 1)),
            match(4, 102, 930, f"{day}T17:45:00Z", "FINISHED", (3, 0), (1, 0))]
write("matches_timed.json", {"matches": timed})
write("matches_finished.json", {"matches": finished})
write("standings_CL.json", standings([row(1, 524, 4, 4, 0, 0, 12, 3), row(2, 86, 4, 3, 1, 0, 10, 4),
                                      row(3, 5, 4, 3, 0, 1, 11, 5), row(4, 64, 4, 3, 0, 1, 9, 5),
                                      row(5, 65, 4, 2, 2, 0, 8, 3), row(6, 57, 4, 2, 1, 1, 7, 4),
                                      row(9, 851, 4, 2, 0, 2, 6, 6), row(14, 610, 4, 1, 2, 1, 5, 6),
                                      row(20, 678, 4, 1, 1, 2, 4, 7), row(22, 102, 4, 1, 1, 2, 4, 6),
                                      row(33, 930, 4, 0, 1, 3, 2, 10)]))
write("form_64.json", {"matches": [match(10 + k, 64, 61, f"2026-10-{12 + 4 * k:02d}T15:00:00Z", "FINISHED", s, (0, 0),
                                         {"code": "PL"}) for k, s in enumerate([(2, 0), (1, 1), (3, 1), (0, 1), (2, 1)])]})
write("form_86.json", {"matches": [match(20 + k, 86, 81, f"2026-10-{12 + 4 * k:02d}T19:00:00Z", "FINISHED", s, (0, 0),
                                         {"code": "PD"}) for k, s in enumerate([(3, 0), (2, 2), (1, 0), (4, 1), (2, 0)])]})
for tid, col in ((64, "Red / White"), (86, "White / Purple"), (5, "Red / White"), (851, "Blue / Black"),
                 (524, "Navy Blue / Red"), (65, "Sky Blue / White"), (108, "Blue / Black"), (109, "Black / White")):
    write(f"team_{tid}.json", {"clubColors": col})

# klassementen top-5 (voor quiz en reserve)
write("standings_PL.json", standings([row(1, 57, 10, 8, 1, 1, 22, 6), row(2, 65, 10, 7, 2, 1, 24, 9),
                                      row(3, 64, 10, 7, 1, 2, 20, 10), row(4, 61, 10, 6, 2, 2, 19, 11),
                                      row(5, 67, 10, 5, 3, 2, 15, 9), row(6, 58, 10, 5, 2, 3, 14, 12),
                                      row(9, 73, 10, 4, 2, 4, 16, 15), row(12, 66, 10, 3, 3, 4, 12, 14),
                                      row(7, 397, 10, 5, 1, 4, 15, 14)]))
write("standings_PD.json", standings([row(1, 86, 11, 9, 1, 1, 27, 8), row(2, 81, 11, 8, 1, 2, 31, 12),
                                      row(3, 78, 11, 7, 2, 2, 18, 9), row(4, 94, 11, 6, 2, 3, 17, 13),
                                      row(18, 263, 11, 2, 3, 6, 9, 19)]))
write("standings_BL1.json", standings([row(1, 5, 9, 8, 1, 0, 30, 7), row(2, 4, 9, 6, 2, 1, 19, 10),
                                       row(3, 3, 9, 5, 3, 1, 18, 11), row(14, 11, 9, 2, 2, 5, 10, 17)]))
write("standings_SA.json", standings([row(1, 113, 10, 7, 2, 1, 18, 7), row(2, 108, 10, 7, 1, 2, 23, 10),
                                      row(3, 98, 10, 6, 2, 2, 16, 9), row(4, 109, 10, 5, 4, 1, 14, 6),
                                      row(8, 99, 10, 4, 3, 3, 14, 13)]))
write("standings_FL1.json", standings([row(1, 524, 11, 8, 2, 1, 26, 9), row(2, 516, 11, 7, 1, 3, 21, 14),
                                       row(3, 521, 11, 6, 3, 2, 17, 11)]))
print("testdata in", out)
