"""Compare the player's openings with the lichess opening explorer (millions of games of players of a similar rating).

  python explorer.py USERNAME --dir OUT [--ratings 1000,1200] [--speeds rapid] [--max-ply 24] [--min-games 50]

Reads OUT/games.pgn and OUT/games.json, writes OUT/explorer.json. Every position is asked once and kept in
OUT/explorer/cache.json, so a later run only asks the positions of new games. The lichess API needs no account;
only board positions are sent (no user name). Requests go one at a time, and after "429 Too Many Requests" the
script waits a full minute, as lichess asks.

For each game it follows the moves from the start while the position and the move played still have at least
--min-games games in the database ("known theory" at that level). The first move below that is where the game
left theory, and the script notes who left it. For every position where the player was to move it keeps the
database numbers for each move: how often it is played and how it scores for the side that plays it.

explorer.json:
  params      ratings, speeds, max_ply, min_games, positions asked
  exits       one row per game: n, colour, exit ply, who left theory ("me", "opp" or "none"), outcome
  exit_stats  per colour: average move where theory ends, share left by you / by the opponent, score in each case
  decisions   positions where the player was to move at least 3 times: line, your moves with your results, and
              the database numbers (games, share, score) of your main move, the most played move and the best-scoring
              move (only moves with at least 5% share and --min-games games count as best)
  weak        decisions where your main move scores at least 4 points below the best-scoring move, largest loss first
  novelties   your own moves that left theory at least twice: line, move, games, your score
"""
import argparse
import collections
import io
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import chess
import chess.pgn

API = "https://explorer.lichess.ovh/lichess"
UA = {"User-Agent": "chess-report-skill"}
# lichess asks for a personal API token (no scopes needed): LICHESS_TOKEN, or the git-ignored file lichess_token.txt in
# the skill folder. Create one at https://lichess.org/account/oauth/token/create
TOKEN_FILE = pathlib.Path(__file__).resolve().parent.parent / "lichess_token.txt"


def lichess_token():
    tok = os.environ.get("LICHESS_TOKEN", "").strip()
    if not tok and TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
    return tok


if lichess_token():
    UA["Authorization"] = "Bearer " + lichess_token()
BANDS = [0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500]
SPEED = {"bullet": "bullet", "blitz": "blitz", "rapid": "rapid", "daily": "correspondence"}


def default_ratings(rating):
    """Two lichess rating bands around a chess.com rating (lichess runs roughly 400 points higher at club level)."""
    target = (rating or 1000) + 400
    i = max(k for k, b in enumerate(BANDS) if b <= target)
    i = min(i, len(BANDS) - 2)
    return ",".join(str(b) for b in BANDS[i:i + 2] if b)  # band 0 is not a valid filter on its own


class Explorer:
    def __init__(self, cache_path, ratings, speeds):
        self.path, self.ratings, self.speeds = cache_path, ratings, speeds
        self.cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        self.asked = 0

    def key(self, board):
        return f"{self.ratings}|{self.speeds}|{' '.join(board.fen().split()[:4])}"

    def get(self, board):
        k = self.key(board)
        if k in self.cache:
            return self.cache[k]
        q = urllib.parse.urlencode({"variant": "standard", "fen": board.fen(), "speeds": self.speeds, "ratings": self.ratings,
                                    "moves": 15, "topGames": 0, "recentGames": 0})
        for attempt in range(6):
            try:
                with urllib.request.urlopen(urllib.request.Request(f"{API}?{q}", headers=UA), timeout=30) as r:
                    data = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise RuntimeError("lichess refused the request (401): put a lichess API token in " + str(TOKEN_FILE) +
                             " or in LICHESS_TOKEN (create one at https://lichess.org/account/oauth/token/create, no scopes needed)")
                if e.code == 429:
                    print("  lichess asks to slow down; waiting 60 s", flush=True)
                    time.sleep(60)
                    continue
                if attempt == 5:
                    raise
                time.sleep(3)
            except (urllib.error.URLError, TimeoutError):
                if attempt == 5:
                    raise
                time.sleep(5)
        rec = {"w": data["white"], "d": data["draws"], "b": data["black"],
               "moves": [[m["san"], m["white"], m["draws"], m["black"]] for m in data["moves"]]}
        self.cache[k] = rec
        self.asked += 1
        if self.asked % 50 == 0:
            self.save()
            print(f"  {self.asked} positions asked", flush=True)
        time.sleep(0.15)
        return rec

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, self.path)


