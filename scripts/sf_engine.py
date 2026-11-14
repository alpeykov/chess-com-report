"""Stockfish analysis for the report: one evaluation per position, move classes, accuracy, motifs, clock.

Stockfish is NOT part of this repository (GPLv3, ~100 MB). find_stockfish() looks for it in this order:
  --stockfish PATH, the STOCKFISH_PATH environment variable, `stockfish` on PATH, C:/projects/stockfish/**.
If it is missing, the skill falls back to the small material engine (engine.py).

Scales (same as lichess):
  win% = 50 + 50 * (2 / (1 + exp(-0.00368208 * cp)) - 1), mate = 100 / 0
  move class by the drop in the mover's win%: inaccuracy >= 10, mistake >= 20, blunder >= 30
  move accuracy = 103.1668 * exp(-0.04354 * drop) - 3.1669, clipped to 0..100
"""
import glob
import math
import os
import re
import shutil
import chess
import chess.engine
import chess.pgn

VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
CLASSES = [(30, "blunder"), (20, "mistake"), (10, "inaccuracy")]


def find_stockfish(path=None):
    cands = [path, os.environ.get("STOCKFISH_PATH"), shutil.which("stockfish"), shutil.which("stockfish.exe")]
    for pat in ("C:/projects/stockfish/**/stockfish*.exe", "/usr/games/stockfish", "/usr/local/bin/stockfish",
                "/opt/homebrew/bin/stockfish", os.path.expanduser("~/stockfish/**/stockfish*")):
        cands += sorted(glob.glob(pat, recursive=True))
    for c in cands:
        if c and os.path.isfile(c) and (os.access(c, os.X_OK) or c.lower().endswith(".exe")):
            return c
    return None


def win_pct(cp=None, mate=None):
    if mate is not None:
        return 100.0 if mate > 0 else 0.0
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def score_tuple(score):
    """(cp, mate) from White's point of view; cp is clipped to +-2000 for graphs."""
    w = score.white()
    if w.is_mate():
        return None, w.mate()
    return max(-2000, min(2000, w.score())), None


def move_accuracy(drop):
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * max(0.0, drop)) - 3.1669))


def classify(drop):
    for limit, name in CLASSES:
        if drop >= limit:
            return name
    return None


def open_engine(path, threads=1, hash_mb=32):
    eng = chess.engine.SimpleEngine.popen_uci(path)
    eng.configure({"Threads": threads, "Hash": hash_mb})
    return eng


def analyse_positions(eng, game, seconds=0.05, depth=None):
    """One analysis per position (start + after every ply). Each entry: wp (White's win %), cp / mate (White's
    point of view, None when not applicable), best (uci) and pv (uci list, up to 8 plies)."""
    lim = chess.engine.Limit(depth=depth) if depth else chess.engine.Limit(time=seconds)
    b, out = game.board(), []
    moves = list(game.mainline_moves())
    for i in range(len(moves) + 1):
        if b.is_checkmate():
            out.append({"wp": 0.0 if b.turn == chess.WHITE else 100.0, "cp": None, "mate": 0, "best": None, "pv": []})
        elif b.is_game_over():
            out.append({"wp": 50.0, "cp": 0, "mate": None, "best": None, "pv": []})
        else:
            info = eng.analyse(b, lim)
            cp, mate = score_tuple(info["score"])
            pv = [m.uci() for m in info.get("pv", [])[:8]]
            out.append({"wp": round(win_pct(cp, mate), 1), "cp": cp, "mate": mate, "best": pv[0] if pv else None, "pv": pv})
        if i < len(moves):
            b.push(moves[i])
    return out


def move_records(game, evals, me):
    """Per ply: who moved, the drop in the mover's win %, class, accuracy, best move and line, phase, clock."""
    color = chess.WHITE if game.headers.get("White", "").lower() == me else chess.BLACK
    clk = clocks(game)
    base, inc = base_seconds(game)
    b, recs = game.board(), []
    moves = list(game.mainline_moves())
    for i, mv in enumerate(moves):
        w0, w1 = evals[i]["wp"], evals[i + 1]["wp"]
        mover = b.turn
        before, after = (w0, w1) if mover == chess.WHITE else (100 - w0, 100 - w1)
        drop = max(0.0, before - after)
        prev_clk = clk[i - 2] if i >= 2 else (base if base else None)
        spent = round(prev_clk - clk[i] + inc, 1) if (prev_clk is not None and i < len(clk) and clk[i] is not None) else None
        best = evals[i]["best"]
        rec = {"ply": i, "san": b.san(mv), "uci": mv.uci(), "mine": mover == color, "side": "white" if mover == chess.WHITE else "black",
               "move_no": b.fullmove_number, "before": round(before, 1), "after": round(after, 1), "drop": round(drop, 1),
               "class": classify(drop), "acc": round(move_accuracy(drop), 1), "phase": phase(b),
               "best": b.san(chess.Move.from_uci(best)) if best and best != mv.uci() else None,
               "clock": clk[i] if i < len(clk) else None, "spent": spent, "fen": b.fen()}
        if rec["class"] or (evals[i]["mate"] is not None and (evals[i]["mate"] > 0) == (mover == chess.WHITE) and rec["best"]):
            if best:
                line = b.copy()
                rec["line"] = line.variation_san([chess.Move.from_uci(u) for u in evals[i]["pv"]])
                rec["motifs_missed"] = line_motifs(b, evals[i]["pv"])
            after_b = b.copy(); after_b.push(mv)
            reply = evals[i + 1]["pv"]
            if reply:
                rec["after_line"] = after_b.variation_san([chess.Move.from_uci(u) for u in reply])
                rec["motifs_allowed"] = line_motifs(after_b, reply)
            m0 = evals[i]["mate"]
            if m0 is not None and (m0 > 0) == (mover == chess.WHITE) and abs(m0) <= 3:
                rec["missed_mate_in"] = abs(m0) if rec["best"] else None
            m1 = evals[i + 1]["mate"]
            if m1 is not None and (m1 > 0) != (mover == chess.WHITE) and abs(m1) <= 3 and m1 != 0:
                rec["allowed_mate_in"] = abs(m1)
        recs.append(rec)
        b.push(mv)
    return recs


