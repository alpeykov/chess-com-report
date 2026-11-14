"""Stockfish scan of the whole history (incremental) or of one game, plus the derived statistics.

History:  python sf_scan.py USERNAME --dir OUT [--seconds 0.05] [--jobs N] [--full] [--stockfish PATH]
  needs OUT/games.json and OUT/games.pgn (fetch_games.py + stats.py). Evaluations are cached per game in OUT/sf/,
  so later runs analyse only new games. Writes:
    OUT/sf_games.json    one row per game: accuracy, move classes, phases, clock, opening exit, win % per ply
    OUT/sf_moves.json    the player's mistakes, blunders and missed mates with best line, motifs, lichess link
    OUT/sf_summary.json  totals for the report (accuracy trend, phases, clock, motifs, openings, puzzles)
One game: python sf_scan.py USERNAME --dir OUT --pgn OUT/last.pgn [--seconds 0.3]
    OUT/sf_last.json     every move of both sides with win % before/after, class, best move, line, motifs, clock

Speed (16 cores, 0.05 s per position): about 1 s per game per process, so ~400 games take 1-2 minutes;
a single game at 0.3 s per position takes ~20 s.
"""
import argparse
import collections
import hashlib
import io
import json
import multiprocessing
import os
import pathlib
import sys
import chess
import chess.pgn
import sf_engine as S

_ENG = None


def _init(path):
    global _ENG
    _ENG = S.open_engine(path, threads=1, hash_mb=16)


def _job(args):
    key, pgn_text, seconds = args
    g = chess.pgn.read_game(io.StringIO(pgn_text))
    return key, S.analyse_positions(_ENG, g, seconds=seconds)


def gid(link, pgn_text):
    return link.rstrip("/").rsplit("/", 1)[-1] if link else hashlib.md5(pgn_text.encode()).hexdigest()[:12]


def game_row(r, g, recs, evals, me):
    mine = [x for x in recs if x["mine"]]
    color = chess.WHITE if r["color"] == "white" else chess.BLACK
    wp_me = [e["wp"] if color == chess.WHITE else round(100 - e["wp"], 1) for e in evals]
    base, inc = S.base_seconds(g)
    clk_mine = [x["clock"] for x in mine if x["clock"] is not None]
    trouble = bool(base and clk_mine and min(clk_mine) < max(30, base * 0.1))
    first_err = next((x["move_no"] for x in mine if x["class"] in ("mistake", "blunder")), None)
    return {
        "n": r["n"], "link": r["link"], "date": r["date"], "color": r["color"], "outcome": r["outcome"], "opp": r["opp"],
        "opening": r.get("opening", ""), "first": r.get("first", [])[:4],
        "acc": S.game_accuracy(recs, True), "acc_opp": S.game_accuracy(recs, False),
        "classes": dict(collections.Counter(x["class"] for x in mine if x["class"])),
        "opp_classes": dict(collections.Counter(x["class"] for x in recs if not x["mine"] and x["class"])),
        "phase_moves": dict(collections.Counter(x["phase"] for x in mine)),
        "phase_errors": dict(collections.Counter(x["phase"] for x in mine if x["class"] in ("mistake", "blunder"))),
        "first_error_move": first_err,
        "exit_wp": wp_me[min(20, len(wp_me) - 1)] if len(wp_me) > 1 else None,
        "base": base, "inc": inc, "time_trouble": trouble,
        "avg_spent": round(sum(x["spent"] for x in mine if x["spent"] is not None) / max(1, sum(1 for x in mine if x["spent"] is not None)), 1),
        "wp": wp_me,
    }


