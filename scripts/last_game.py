"""Deeper look at the last game: puzzles, threats, clock, the opponent's mistakes, recurring motifs, the opening
against the lichess database and a comparison with the previous games.

    python last_game.py USERNAME --dir OUT [--depth 18] [--recent 20] [--motif-games 50]

Needs OUT/last.pgn and OUT/sf_last.json (sf_scan.py --pgn OUT/last.pgn). Uses, when present, OUT/sf_games.json and
OUT/sf_moves.json (history), OUT/explorer.json (rating bands and speeds for the lichess explorer, and its cache).
Writes OUT/last_extra.json:
  moments    your mistakes, blunders and missed mates: chances before / after, clock, the threat in the position
             (what the opponent would play if it were their move again), what your move allowed, the motifs and how
             often they came up in your recent games, and a puzzle (the accepted moves and the solution line)
  opp        the opponent's mistakes and blunders and whether your reply kept the gain (punished / partly / missed)
  clock      time per move: yours, before your mistakes, how many mistakes took under 10 seconds
  opening    where the game left the moves known in the lichess database, who left first, your known moves that
             score worse than a popular alternative
  compare    this game against the average of your previous games (accuracy, mistakes by phase, time per move)
Win % everywhere is from your side.
"""
import argparse
import collections
import json
import pathlib
import statistics
import sys

import chess
import chess.engine
import chess.pgn

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sf_engine  # noqa: E402