def score_for(w, d, b, white):
    n = w + d + b
    return round(100 * ((w if white else b) + d / 2) / n, 1) if n else None


def move_stats(rec, white):
    """{san: (games, share %, score % for the mover)} for one position."""
    tot = rec["w"] + rec["d"] + rec["b"]
    return {s: (w + d + b, round(100 * (w + d + b) / tot, 1) if tot else 0, score_for(w, d, b, white)) for s, w, d, b in rec["moves"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--ratings", help="lichess rating bands, e.g. 1000,1200 (default: from your current rating)")
    ap.add_argument("--speeds", help="lichess speeds, e.g. rapid or blitz,rapid (default: your main time classes)")
    ap.add_argument("--max-ply", type=int, default=24, help="follow theory up to this many half-moves (default 24 = move 12)")
    ap.add_argument("--min-games", type=int, default=50, help="a move counts as theory with at least this many games")
    a = ap.parse_args()
    me, out = a.username.strip().lower(), pathlib.Path(a.dir)
    rows = json.loads((out / "games.json").read_text(encoding="utf-8"))
    by_link = {r["link"]: r for r in rows}

    tc = collections.Counter(r["time_class"] for r in rows)
    speeds = a.speeds or ",".join(sorted({SPEED[k] for k, v in tc.items() if k in SPEED and v >= 0.1 * len(rows)}) or {"rapid"})
    main_tc = tc.most_common(1)[0][0]
    cur = next((r["my_elo"] for r in reversed(rows) if r["time_class"] == main_tc), None)
    ratings = a.ratings or default_ratings(cur)
    ex = Explorer(out / "explorer" / "cache.json", ratings, speeds)
    print(f"lichess explorer: ratings {ratings}, speeds {speeds}, theory = at least {a.min_games} games, up to ply {a.max_ply}", flush=True)

    exits, dec = [], collections.defaultdict(lambda: {"count": 0, "line": None, "mine": collections.Counter(), "res": collections.defaultdict(list), "db": None, "white": None})
    nov = collections.defaultdict(list)
    pgn = io.StringIO((out / "games.pgn").read_text(encoding="utf-8"))
    try:
        while True:
            g = chess.pgn.read_game(pgn)
            if g is None:
                break
            r = by_link.get(g.headers.get("Link", ""))
            if not r or r["time_class"] not in SPEED:
                continue
            white = r["color"] == "white"
            pts = {"win": 1, "draw": .5, "loss": 0}[r["outcome"]]
            b, line, exit_ply, who = g.board(), [], None, "none"
            for ply, mv in enumerate(g.mainline_moves()):
                if ply >= a.max_ply:
                    break
                rec = ex.get(b)
                if rec["w"] + rec["d"] + rec["b"] < a.min_games:  # the position itself is already rare
                    exit_ply, who = ply, ("opp" if (b.turn == chess.WHITE) == white else "me")
                    break
                san = b.san(mv)
                mover_is_me = (b.turn == chess.WHITE) == white
                st = move_stats(rec, b.turn == chess.WHITE)
                if mover_is_me:
                    k = " ".join(b.fen().split()[:4])
                    d = dec[k]
                    d["count"] += 1
                    d["line"] = d["line"] or list(line)
                    d["mine"][san] += 1
                    d["res"][san].append(pts)
                    d["db"], d["white"] = st, b.turn == chess.WHITE
                if st.get(san, (0,))[0] < a.min_games:
                    exit_ply, who = ply, ("me" if mover_is_me else "opp")
                    if mover_is_me:
                        nov[(" ".join(line), san, white)].append(pts)
                    break
                line.append(san)
                b.push(mv)
            exits.append({"n": r["n"], "color": r["color"], "ply": exit_ply, "who": who, "outcome": r["outcome"]})
    finally:
        ex.save()

    def sc(p):
        return round(100 * sum(p) / len(p)) if p else None

    exit_stats = {}
    for col in ("white", "black"):
        es = [e for e in exits if e["color"] == col]
        if not es:
            continue
        pts = lambda sel: [{"win": 1, "draw": .5, "loss": 0}[e["outcome"]] for e in sel]
        known = [e["ply"] for e in es if e["ply"] is not None]
        exit_stats[col] = {
            "games": len(es),
            "avg_exit_move": round(sum(p // 2 + 1 for p in known) / len(known), 1) if known else None,
            "me": len([e for e in es if e["who"] == "me"]), "opp": len([e for e in es if e["who"] == "opp"]),
            "none": len([e for e in es if e["who"] == "none"]),
            "score_me": sc(pts([e for e in es if e["who"] == "me"])), "score_opp": sc(pts([e for e in es if e["who"] == "opp"])),
            "score_none": sc(pts([e for e in es if e["who"] == "none"])),
        }

    decisions = []
    for k, d in dec.items():
        if d["count"] < 3 or not d["db"]:
            continue
        db = d["db"]
        main_mv = d["mine"].most_common(1)[0][0]
        popular = max(db, key=lambda s: db[s][0]) if db else None
        cands = {s: v for s, v in db.items() if v[1] >= 5 and v[0] >= a.min_games}
        best = max(cands, key=lambda s: cands[s][2]) if cands else popular
        decisions.append({
            "fen": k, "line": d["line"], "ply": len(d["line"]), "white": d["white"], "count": d["count"],
            "mine": [{"san": s, "times": c, "score": sc(d["res"][s]), "db": db.get(s)} for s, c in d["mine"].most_common()],
            "main": main_mv, "popular": popular, "popular_db": db.get(popular), "best": best, "best_db": db.get(best),
        })
    decisions.sort(key=lambda x: (-x["count"], x["ply"]))
    weak = []
    for x in decisions:
        m = x["mine"][0]
        if m["db"] and x["best"] != x["main"] and x["best_db"] and x["best_db"][2] - m["db"][2] >= 4:
            weak.append(dict(x, gap=round(x["best_db"][2] - m["db"][2], 1)))
    weak.sort(key=lambda x: -(x["gap"] * x["mine"][0]["times"]))
    # what your move and the better one do, checked with Stockfish (no engine: board facts only)
    import move_ideas
    eng = move_ideas.open_engine()
    try:
        for w in weak[:6]:
            b = chess.Board()
            for s in w["line"]:
                b.push_san(s)
            w["ideas"] = move_ideas.ideas(b, [w["mine"][0]["san"], w["best"]], eng)
    finally:
        if eng:
            eng.quit()
    novelties = sorted(({"line": k[0].split(), "san": k[1], "white": k[2], "games": len(v), "score": sc(v)} for k, v in nov.items() if len(v) >= 2),
                       key=lambda x: -x["games"])

    res = {"params": {"ratings": ratings, "speeds": speeds, "max_ply": a.max_ply, "min_games": a.min_games,
                      "positions": len([k for k in ex.cache if k.startswith(f"{ratings}|{speeds}|")]), "asked_now": ex.asked},
           "exits": exits, "exit_stats": exit_stats, "decisions": decisions, "weak": weak, "novelties": novelties}
    (out / "explorer.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"explorer.json: {len(exits)} games, {len(decisions)} repeated positions, {len(weak)} weaker choices, "
          f"{len(novelties)} repeated departures; {ex.asked} new positions asked", flush=True)
    for col, s in exit_stats.items():
        print(f"  {col}: theory ends on move {s['avg_exit_move']} on average; left by you {s['me']} ({s['score_me']}%), "
              f"by the opponent {s['opp']} ({s['score_opp']}%), still in theory {s['none']} ({s['score_none']}%)")
    for w in weak[:8]:
        m = w["mine"][0]
        print(f"  after {' '.join(w['line']) or 'start'}: you {m['san']} x{m['times']} (db {m['db'][2]}%, yours {m['score']}%) "
              f"-> {w['best']} db {w['best_db'][2]}% ({w['best_db'][1]}% share)")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:  # e.g. no lichess token
        sys.exit(str(e))
