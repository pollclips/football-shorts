"""Gratis voetbaldata via football-data.org (v4).

Gratis plan: 12 competities, 10 verzoeken per minuut, uitslagen met wat vertraging.
Sleutel komt uit de omgevingsvariabele FOOTBALL_DATA_API_KEY.
Voor lokale tests: FIXTURES_DIR=map met matches.json, standings_<CODE>.json, next_<teamid>.json.
"""
import json
import os
import time
from pathlib import Path

import requests

BASE = "https://api.football-data.org/v4"
COMPETITIONS = {
    "PL": ("Premier League", "#PremierLeague", 1.00),
    "CL": ("Champions League", "#ChampionsLeague", 1.00),
    "WC": ("World Cup", "#WorldCup", 1.00),
    "EC": ("EURO", "#EURO", 1.00),
    "PD": ("LaLiga", "#LaLiga", 0.85),
    "BL1": ("Bundesliga", "#Bundesliga", 0.75),
    "SA": ("Serie A", "#SerieA", 0.75),
    "FL1": ("Ligue 1", "#Ligue1", 0.60),
    "PPL": ("Primeira Liga", "#PrimeiraLiga", 0.50),
    "DED": ("Eredivisie", "#Eredivisie", 0.50),
    "ELC": ("Championship", "#EFLChampionship", 0.40),
    "BSA": ("Brasileirão", "#Brasileirao", 0.40),
}

# nettere namen dan de standaard shortName van de API
NAME_FIX = {
    "Brighton Hove": "Brighton",
    "Wolverhampton": "Wolves",
    "Nottingham": "Nott'm Forest",
    "Man United": "Man United",
    "Atleti": "Atlético",
    "Barça": "Barcelona",
    "M'gladbach": "Gladbach",
    "Sl. Bratislava": "Slovan Bratislava",
}


class Api:
    def __init__(self):
        self.key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
        self.fixtures = os.environ.get("FIXTURES_DIR")
        self._last = 0.0

    def get(self, path, params=None, fixture=None):
        if self.fixtures:
            p = Path(self.fixtures) / fixture
            return json.loads(p.read_text()) if p.exists() else None
        if not self.key:
            raise SystemExit("FOOTBALL_DATA_API_KEY ontbreekt (zet hem als GitHub secret).")
        for attempt in range(3):
            wait = 6.5 - (time.time() - self._last)        # max 10 verzoeken/minuut
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            r = requests.get(BASE + path, params=params, headers={"X-Auth-Token": self.key}, timeout=30)
            if r.status_code == 429:
                time.sleep(61)
                continue
            if r.status_code in (400, 401):
                raise SystemExit(f"football-data.org weigert de sleutel ({r.status_code}): {r.text[:200]}")
            if r.status_code == 403:
                return None                                    # buiten het gratis plan
            r.raise_for_status()
            return r.json()
        return None

    def matches(self, date_from, date_to):
        js = self.get("/matches", {"dateFrom": date_from, "dateTo": date_to}, "matches.json")
        return (js or {}).get("matches", [])

    def standings(self, code):
        js = self.get(f"/competitions/{code}/standings", None, f"standings_{code}.json")
        return (js or {}).get("standings", [])

    def team_colors(self, team_id):
        """Clubkleuren als tekst, bv. "Sky Blue / White" (leeg als onbekend)."""
        try:
            js = self.get(f"/teams/{team_id}", None, f"team_{team_id}.json")
        except requests.RequestException:
            return ""
        return (js or {}).get("clubColors") or ""

    def next_match(self, team_id, date_from, date_to):
        try:
            js = self.get(f"/teams/{team_id}/matches", {"dateFrom": date_from, "dateTo": date_to},
                          f"next_{team_id}.json")
        except requests.RequestException:
            return None
        ms = [m for m in (js or {}).get("matches", []) if m.get("status") in ("SCHEDULED", "TIMED")]
        ms.sort(key=lambda m: m["utcDate"])
        return ms[0] if ms else None


def team_name(t):
    n = t.get("shortName") or t.get("name") or "?"
    n = NAME_FIX.get(n, n)
    for suf in (" FC", " AFC", " CF"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n


def table_rows(standings, team_id=None):
    """Geeft de tabel (lijst rijen) die het team bevat; anders de eerste TOTAL-tabel."""
    totals = [s for s in standings if s.get("type", "TOTAL") == "TOTAL"] or standings
    chosen = None
    for s in totals:
        if team_id is None or any(r["team"]["id"] == team_id for r in s.get("table", [])):
            chosen = s
            break
    if chosen is None and totals:
        chosen = totals[0]
    rows = []
    for r in (chosen or {}).get("table", []):
        rows.append({
            "id": r["team"]["id"], "name": team_name(r["team"]), "pos": r["position"],
            "played": r["playedGames"], "won": r["won"], "draw": r["draw"], "lost": r["lost"],
            "pts": r["points"], "gf": r["goalsFor"], "ga": r["goalsAgainst"],
        })
    return rows
