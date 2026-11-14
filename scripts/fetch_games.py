"""Download a player's games from the public chess.com API (no login needed).

usage: python fetch_games.py USERNAME --dir OUT [--months N] [--last-only]

Writes OUT/games.pgn (standard chess only, oldest first) and OUT/last.pgn (the most recent game).
--months N limits the download to the last N monthly archives (default: all).
--last-only fetches just the newest archive and writes only last.pgn (for a single-game analysis).
"""
import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

UA = {"User-Agent": "chess-com-report-skill/1.0"}


def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                sys.exit(f"chess.com user not found: {url}")
            if e.code == 429 and attempt < 3:
                time.sleep(2 + attempt * 3)
                continue
            raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--months", type=int, default=0)
    ap.add_argument("--last-only", action="store_true")
    a = ap.parse_args()
    user = a.username.strip().lower()
    out = pathlib.Path(a.dir)
    out.mkdir(parents=True, exist_ok=True)

    archives = get(f"https://api.chess.com/pub/player/{user}/games/archives")["archives"]
    if not archives:
        sys.exit("No games found for this user.")
    if a.last_only:
        archives = archives[-2:]  # the newest month may be empty right after the 1st
    elif a.months:
        archives = archives[-a.months:]

    games = []
    for url in archives:
        for g in get(url).get("games", []):
            if g.get("rules") == "chess" and g.get("pgn"):
                games.append(g)
        time.sleep(0.3)
    if not games:
        sys.exit("No standard chess games found.")
    games.sort(key=lambda g: g["end_time"])

    (out / "last.pgn").write_text(games[-1]["pgn"].strip() + "\n", encoding="utf-8")
    if not a.last_only:
        (out / "games.pgn").write_text("\n\n".join(g["pgn"].strip() for g in games) + "\n", encoding="utf-8")
        tc = {}
        for g in games:
            tc[g.get("time_class", "?")] = tc.get(g.get("time_class", "?"), 0) + 1
        print(f"{len(games)} games saved to {out / 'games.pgn'}; by time class: {tc}")
    last = games[-1]
    print(f"Last game: {last['white']['username']} vs {last['black']['username']} {last['url']}")


if __name__ == "__main__":
    main()