PIECE = {chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B", chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}


def wp_for(score, colour):
    s = score.pov(colour)
    if s.is_mate():
        return 100.0 if s.mate() > 0 else 0.0
    return round(sf_engine.win_pct(s.score(), None), 1)


def move_info(board, mv):
    """SAN plus what the move takes and whether it mates."""
    cap = board.piece_at(mv.to_square) if board.is_capture(mv) else None
    if board.is_en_passant(mv):
        cap = chess.Piece(chess.PAWN, not board.turn)
    after = board.copy()
    after.push(mv)
    return {"san": board.san(mv), "uci": mv.uci(), "from": chess.square_name(mv.from_square), "to": chess.square_name(mv.to_square),
            "piece": PIECE[board.piece_at(mv.from_square).piece_type], "takes": PIECE[cap.piece_type] if cap else None,
            "mate": after.is_checkmate(), "check": after.is_check()}


def material(board, colour):
    """Your pieces minus the opponent's, by type: {"P": 1, "B": -1, ...} (zero types left out)."""
    out = {}
    for t, k in ((chess.PAWN, "P"), (chess.KNIGHT, "N"), (chess.BISHOP, "B"), (chess.ROOK, "R"), (chess.QUEEN, "Q")):
        d = len(board.pieces(t, colour)) - len(board.pieces(t, not colour))
        if d:
            out[k] = d
    return out


VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def points(board, colour):
    return sum(VALUE.get(p.piece_type, 0) * (1 if p.color == colour else -1) for p in board.piece_map().values())


def material_drop(board, move, after_line, colour):
    """Points your move gives away against the opponent's best reply (Stockfish's after_line, followed while
    the exchange goes on: captures and checks, at least 2 plies, at most 6). A move can lose the queen and still
    keep a won position, so the win-% classes miss it; this catches it."""
    b = board.copy()
    start = points(b, colour)
    b.push(move)
    n = 0
    for tok in (after_line or "").split():
        tok = tok.lstrip("0123456789.")  # "24...Qxa5" or "25." -> "Qxa5" / ""
        if not tok:
            continue
        try:
            m = b.parse_san(tok)
        except ValueError:
            break
        cap = b.is_capture(m)
        b.push(m)
        n += 1
        if b.is_game_over() or n >= 6 or (n >= 2 and not cap and not b.is_check()):
            break
    return start - points(b, colour)


def line_san(board, pv, n):
    b, out = board.copy(), []
    for m in pv[:n]:
        out.append(b.san(m))
        b.push(m)
        if b.is_game_over():
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--depth", type=int, default=18)
    ap.add_argument("--recent", type=int, default=20, help="previous games to compare with")
    ap.add_argument("--motif-games", type=int, default=50, help="recent games in which motifs are counted")
    ap.add_argument("--stockfish")
    a = ap.parse_args()
    me, out = a.username.strip().lower(), pathlib.Path(a.dir)
    g = chess.pgn.read_game(open(out / "last.pgn", encoding="utf-8"))
    white = g.headers["White"].lower() == me
    col = chess.WHITE if white else chess.BLACK
    link = g.headers.get("Link", "")
    moves = list(g.mainline_moves())
    sfl = json.loads((out / "sf_last.json").read_text(encoding="utf-8"))
    ev = [w if white else round(100 - w, 1) for w in sfl["evals"]]  # my win % after each ply
    rows = {m["ply"]: m for m in sfl["moves"]}

    def board_at(ply):
        b = g.board()
        for m in moves[:ply]:
            b.push(m)
        return b

    path = sf_engine.find_stockfish(a.stockfish)
    if not path:
        sys.exit("Stockfish not found: run update_stockfish.py")
    eng = sf_engine.open_engine(path, threads=2, hash_mb=128)
    lim = chess.engine.Limit(depth=a.depth)

    # ---- history for the motif counts and the comparison
    hist_moves = json.loads((out / "sf_moves.json").read_text(encoding="utf-8")) if (out / "sf_moves.json").exists() else []
    hist_games = json.loads((out / "sf_games.json").read_text(encoding="utf-8")) if (out / "sf_games.json").exists() else []
    hist_games = [r for r in hist_games if r.get("link") != link]
    recent_n = {r["n"] for r in hist_games[-a.motif_games:]}
    motif_count = collections.Counter()
    for m in hist_moves:
        if m.get("mine") and m.get("game") in recent_n and m.get("link") != link and m.get("class") in ("mistake", "blunder"):
            for t in m.get("motifs_missed") or []:
                motif_count[("missed", t)] += 1
            for t in m.get("motifs_allowed") or []:
                motif_count[("allowed", t)] += 1

    # ---- your mistakes, blunders and missed mates
    moments = []
    try:
        for ply in range(len(moves)):
            r = rows.get(ply)
            if not r or not r.get("mine"):
                continue
            missed_mate = any(t in ("mate", "back_rank_mate") for t in r.get("motifs_missed") or [])
            b = board_at(ply)
            after_line = r.get("after_line")
            if not after_line:  # sf_scan keeps the reply line only for the moves it classified: work it out here
                ab = b.copy()
                ab.push(moves[ply])
                if not ab.is_game_over():
                    ai0 = eng.analyse(ab, chess.engine.Limit(depth=12))
                    after_line = ab.variation_san(ai0.get("pv", [])[:6])
            drop = material_drop(b, moves[ply], after_line, col)
            if r.get("class") not in ("mistake", "blunder") and not missed_mate and drop < 3:
                continue
            by_material = r.get("class") not in ("mistake", "blunder") and not missed_mate
            if by_material:  # still winning (or already lost), but a piece given away
                r = dict(r, **{"class": "blunder" if drop >= 5 else "mistake"})
            played = move_info(b, moves[ply])
            multi = eng.analyse(b, lim, multipv=4)
            top = wp_for(multi[0]["score"], col)
            ok = [i["pv"][0].uci() for i in multi if i.get("pv") and wp_for(i["score"], col) >= top - 3]
            if by_material and multi[0].get("pv"):
                # only when the best move keeps that material: a piece that is lost whatever you play is not this move's fault
                bb0 = b.copy()
                bb0.push(multi[0]["pv"][0])
                best_drop = material_drop(b, multi[0]["pv"][0], bb0.variation_san(multi[0]["pv"][1:7]), col)
                if drop - best_drop < 3:
                    continue
            best = move_info(b, multi[0]["pv"][0])
            # the line shown: 5 plies, longer while it would stop in the middle of an exchange (a capture or a check
            # still to be answered), so the material at its end is a real count (at most 11 plies)
            pv0 = multi[0]["pv"]
            n, eb = 0, b.copy()
            while n < len(pv0) and n < 11:
                cap = eb.is_capture(pv0[n])
                eb.push(pv0[n])
                n += 1
                if eb.is_game_over() or (n >= 5 and not cap and not eb.is_check()):
                    break
            sol = line_san(b, pv0, n)
            # a draw by perpetual check: about even, and every one of your moves in the line gives check
            bb, checks = b.copy(), []
            for k, m_ in enumerate(multi[0]["pv"][:7]):
                bb.push(m_)
                if k % 2 == 0:
                    checks.append(bb.is_check())
            perpetual = 45 <= top <= 55 and len(checks) >= 3 and all(checks)
            # the next best move that is not the first one: a choice without the sacrifice
            alt = next(({"san": b.san(i["pv"][0]), "wp": wp_for(i["score"], col)} for i in multi[1:]
                        if i.get("pv") and i["pv"][0] != moves[ply]), None)
            if best["mate"] and not played["mate"]:  # a mate in one: only mating moves solve the puzzle
                ok = [i["pv"][0].uci() for i in multi if i.get("pv") and move_info(b, i["pv"][0])["mate"]]
                missed_mate = True
            elif moves[ply].uci() in ok:
                if drop < 3:  # the played move was fine after all at this depth
                    continue
                # in a lost (or won) position every move scores about the same; a move that gives away a piece is
                # still a mistake: the other top moves solve the puzzle
                ok = [u for u in ok if u != moves[ply].uci()]
                if not ok:
                    continue
            # the threat: what the opponent would play if it were their move now
            threat = None
            if not b.is_check():
                nb = b.copy()
                nb.push(chess.Move.null())
                ti = eng.analyse(nb, lim)
                if ti.get("pv"):
                    tw = wp_for(ti["score"], col)
                    threat = dict(move_info(nb, ti["pv"][0]), wp=tw, line=line_san(nb, ti["pv"], 3), ply=ply)
            after = board_at(ply + 1)
            ai = eng.analyse(after, lim)
            allowed = dict(move_info(after, ai["pv"][0]), line=line_san(after, ai["pv"], 4)) if ai.get("pv") and not after.is_game_over() else None
            tags = sorted(set((r.get("motifs_missed") or [])))
            tags_a = sorted(set((r.get("motifs_allowed") or [])))
            moments.append({
                "ply": ply, "move_no": ply // 2 + 1, "played": played, "best": best, "ok": ok, "solution": sol,
                "before": ev[ply], "after": ev[ply + 1], "best_wp": top, "material_drop": drop, "perpetual": perpetual, "mat_before": material(b, col), "mat_end": material(eb, col), "alt": alt, "class": r.get("class"), "missed_mate": missed_mate,
                "phase": r.get("phase"), "spent": r.get("spent"), "clock": r.get("clock"),
                "threat": threat, "allowed": allowed, "motifs_missed": tags, "motifs_allowed": tags_a,
                "seen_missed": {t: motif_count[("missed", t)] for t in tags}, "seen_allowed": {t: motif_count[("allowed", t)] for t in tags_a},
            })

        # ---- the opponent's mistakes: did your reply keep the gain?
        opp = []
        for ply in range(len(moves) - 1):
            r = rows.get(ply)
            if not r or r.get("mine") or r.get("class") not in ("mistake", "blunder"):
                continue
            gain = ev[ply + 1] - ev[ply]
            kept = ev[ply + 2] - ev[ply]
            b = board_at(ply + 1)
            bi = eng.analyse(b, lim)
            best = move_info(b, bi["pv"][0]) if bi.get("pv") else None
            reply = move_info(b, moves[ply + 1])
            verdict = "punished" if kept >= 0.6 * gain else "partly" if kept >= 0.25 * gain else "missed"
            if best and best["uci"] == reply["uci"]:
                verdict = "punished"
            opp.append({"ply": ply, "move": move_info(board_at(ply), moves[ply]), "class": r["class"], "before": ev[ply], "after": ev[ply + 1],
                        "reply": reply, "after_reply": ev[ply + 2], "best": best, "best_wp": wp_for(bi["score"], col),
                        "best_line": line_san(b, bi.get("pv", []), 4), "verdict": verdict})
    finally:
        eng.quit()

    # ---- clock
    mine_rows = [rows[p] for p in sorted(rows) if rows[p].get("mine") and rows[p].get("spent") is not None]
    spent = [m["spent"] for m in mine_rows]
    err = [m for m in moments if m["spent"] is not None]
    clock = {"avg": round(statistics.mean(spent), 1) if spent else None, "median": round(statistics.median(spent), 1) if spent else None,
             "max": max(spent) if spent else None,
             "max_move": next((m["move_no"] for m in mine_rows if m["spent"] == max(spent)), None) if spent else None,
             "errors_avg": round(statistics.mean(m["spent"] for m in err), 1) if err else None,
             "errors_fast": sum(1 for m in err if m["spent"] < 10), "errors": len(err),
             "left": mine_rows[-1]["clock"] if mine_rows else None}

    # ---- opening against the lichess database
    opening = None
    exf = out / "explorer.json"
    if exf.exists():
        try:
            import explorer
            p = json.loads(exf.read_text(encoding="utf-8"))["params"]
            ex = explorer.Explorer(out / "explorer" / "cache.json", p["ratings"], p["speeds"])
            b, steps, exit_ply, who = g.board(), [], None, "none"
            try:
                for ply, mv in enumerate(moves[:p["max_ply"]]):
                    rec = ex.get(b)
                    if rec["w"] + rec["d"] + rec["b"] < p["min_games"]:
                        exit_ply, who = ply, ("opp" if (b.turn == col) else "me")
                        break
                    st = explorer.move_stats(rec, b.turn == chess.WHITE)
                    san = b.san(mv)
                    mine = b.turn == col
                    known = {s: v for s, v in st.items() if v[0] >= p["min_games"]}
                    best = max(known, key=lambda s: known[s][2]) if known else None
                    steps.append({"ply": ply, "san": san, "mine": mine, "db": st.get(san), "best": best, "best_db": known.get(best),
                                  "popular": max(st, key=lambda s: st[s][0]) if st else None})
                    if st.get(san, (0,))[0] < p["min_games"]:
                        exit_ply, who = ply, ("me" if mine else "opp")
                        break
                    b.push(mv)
            finally:
                ex.save()
            weaker = [s for s in steps if s["mine"] and s["db"] and s["best_db"] and s["best"] != s["san"] and s["best_db"][2] - s["db"][2] >= 4]
            opening = {"params": p, "steps": steps, "exit_ply": exit_ply, "who": who, "weaker": weaker,
                       "name": g.headers.get("ECOUrl", "").rsplit("/", 1)[-1].replace("-", " "), "eco": g.headers.get("ECO")}
        except Exception as e:  # no network: leave the part out
            print(f"opening explorer skipped: {e}", flush=True)

    # ---- this game against the previous ones
    def phase_err(rs):
        c = collections.Counter(m["phase"] for m in rs if m.get("mine") and m.get("class") in ("mistake", "blunder"))
        return {ph: c.get(ph, 0) for ph in ("opening", "middlegame", "endgame")}

    prev = hist_games[-a.recent:]
    compare = None
    if prev:
        def avg(f):
            v = [f(r) for r in prev]
            v = [x for x in v if x is not None]
            return round(statistics.mean(v), 1) if v else None
        this_pe = phase_err(sfl["moves"])
        first_err = next((m["move_no"] for m in sfl["moves"] if m.get("mine") and m.get("class") in ("mistake", "blunder")), None)
        compare = {
            "games": len(prev), "since": prev[0].get("date"),
            "this": {"acc": sfl.get("accuracy"), "acc_opp": sfl.get("accuracy_opp"), "errors": sum(this_pe.values()), **{f"err_{k}": v for k, v in this_pe.items()},
                     "blunders": sum(1 for m in sfl["moves"] if m.get("mine") and m.get("class") == "blunder"),
                     "first_error": first_err, "spent": clock["avg"]},
            "avg": {"acc": avg(lambda r: r.get("acc")), "acc_opp": avg(lambda r: r.get("acc_opp")),
                    "errors": avg(lambda r: sum((r.get("phase_errors") or {}).values())),
                    **{f"err_{k}": avg(lambda r, k=k: (r.get("phase_errors") or {}).get(k, 0)) for k in ("opening", "middlegame", "endgame")},
                    "blunders": avg(lambda r: (r.get("classes") or {}).get("blunder", 0)),
                    "first_error": avg(lambda r: r.get("first_error_move")), "spent": avg(lambda r: r.get("avg_spent"))},
        }

    res = {"link": link, "white": white, "date": g.headers.get("UTCDate"), "opp": g.headers["Black" if white else "White"],
           "moves": [m.uci() for m in moves], "motif_games": len(recent_n), "moments": moments, "opp": opp, "clock": clock,
           "opening": opening, "compare": compare}
    (out / "last_extra.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"last_extra.json: {len(moments)} moments, {len(opp)} opponent mistakes "
          f"({sum(1 for o in opp if o['verdict'] == 'punished')} punished), opening {'yes' if opening else 'no'}, "
          f"compared with {compare['games'] if compare else 0} games")
    for m in moments:
        t = m["threat"]
        print(f"  {m['move_no']}{'.' if white else '...'}{m['played']['san']} -> {m['best']['san']} ok={m['ok']} "
              f"{m['before']}->{m['after']} spent {m['spent']}s threat {t['san'] if t else '-'} ({t['wp'] if t else ''}) "
              f"allowed {m['allowed']['san'] if m['allowed'] else '-'} motifs {m['seen_missed']} {m['seen_allowed']}")
    for o in opp:
        print(f"  opp {o['ply'] // 2 + 1}.{o['move']['san']} {o['before']}->{o['after']} reply {o['reply']['san']} -> {o['after_reply']} "
              f"best {o['best']['san'] if o['best'] else '-'} {o['verdict']}")


if __name__ == "__main__":
    main()
