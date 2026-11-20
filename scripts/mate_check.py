"""Find every forced mate in a game: missed mates and slower mates.

For each move of the player it asks Stockfish whether the side to move had a forced
mate. Consecutive moves with a mate on the board form an "episode". For each episode
it reports:
  - where the mate first appeared and in how many moves (mate in N),
  - the fastest line (played out move by move with Stockfish),
  - what happened: mated in M moves (M - N moves lost), or the mate was missed
    (the played move let it go; the chance that remained is printed).
The same is done for the opponent's mates against the player (missed by the opponent).

With --gifs DIR it also writes two GIFs per episode where something was lost
(played line vs fastest line) using make_gif.py.

  python mate_check.py USERNAME --pgn data/last.pgn [--out data/mate_check.json] [--gifs .]
"""
import argparse, json, os, subprocess, sys
import chess, chess.pgn, chess.engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sf_engine import find_stockfish

DEPTH = 22
DEPTH_MATE = 32


_CACHE = {}


def _analyse(engine, board):
    info = engine.analyse(board, chess.engine.Limit(depth=DEPTH))
    if info["score"].is_mate():   # mate distances at low depth are rough: look deeper
        info = engine.analyse(board, chess.engine.Limit(depth=DEPTH_MATE))
    return info["score"].pov(board.turn).mate(), info


