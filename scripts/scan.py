"""Find mistakes and missed chances with the small engine.

Whole history (player's moves only):
  python scan.py USERNAME --dir OUT [--games 120] [--depth 3]
  -> OUT/flagged.json: moves where the player lost material or missed a win/mate, sorted by size,
     each verified at depth 5 with the best line ("line") and what happened after the played move ("after").

One game (both sides, every move printed):
  python scan.py USERNAME --dir OUT --pgn OUT/last.pgn
  -> prints a move table and OUT/last_flagged.json with verified lines.

Ply/frame convention used everywhere in this skill: "ply" = number of half-moves already played
BEFORE the move (0 = the first move of the game). In the step-through viewer the position AFTER that
move is frame ply+1. White's move N is ply 2N-2, Black's move N is ply 2N-1.
"""
import argparse
import io
import json
import pathlib
import sys
import chess
import chess.pgn
from engine import best_and_played, pv, material, MATE


def classify(board, best, played):
    before = material(board)
    if best > 900 and played < 900:
        return "missed_mate"
    if played <= -900:
        return "allowed_mate"
    if played < before - 1 and best - played >= 2:
        return "lost_material"
    return "missed_gain"


def scan_game(game, me, depth, both_sides=False, verbose=False):
    out, b = [], game.board()
    color = chess.WHITE if game.headers["White"].lower() == me else chess.BLACK
    for i, mv in enumerate(game.mainline_moves()):
        mine = b.turn == color
        if mine or both_sides:
            best, bm, ps = best_and_played(b, mv, depth=depth)
            flag = best - ps >= 2 or (best > 900 and ps < 900)
            if verbose:
                print(f"ply {i:3} {b.fullmove_number}{'.' if b.turn else '...'}{b.san(mv):8} {'ME ' if mine else 'OPP'} "
                      f"played={ps:5} best={b.san(bm):8} {best:5}{'  <==' if flag else ''}", flush=True)
            if flag:
                out.append(dict(ply=i, frame=i + 1, move_no=b.fullmove_number, side="white" if b.turn else "black",
                                mine=mine, played=b.san(mv), best=b.san(bm), best_score=best, played_score=ps,
                                drop=min(best, 999) - max(ps, -999), kind=classify(b, best, ps), fen=b.fen()))
        b.push(mv)
    return out


def verify(items, depth=5):
    for f in items:
        b = chess.Board(f["fen"])
        played = b.parse_san(f["played"])
        best, bm, ps = best_and_played(b, played, depth=depth)
        f.update(best_score=best, played_score=ps, best=b.san(bm), line=" ".join(pv(b, depth)))
        after = b.copy()
        after.push(played)
        f["after"] = " ".join(pv(after, depth - 1))
        f["confirmed"] = best - ps >= 2 or (best > 900 and ps < 900)
        f["kind"] = classify(b, best, ps)
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--games", type=int, default=120, help="scan only the last N games (default 120)")
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--pgn", help="scan a single game, both sides")
    ap.add_argument("--verify-top", type=int, default=60)
    a = ap.parse_args()
    me = a.username.strip().lower()
    out = pathlib.Path(a.dir)

    if a.pgn:
        game = chess.pgn.read_game(open(a.pgn, encoding="utf-8"))
        items = verify(scan_game(game, me, a.depth, both_sides=True, verbose=True))
        for f in items:
            tag = "ME " if f["mine"] else "OPP"
            print(f"[{tag}] ply {f['ply']} {f['move_no']}{'.' if f['side'] == 'white' else '...'}{f['played']} "
                  f"({f['kind']}, confirmed={f['confirmed']}) best {f['best']} {f['best_score']} vs {f['played_score']} | "
                  f"line: {f['line']} | after played: {f['after']}")
        (out / "last_flagged.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        return

    rows = json.loads((out / "games.json").read_text(encoding="utf-8"))
    pgn = io.StringIO((out / "games.pgn").read_text(encoding="utf-8"))
    by_link, games = {r["link"]: r for r in rows}, []
    while (g := chess.pgn.read_game(pgn)) is not None:
        r = by_link.get(g.headers.get("Link", ""))
        if r:
            games.append((r, g))
    games.sort(key=lambda x: x[0]["n"])
    games = games[-a.games:]
    flagged = []
    for k, (r, g) in enumerate(games, 1):
        for f in scan_game(g, me, a.depth):
            f.update(game=r["n"], opp=r["opp"], date=r["date"], color=r["color"], outcome=r["outcome"], link=r["link"])
            flagged.append(f)
        print(f"scanned {k}/{len(games)}", file=sys.stderr, flush=True)
    flagged.sort(key=lambda f: -f["drop"])
    verify(flagged[:a.verify_top])
    flagged = [f for f in flagged if f.get("confirmed", True)]
    kinds = {}
    for f in flagged:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    (out / "flagged.json").write_text(json.dumps(flagged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(games)} games scanned, {len(flagged)} flagged moves: {kinds}")
    for f in [x for x in flagged if x.get("line")][:25]:
        print(f"G{f['game']} vs {f['opp']} {f['move_no']}{'.' if f['side'] == 'white' else '...'}{f['played']} "
              f"[{f['kind']}] best {f['best']} ({f['best_score']} vs {f['played_score']}) line: {f.get('line', '')}")


if __name__ == "__main__":
    main()