def game_accuracy(recs, mine=True):
    """Lichess-style: the mean of the arithmetic and harmonic means of the move accuracies."""
    a = [r["acc"] for r in recs if r["mine"] == mine]
    if not a:
        return None
    arith = sum(a) / len(a)
    harm = len(a) / sum(1 / max(x, 1.0) for x in a)
    return round((arith + harm) / 2, 1)


def clocks(game):
    """Seconds left after each ply from %clk comments (None when missing)."""
    out = []
    for node in game.mainline():
        m = re.search(r"\[%clk (\d+):(\d+):(\d+(?:\.\d+)?)\]", node.comment or "")
        out.append(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None)
    return out


def base_seconds(game):
    tc = game.headers.get("TimeControl", "")
    m = re.match(r"^(\d+)(?:\+(\d+))?$", tc)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (None, 0)


def phase(board):
    """opening / middlegame / endgame from the move number and the pieces left."""
    nonpawn = sum(VAL[p.piece_type] for p in board.piece_map().values() if p.piece_type not in (chess.PAWN, chess.KING))
    if nonpawn <= 26:
        return "endgame"
    return "opening" if board.fullmove_number <= 10 else "middlegame"


# ---------------- tactical motifs ----------------
def _attacked_targets(board, sq, color):
    """Enemy pieces worth something that the piece on sq attacks (king counts as 100)."""
    res = []
    for t in board.attacks(sq):
        p = board.piece_at(t)
        if p and p.color != color:
            res.append((100 if p.piece_type == chess.KING else VAL[p.piece_type], t, p))
    return res


def motif(board, move):
    """The tactical idea of `move` played in `board` (a list of tags): mate, back-rank mate, fork, discovered attack,
    pin, skewer, hanging piece, promotion."""
    tags = []
    mover = board.turn
    piece = board.piece_at(move.from_square)
    captured = board.piece_at(move.to_square)
    if captured and not board.is_attacked_by(not mover, move.to_square):
        tags.append("hanging")
    b = board.copy()
    b.push(move)
    if b.is_checkmate():
        k = b.king(not mover)
        back = 0 if (not mover) == chess.WHITE else 7
        tags.append("back_rank_mate" if chess.square_rank(k) == back else "mate")
        return tags
    if move.promotion:
        tags.append("promotion")
    # fork: the moved piece attacks two valuable targets (or the king and one more)
    tg = [t for t in _attacked_targets(b, move.to_square, mover) if t[0] >= 3]
    if len(tg) >= 2 and (any(v == 100 for v, _, _ in tg) or sum(1 for v, _, _ in tg if v >= VAL[piece.piece_type]) >= 2
                         or piece.piece_type in (chess.KNIGHT, chess.PAWN)):
        tags.append("fork")
    # discovered attack: another of our sliders now attacks something valuable through the vacated square
    for sq in b.pieces(chess.BISHOP, mover) | b.pieces(chess.ROOK, mover) | b.pieces(chess.QUEEN, mover):
        if sq == move.to_square:
            continue
        before = {t for v, t, _ in _attacked_targets(board, sq, mover) if v >= 5}
        after = {t for v, t, _ in _attacked_targets(b, sq, mover) if v >= 5}
        if after - before and move.from_square in chess.SquareSet(chess.between(sq, next(iter(after - before)))):
            tags.append("discovered")
            break
    # pin / skewer: the moved slider attacks an enemy piece with a second enemy piece right behind it on the same line
    if piece.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        for v, t, p in _attacked_targets(b, move.to_square, mover):
            for s in chess.SquareSet(chess.ray(move.to_square, t)):
                if s in (t, move.to_square) or t not in chess.SquareSet(chess.between(move.to_square, s)):
                    continue  # only squares beyond t, seen from the slider
                if any(b.piece_at(x) for x in chess.SquareSet(chess.between(t, s))):
                    continue  # something between t and s
                q = b.piece_at(s)
                if q is None or q.color == mover:
                    continue
                vq = 100 if q.piece_type == chess.KING else VAL[q.piece_type]
                if vq > v >= 3 or (vq == 100 and v >= 3):
                    tags.append("pin")
                elif v > vq >= 3 or (v == 100 and vq >= 5):
                    tags.append("skewer")
    return sorted(set(tags))


def line_motifs(board, uci_line, plies=3):
    """Motifs along the first plies of a line (the side to move's ideas only)."""
    b, tags = board.copy(), []
    me = b.turn
    for k, u in enumerate(uci_line[:plies]):
        m = chess.Move.from_uci(u)
        if m not in b.legal_moves:
            break
        if b.turn == me:
            tags += motif(b, m)
        b.push(m)
    return sorted(set(tags))


def lichess_link(fen, color):
    return "https://lichess.org/analysis/standard/" + fen.replace(" ", "_") + "?color=" + ("white" if color == chess.WHITE else "black")
