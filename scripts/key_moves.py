"""Deeper Stockfish check of the key moves of the last game, in parallel (step 4c).

    python key_moves.py --dir OUT/data [--seconds 1.5] [--jobs N] [--plies 7,15,...]

Picks the moves worth a row in the key-moment table from sf_last.json:
  - every move of the player with a class (inaccuracy / mistake / blunder) or a win-% drop >= 5,
  - every mistake / blunder of the opponent and the player's reply to it (was it punished?),
  - every move of the player that was not Stockfish's choice (a superset of the hand checks),
  - every move (either side) that changes the material balance by 3 or more (captures),
  - every answer of the player to a check (king walks vs blocking), and the player's last move.
For each one it analyses, at the same strength the hand checks used (Stockfish, 1 thread,
`--seconds` per position, 2 best lines): the position before the move (best and second best line)
and the position after the played move (what it allows). Positions run on several engines side by
side, so 16 moves take about 10 s instead of about 50 s one after another; a mate position never
breaks the run (no 'pv' is simply an empty line).

Writes OUT/data/key_moves.json and prints for each move, ready for a table row: the decision frame
(= the ply index, as used by GOTO buttons and row()), the move as a piece name plus SAN, the
material balance from the player's side before and after, and the player's chances (lichess win %,
the same scale as sf_last.json) for the best move, the second best and the played move, each with
its line. `--plies` adds more decision plies to check.
"""
import argparse, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

import chess, chess.engine, chess.pgn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sf_engine import find_stockfish, open_engine, win_pct  # noqa: E402
import timing  # noqa: E402

VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
BG = dict(K="Цар", Q="Царица", R="Топ", B="Офицер", N="Кон")


def material(board, color):
    return sum(VAL[p.piece_type] * (1 if p.color == color else -1) for p in board.piece_map().values())


def bg_move(board, move):
    """'17...Кон взима h5 (Nxh5)' – board is BEFORE the move."""
    san = board.san(move)
    num = f"{board.fullmove_number}." if board.turn == chess.WHITE else f"{board.fullmove_number}..."
    if board.is_castling(move):
        return f"{num}{'дълга' if board.is_queenside_castling(move) else 'къса'} рокада ({san})"
    p = board.piece_at(move.from_square)
    name = BG.get(p.symbol().upper(), "пешка")
    if p.piece_type == chess.PAWN:
        rest = san.replace("x", " взима ", 1) if "x" in san else san   # 'e взима d5'
    else:
        rest = san[1:].replace("x", " взима ", 1).lstrip()   # 'Топ b взима c8' for Rbxc8
    return f"{num}{name} {rest} ({san})"


def chance(info, me):
    s = info["score"].pov(me)
    return round(win_pct(mate=s.mate()) if s.is_mate() else win_pct(cp=s.score()), 1), str(s)


def line(board, info, n):
    pv = info.get("pv", [])[:n]
    try:
        return board.variation_san(pv) if pv else ""
    except Exception:
        return " ".join(m.uci() for m in pv)


def mine_pct(r, key):
    """sf_last 'before'/'after' are from the mover's side; turn them to the player's side."""
    v = r.get(key)
    return None if v is None else (v if r["mine"] else round(100 - v, 1))