def summarize(rows, moves):
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 1) if xs else None
    n = len(rows)
    q = [rows[n * k // 4:n * (k + 1) // 4] for k in range(4)]
    mine_moves = sum(sum(r["phase_moves"].values()) for r in rows)
    cls = collections.Counter()
    for r in rows:
        cls.update(r["classes"])
    phases = {}
    for ph in ("opening", "middlegame", "endgame"):
        mv = sum(r["phase_moves"].get(ph, 0) for r in rows)
        er = sum(r["phase_errors"].get(ph, 0) for r in rows)
        phases[ph] = {"moves": mv, "errors": er, "per100": round(100 * er / mv, 1) if mv else None}
    # clock
    timed = [m for m in moves if m.get("clock") is not None]
    bl = [m for m in moves if m["class"] == "blunder"]
    bl_t = [m for m in bl if m.get("clock") is not None]
    clock = {
        "games_with_clock": sum(1 for r in rows if r["base"]),
        "avg_seconds_per_move": mean([r["avg_spent"] for r in rows if r["base"]]),
        "time_trouble_games": sum(1 for r in rows if r["time_trouble"]),
        "score_in_time_trouble": _score([r for r in rows if r["time_trouble"]]),
        "score_without": _score([r for r in rows if r["base"] and not r["time_trouble"]]),
        "blunders_under_60s": sum(1 for m in bl_t if m["clock"] < 60), "blunders_timed": len(bl_t),
        "blunders_fast": sum(1 for m in bl if m.get("spent") is not None and m["spent"] < 5),
        "blunders_with_spent": sum(1 for m in bl if m.get("spent") is not None),
        "avg_spent_before_blunder": mean([m.get("spent") for m in bl]),
    }
    # motifs
    missed = collections.Counter(t for m in moves for t in m.get("motifs_missed", []))
    allowed = collections.Counter(t for m in moves for t in m.get("motifs_allowed", []))
    # opening exit (player's win % after move 10)
    by_first = collections.defaultdict(list)
    for r in rows:
        if r["exit_wp"] is not None and r["first"]:
            key = ("white " + r["first"][0]) if r["color"] == "white" else ("black " + " ".join(r["first"][:2]))
            by_first[key].append(r)
    openings = {k: {"games": len(v), "exit_wp": mean([x["exit_wp"] for x in v]), "score": _score(v)}
                for k, v in sorted(by_first.items(), key=lambda kv: -len(kv[1])) if len(v) >= 5}
    # puzzles: the biggest blunders and missed mates, one per game
    seen, puzzles = set(), []
    for m in sorted(moves, key=lambda m: (-(m.get("missed_mate_in") is not None), -m["drop"])):
        if m["game"] in seen or not m.get("best"):
            continue
        seen.add(m["game"])
        puzzles.append({k: m[k] for k in ("game", "date", "opp", "move_no", "side", "san", "best", "line", "drop", "link_puzzle",
                                          "missed_mate_in", "motifs_missed") if k in m})
        if len(puzzles) >= 12:
            break
    return {
        "games": n, "accuracy": mean([r["acc"] for r in rows]), "accuracy_opp": mean([r["acc_opp"] for r in rows]),
        "accuracy_white": mean([r["acc"] for r in rows if r["color"] == "white"]),
        "accuracy_black": mean([r["acc"] for r in rows if r["color"] == "black"]),
        "accuracy_by_result": {o: mean([r["acc"] for r in rows if r["outcome"] == o]) for o in ("win", "loss", "draw")},
        "accuracy_by_quarter": [{"range": [c[0]["n"], c[-1]["n"]], "dates": [c[0]["date"], c[-1]["date"]], "acc": mean([r["acc"] for r in c])}
                                for c in q if c],
        "accuracy_last_50": mean([r["acc"] for r in rows[-50:]]),
        "moves": mine_moves, "classes": dict(cls),
        "per_game": {k: round(v / n, 2) for k, v in cls.items()} if n else {},
        "first_error_move_median": sorted(r["first_error_move"] for r in rows if r["first_error_move"])[
            len([r for r in rows if r["first_error_move"]]) // 2] if any(r["first_error_move"] for r in rows) else None,
        "phases": phases, "clock": clock, "motifs_missed": dict(missed.most_common()), "motifs_allowed": dict(allowed.most_common()),
        "missed_mates": sum(1 for m in moves if m.get("missed_mate_in")), "missed_mates_in_1": sum(1 for m in moves if m.get("missed_mate_in") == 1),
        "allowed_mates": sum(1 for m in moves if m.get("allowed_mate_in")),
        "openings_exit": openings, "puzzles": puzzles,
    }


def _score(rs):
    if not rs:
        return None
    return round(100 * (sum(r["outcome"] == "win" for r in rs) + .5 * sum(r["outcome"] == "draw" for r in rs)) / len(rs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--stockfish")
    ap.add_argument("--seconds", type=float, default=None, help="per position (default 0.05 history, 0.3 single game)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--full", action="store_true", help="re-analyse every game (ignore the cache)")
    ap.add_argument("--pgn", help="analyse one game, both sides")
    a = ap.parse_args()
    me, out = a.username.strip().lower(), pathlib.Path(a.dir)
    path = S.find_stockfish(a.stockfish)
    if not path:
        sys.exit("Stockfish not found: pass --stockfish PATH or set STOCKFISH_PATH (see README). "
                 "The report can still be built with the material engine (scan.py).")

    if a.pgn:
        g = chess.pgn.read_game(open(a.pgn, encoding="utf-8"))
        eng = S.open_engine(path, threads=max(1, min(4, a.jobs)), hash_mb=128)
        evals = S.analyse_positions(eng, g, seconds=a.seconds or 0.3)
        eng.quit()
        recs = S.move_records(g, evals, me)
        for r in recs:
            if r["class"] in ("mistake", "blunder") or r.get("missed_mate_in"):
                r["link_puzzle"] = S.lichess_link(r["fen"], chess.WHITE if r["side"] == "white" else chess.BLACK)
        res = {"evals": [e["wp"] for e in evals], "moves": recs,
               "accuracy": S.game_accuracy(recs, True), "accuracy_opp": S.game_accuracy(recs, False)}
        (out / "sf_last.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"accuracy {res['accuracy']} (opponent {res['accuracy_opp']})")
        for r in recs:
            if r["class"] or r.get("missed_mate_in"):
                print(f"{'ME ' if r['mine'] else 'OPP'} {r['move_no']}{'.' if r['side'] == 'white' else '...'}{r['san']:7} {r['class'] or '':10} "
                      f"-{r['drop']:4}% best {r['best']} {r.get('motifs_missed', [])} | {r.get('line', '')}")
        return

    rows_meta = json.loads((out / "games.json").read_text(encoding="utf-8"))
    by_link = {r["link"]: r for r in rows_meta}
    cache = out / "sf"
    cache.mkdir(exist_ok=True)
    games, todo = [], []
    pgn = io.StringIO((out / "games.pgn").read_text(encoding="utf-8"))
    while (g := chess.pgn.read_game(pgn)) is not None:
        r = by_link.get(g.headers.get("Link", ""))
        if not r:
            continue
        text = str(g)
        key = gid(r["link"], text)
        games.append((r, g, key))
        if a.full or not (cache / f"{key}.json").exists():
            todo.append((key, text, a.seconds or 0.05))
    print(f"{len(games) - len(todo)} games cached, {len(todo)} to analyse with {path}", file=sys.stderr, flush=True)
    if todo:
        with multiprocessing.Pool(max(1, a.jobs), initializer=_init, initargs=(path,)) as pool:
            for k, (key, evals) in enumerate(pool.imap_unordered(_job, todo), 1):
                (cache / f"{key}.json").write_text(json.dumps(evals), encoding="utf-8")
                if k % 20 == 0 or k == len(todo):
                    print(f"analysed {k}/{len(todo)}", file=sys.stderr, flush=True)
    rows, moves = [], []
    for r, g, key in sorted(games, key=lambda x: x[0]["n"]):
        evals = json.loads((cache / f"{key}.json").read_text(encoding="utf-8"))
        recs = S.move_records(g, evals, me)
        rows.append(game_row(r, g, recs, evals, me))
        for m in recs:
            if m["mine"] and (m["class"] in ("mistake", "blunder") or m.get("missed_mate_in")):
                m.update(game=r["n"], date=r["date"], opp=r["opp"], outcome=r["outcome"], link=r["link"],
                         link_puzzle=S.lichess_link(m["fen"], chess.WHITE if m["side"] == "white" else chess.BLACK))
                moves.append(m)
    summ = summarize(rows, moves)
    (out / "sf_games.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    (out / "sf_moves.json").write_text(json.dumps(moves, ensure_ascii=False, indent=0), encoding="utf-8")
    (out / "sf_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: summ[k] for k in ("games", "accuracy", "accuracy_last_50", "per_game", "phases", "clock",
                                           "motifs_missed", "missed_mates", "allowed_mates")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