def prefill(boards, jobs):
    """Analyse many positions at once: several single-thread engines in parallel (Stockfish with many threads at a
    fixed depth is slower than one thread, so the speed comes from running positions side by side)."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    local, engines, lock = threading.local(), [], threading.Lock()

    def work(b):
        if not hasattr(local, "eng"):
            local.eng = chess.engine.SimpleEngine.popen_uci(find_stockfish())
            local.eng.configure({"Threads": 1, "Hash": 64})
            with lock:
                engines.append(local.eng)
        return b.fen(), _analyse(local.eng, b)
    todo = {b.fen(): b for b in boards if not b.is_checkmate() and b.fen() not in _CACHE}
    try:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            for fen, r in ex.map(work, todo.values()):
                _CACHE[fen] = r
    finally:
        for e in engines:
            e.quit()


def mate_in(engine, board):
    """Mate distance for the side to move (>0 it mates, <0 it gets mated, None no mate), cached per position."""
    if board.is_checkmate():
        return -0, None
    key = board.fen()
    if key not in _CACHE:
        _CACHE[key] = _analyse(engine, board)
    return _CACHE[key]


def fastest_line(engine, board, n):
    """Play the mating side's best moves (and the defender's best) until mate."""
    b = board.copy(); line = []
    for _ in range(2 * n + 2):
        if b.is_game_over():
            break
        left = n - len(line) // 2   # moves of the mating side still to play
        info = engine.analyse(b, chess.engine.Limit(mate=max(1, left))) if left > 0 else {}
        if not info.get("pv"):     # the mate search found nothing: plain search
            info = engine.analyse(b, chess.engine.Limit(depth=DEPTH))
        m = info["pv"][0]
        line.append(b.san(m)); b.push(m)
    return line


def chance(info, turn):
    wdl = info["score"].pov(turn).wdl(model="sf", ply=30)
    return round(100 * (wdl.wins + 0.5 * wdl.draws) / 1000, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--pgn", required=True)
    ap.add_argument("--out")
    ap.add_argument("--gifs", help="folder for played/fastest GIFs")
    ap.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) // 2)),
                    help="positions analysed side by side (one single-thread engine each)")
    a = ap.parse_args()

    g = chess.pgn.read_game(open(a.pgn, encoding="utf-8"))
    me_white = g.headers.get("White", "").lower() == a.username.lower()
    me = chess.WHITE if me_white else chess.BLACK
    moves = list(g.mainline_moves())
    b = g.board(); boards = [b.copy()]
    for m in moves:
        b.push(m); boards.append(b.copy())
    prefill(boards, a.jobs)
    eng = chess.engine.SimpleEngine.popen_uci(find_stockfish())
    eng.configure({"Hash": 128})

    b = g.board()
    rows = []  # per ply where the side to move had a mate
    for ply, m in enumerate(moves):
        mi, info = mate_in(eng, b)
        if mi is not None and mi > 0:
            san = b.san(m)
            after = b.copy(); after.push(m)
            if after.is_checkmate():
                left, ch = 0, 100.0
            else:
                ra = mate_in(eng, after)
                mo, ia = ra
                left = -mo if (mo is not None and mo < 0) else None   # mates still on (in moves)
                ch = 100.0 if left is not None else round(100 - chance(ia, after.turn), 1)
            rows.append(dict(ply=ply, side="me" if b.turn == me else "opp", mate_in=mi, played=san,
                             move_no=b.fullmove_number, white=b.turn == chess.WHITE,
                             mate_after=left, chance_after=ch, fen=b.fen()))
        b.push(m)

    # group into episodes: same side, consecutive own moves (ply step 2)
    eps = []
    for r in rows:
        if eps and eps[-1]["side"] == r["side"] and r["ply"] == eps[-1]["rows"][-1]["ply"] + 2 \
                and eps[-1]["rows"][-1]["mate_after"] is not None:
            eps[-1]["rows"].append(r)
        else:
            eps.append(dict(side=r["side"], rows=[r]))
    out = []
    for e in eps:
        last = e["rows"][-1]
        # the step from which the earliest mate was possible (mate on move move_no + mate_in - 1)
        first = min(e["rows"], key=lambda r: (r["move_no"] + r["mate_in"], r["ply"]))
        e["rows"] = [r for r in e["rows"] if r["ply"] >= first["ply"]]
        start = chess.Board(first["fen"])
        best = fastest_line(eng, start, first["mate_in"])
        mated = last["mate_after"] == 0
        ended = not mated and last["mate_after"] is not None   # the game ended (resignation, time) with the mate still on
        earliest = first["move_no"] + first["mate_in"] - 1
        res = dict(side=e["side"], ply=first["ply"], move_no=first["move_no"], white=first["white"],
                   mate_in=first["mate_in"], fastest=best, played=[r["played"] for r in e["rows"]],
                   mated=mated, ended=ended, end_ply=last["ply"], earliest_mate_move=earliest,
                   mate_move=last["move_no"] if mated else None,
                   lost_moves=(last["move_no"] - earliest) if mated else None,
                   missed=None if (mated or ended) else dict(ply=last["ply"], move_no=last["move_no"], played=last["played"],
                                                  chance_after=last["chance_after"]),
                   steps=[dict(ply=r["ply"], move_no=r["move_no"], played=r["played"], mate_in=r["mate_in"],
                               mate_after=r["mate_after"]) for r in e["rows"]])
        out.append(res)
    eng.quit()

    def mv(n, white, san):
        return f"{n}.{san}" if white else f"{n}...{san}"
    for e in out:
        who = "ВИЕ" if e["side"] == "me" else "ПРОТИВНИКЪТ"
        print(f"== {who}: мат в {e['mate_in']} от ход {e['move_no']} ({'бели' if e['white'] else 'черни'}), "
              f"най-бързо: {' '.join(e['fastest'])}")
        for s in e["steps"]:
            tag = "мат" if s["mate_after"] == 0 else ("ок" if s["mate_after"] is not None and s["mate_after"] == s["mate_in"] - 1
                                                    else ("по-бавно" if s["mate_after"] is not None else "ПРОПУСНАТ"))
            print(f"   {mv(s['move_no'], e['white'], s['played'])}: мат в {s['mate_in']} -> "
                  f"{'мат' if s['mate_after']==0 else (('мат в ' + str(s['mate_after'])) if s['mate_after'] is not None else 'няма мат')}  [{tag}]")
        if e["mated"]:
            print(f"   мат на ход {e['mate_move']}; най-бързо мат на ход {e['earliest_mate_move']} (изгубени {e['lost_moves']} хода)")
        elif e["ended"]:
            print(f"   партията свърши (предаване/време), матът оставаше на дъската")
        else:
            print(f"   матът е пропуснат с {mv(e['missed']['move_no'], e['white'], e['missed']['played'])}, шанс след хода {e['missed']['chance_after']}%")
    if not out:
        print("Няма форсиран мат в партията.")
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if a.gifs:
        here = os.path.dirname(os.path.abspath(__file__))
        gid = g.headers.get("Link", "game").rstrip("/").split("/")[-1]
        flip = not me_white
        for e in out:
            if e["side"] != "me" or e.get("ended") or (e["mated"] and not e["lost_moves"]):
                continue
            base = os.path.join(a.gifs, f"mate-{gid}-{e['move_no']}")
            mvn = f"{e['move_no']}." if e["white"] else f"{e['move_no']}..."
            end = e["end_ply"] + 1 if e["mated"] else min(e["end_ply"] + 5, len(moves))  # missed: show what followed
            common = [sys.executable, os.path.join(here, "make_gif.py"), "--pgn", a.pgn, "--from-ply", str(e["ply"])] + (["--flip"] if flip else [])
            subprocess.run(common + ["--to-ply", str(end), "--out", base + "-played.gif", "--title", f"Изиграно от {mvn}"])
            subprocess.run(common + ["--line", " ".join(e["fastest"]), "--out", base + "-fastest.gif",
                                     "--title", f"Най-бързо: мат в {e['mate_in']}"])


if __name__ == "__main__":
    main()