def pick(moves, extra):
    plies = set(extra)
    for i, m in enumerate(moves):
        if m.get("mine") and (m.get("class") or (m.get("drop") or 0) >= 5):
            plies.add(m["ply"])
        # every move of the player that was not the engine's choice
        if m.get("mine") and m.get("best") and m.get("best") != m.get("san"):
            plies.add(m["ply"])
        if not m.get("mine") and m.get("class") in ("mistake", "blunder"):
            plies.add(m["ply"])
            if i + 1 < len(moves):
                plies.add(moves[i + 1]["ply"])
    return plies


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--seconds", type=float, default=1.5)
    ap.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) // 2)))
    ap.add_argument("--plies", default="", help="extra decision plies, comma separated")
    a = ap.parse_args()
    t0 = time.time()
    sf = json.load(open(os.path.join(a.dir, "sf_last.json"), encoding="utf-8"))
    game = chess.pgn.read_game(open(os.path.join(a.dir, "last.pgn"), encoding="utf-8"))
    mv = list(game.mainline_moves())
    moves = sf["moves"]
    me = chess.WHITE if any(m["mine"] and m["side"] == "white" for m in moves) else chess.BLACK

    boards = []
    b = chess.Board()
    for m in mv:
        boards.append(b.copy())
        b.push(m)
    plies = pick(moves, [int(x) for x in a.plies.split(",") if x.strip()])
    for p in range(len(mv)):  # material swings of either side's moves
        if True:
            after = boards[p + 1] if p + 1 < len(boards) else b
            if abs(material(after, me) - material(boards[p], me)) >= 3:
                plies.add(p)
    for p in range(len(mv)):  # the player's answers to a check (king walks, blocks)
        if boards[p].turn == me and boards[p].is_check():
            plies.add(p)
    if mv and boards[-1].turn == me:
        plies.add(len(mv) - 1)  # the player's last move (the mate, or the move before resigning)
    plies = sorted(p for p in plies if 0 <= p < len(mv))

    local = threading.local()
    engines = []
    lock = threading.Lock()
    path = find_stockfish()

    def eng():
        if not hasattr(local, "e"):
            local.e = open_engine(path, threads=1, hash_mb=64)
            with lock:
                engines.append(local.e)
        return local.e

    def work(job):
        p, which = job
        board = boards[p].copy()
        if which == "after":
            board.push(mv[p])
            if board.is_game_over():
                return job, []
            return job, [eng().analyse(board, chess.engine.Limit(time=a.seconds))]
        return job, eng().analyse(board, chess.engine.Limit(time=a.seconds), multipv=2)

    jobs = [(p, w) for p in plies for w in ("before", "after")]
    res = {}
    try:
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            for job, info in ex.map(work, jobs):
                res[job] = info
    finally:
        for e in engines:
            try:
                e.quit()
            except Exception:
                pass

    out = []
    for p in plies:
        bb, played = boards[p], mv[p]
        aft = bb.copy(); aft.push(played)
        before, after = res[(p, "before")], res[(p, "after")]
        row = {"frame": p, "mine": bb.turn == me, "move": bg_move(bb, played), "san": bb.san(played),
               "class": moves[p].get("class"), "sf_before": moves[p].get("before"), "sf_after": moves[p].get("after"),
               "material_before": material(bb, me), "material_after": material(aft, me),
               "lines": []}
        for k, info in enumerate(before):
            c, sc = chance(info, me)
            first = info.get("pv", [None])[0] if info.get("pv") else None
            row["lines"].append({"kind": "best" if k == 0 else "second", "chance": c, "score": sc,
                                 "move": bg_move(bb, first) if first else "", "line": line(bb, info, 12 if k == 0 else 6)})
        if after:
            c, sc = chance(after[0], me)
            row["lines"].append({"kind": "played", "chance": c, "score": sc, "line": line(aft, after[0], 12)})
        else:
            row["lines"].append({"kind": "played", "chance": 100.0 if aft.is_checkmate() and bb.turn == me else 0.0 if aft.is_checkmate() else 50.0,
                                 "score": aft.result(), "line": "(game over)"})
        out.append(row)

    json.dump({"seconds": a.seconds, "me": "white" if me else "black", "moves": out},
              open(os.path.join(a.dir, "key_moves.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    side = "White" if me else "Black"
    print(f"key_moves: {len(plies)} moves, {len(jobs)} positions at {a.seconds}s on {a.jobs} engines; chances for {side} (the player)")
    for r in out:
        who = "YOU" if r["mine"] else "opp"
        cls = f" [{r['class']}]" if r["class"] else ""
        print(f"frame {r['frame']:3d} {who} {r['move']}{cls}  material {r['material_before']:+d} -> {r['material_after']:+d}"
              f"  sf_last {mine_pct(r, 'sf_before')}% -> {mine_pct(r, 'sf_after')}%")
        for l in r["lines"]:
            head = {"best": "  best  ", "second": "  2nd   ", "played": "  after "}[l["kind"]]
            print(f"{head}{l['chance']:5.1f}% ({l['score']}) {l.get('move', '')}: {l['line']}")
    took = time.time() - t0
    timing.record("key_moves", took, positions=len(jobs), jobs=a.jobs, inner=bool(os.environ.get("ANALYZE_LAST")) or None)
    print(f"key_moves: done in {took:.0f}s")


if __name__ == "__main__":
    main()
