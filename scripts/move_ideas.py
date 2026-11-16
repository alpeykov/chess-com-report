"""Why one opening move is better than another: plain facts from the board plus a Stockfish check.

    import move_ideas
    f = move_ideas.facts(board, "c4")                 # what the move does on the board
    e = move_ideas.engine(eng, board, "c4", depth=18)  # win % for the side that moves, main line, pawn given / won back
    move_ideas.describe(dict(f, **e), lang)           # one sentence of clauses, "" when there is nothing to say

facts():
  attacks   enemy pieces the move newly attacks that are worth it (undefended, or worth at least the attacker)
  centre    central squares in the opponent's half the move newly controls (d5/e5 for White, d4/e4 for Black)
  develops  a knight or bishop leaves its first rank
  castles   the move castles
  opens     own bishops still on their first rank that gain at least 2 squares
  blocks    own bishops on their first rank whose diagonal the moved piece now cuts (a pawn still on its starting
            square is not counted as a block, because it is expected to move)
  offers    the moved piece can be taken (undefended, or by a cheaper piece): a gambit
"""
import chess
import chess.engine

import sf_engine

VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
NAMES = {  # the piece as an object of the sentence
    "bg": {chess.PAWN: "пешката", chess.KNIGHT: "Коня", chess.BISHOP: "Офицера", chess.ROOK: "Топа", chess.QUEEN: "Царицата", chess.KING: "Царя"},
    "en": {chess.PAWN: "the pawn", chess.KNIGHT: "the knight", chess.BISHOP: "the bishop", chess.ROOK: "the rook", chess.QUEEN: "the queen", chess.KING: "the king"},
    "fr": {chess.PAWN: "le pion", chess.KNIGHT: "le cavalier", chess.BISHOP: "le fou", chess.ROOK: "la tour", chess.QUEEN: "la dame", chess.KING: "le roi"},
}
ON = {"bg": " на ", "en": " on ", "fr": " en "}


def _start_pawn(board, sq):
    p = board.piece_at(sq)
    return p and p.piece_type == chess.PAWN and chess.square_rank(sq) == (1 if p.color else 6)


def _reach(board, sq):
    """Squares a bishop / rook on sq could use, looking through own pawns that have not moved yet."""
    p = board.piece_at(sq)
    dirs = {chess.BISHOP: ((1, 1), (1, -1), (-1, 1), (-1, -1)), chess.ROOK: ((1, 0), (-1, 0), (0, 1), (0, -1))}[p.piece_type]
    n = 0
    for df, dr in dirs:
        f, r = chess.square_file(sq) + df, chess.square_rank(sq) + dr
        while 0 <= f < 8 and 0 <= r < 8:
            s = chess.square(f, r)
            q = board.piece_at(s)
            n += 1
            if q and not (q.color == p.color and _start_pawn(board, s)):
                break
            f, r = f + df, r + dr
    return n


def facts(board, san):
    mv = board.parse_san(san)
    me, pc = board.turn, board.piece_at(mv.from_square)
    after = board.copy()
    after.push(mv)
    back = 0 if me else 7
    f = {"san": san, "piece": pc.piece_type, "to": chess.square_name(mv.to_square), "castles": board.is_castling(mv),
         "develops": pc.piece_type in (chess.KNIGHT, chess.BISHOP) and chess.square_rank(mv.from_square) == back,
         "attacks": [], "centre": [], "opens": [], "blocks": [], "offers": False}
    for sq, q in after.piece_map().items():
        if q.color == me or q.piece_type == chess.KING:
            continue
        new = after.attackers(me, sq) - board.attackers(me, sq)
        if not new:
            continue
        low = min(VAL[after.piece_at(a).piece_type] for a in new)
        defended = bool(after.attackers(not me, sq))
        if not defended or VAL[q.piece_type] >= low:
            f["attacks"].append({"piece": q.piece_type, "sq": chess.square_name(sq), "defended": defended})
    for name in (("d5", "e5") if me else ("d4", "e4")):
        sq = chess.parse_square(name)
        if any(a["sq"] == name for a in f["attacks"]):
            continue  # "attacks the pawn on d5" already says it
        if after.attackers(me, sq) - board.attackers(me, sq) or (mv.to_square == sq and pc.piece_type == chess.PAWN):
            f["centre"].append(name)
    for sq, q in board.piece_map().items():
        if q.color != me or sq == mv.from_square or q.piece_type != chess.BISHOP or chess.square_rank(sq) != back:
            continue
        gain = len(after.attacks(sq)) - len(board.attacks(sq))
        if gain >= 2:
            f["opens"].append({"piece": q.piece_type, "sq": chess.square_name(sq)})
        elif (q.piece_type == chess.BISHOP and chess.square_distance(sq, mv.to_square) <= 2
              and _reach(board, sq) - _reach(after, sq) >= 2):  # a pawn right in front of it, not one far down the diagonal
            f["blocks"].append({"piece": q.piece_type, "sq": chess.square_name(sq)})
    takers = after.attackers(not me, mv.to_square)
    if takers and not board.is_castling(mv):
        cheap = min(VAL[after.piece_at(a).piece_type] for a in takers)
        f["offers"] = not after.attackers(me, mv.to_square) or cheap < VAL[pc.piece_type]
    return f


def _material(board, colour):
    return sum(VAL[p.piece_type] * (1 if p.color == colour else -1) for p in board.piece_map().values())


def _line(eng, board, depth, plies):
    info = eng.analyse(board, chess.engine.Limit(depth=depth))
    b, line = board.copy(), []
    for m in info.get("pv", [])[:plies]:
        line.append(b.san(m))
        b.push(m)
    return info["score"], line, b


def engine(eng, board, san, depth=18, plies=6, offers=False):
    """Stockfish after the move: win % for the side that played it and the main line (SAN). For a move that
    offers a piece, also the line after the opponent takes it ("take": capture + reply) and whether the piece
    comes back within it ("back")."""
    me = board.turn
    after = board.copy()
    mv = after.push_san(san)
    s, line, _ = _line(eng, after, depth, plies)
    s = s.pov(me)
    wp = sf_engine.win_pct(s.score(), None) if not s.is_mate() else (100.0 if s.mate() > 0 else 0.0)
    out = {"wp": round(wp, 1), "pv": line}
    if offers:
        caps = [m for m in after.legal_moves if m.to_square == mv.to_square]
        if caps:
            cap = min(caps, key=lambda m: VAL[after.piece_at(m.from_square).piece_type])
            took = after.copy()
            take = took.san(cap)
            took.push(cap)
            _, reply, _ = _line(eng, took, depth, 10)
            # the line up to the move that brings the material back, if it does within it
            b, back = took.copy(), False
            for i, r in enumerate(reply):
                m = b.parse_san(r)
                again = b.turn == me and m.to_square == mv.to_square and b.is_capture(m)  # takes back on that square
                b.push(m)
                if again or _material(b, me) >= _material(board, me):
                    reply, back = reply[:i + 1], True
                    break
            out.update(take=[take] + (reply if back else reply[:plies - 1]), back=back)
    return out


def ideas(board, sans, eng=None, depth=18):
    """{san: facts (+ engine when eng is given)} for every move in sans."""
    out = {}
    for s in sans:
        f = facts(board, s)
        if eng:
            f.update(engine(eng, board, s, depth, offers=f["offers"]))
        out[s] = f
    return out


def _obj(lang, piece, sq):
    return f"{NAMES[lang][piece]}{ON[lang]}{sq}"


def clauses(f, lang, ply=None):
    """What the move does, as short clauses in lang (bg/en/fr); ply (the move's half-move index) numbers the
    gambit line."""
    c = []
    for a in f["attacks"]:
        loose, p, sq = not a["defended"], a["piece"], a["sq"]
        if lang == "bg":
            what = _obj("bg", p, sq)
            if loose:
                what = f"незащитената пешка на {sq}" if p == chess.PAWN else f"незащитената фигура {what}"
            c.append("напада " + what)
        elif lang == "en":
            c.append("attacks " + (f"the undefended {_obj('en', p, sq)[4:]}" if loose else _obj("en", p, sq)))
        else:
            fem = p in (chess.ROOK, chess.QUEEN)
            c.append("attaque " + _obj("fr", p, sq) + ((" non défendue" if fem else " non défendu") if loose else ""))
    if f["centre"]:
        sq = ", ".join(f["centre"])
        c.append({"bg": f"бори се за центъра ({sq})", "en": f"fights for the centre ({sq})", "fr": f"lutte pour le centre ({sq})"}[lang])
    if f["castles"]:
        c.append({"bg": "скрива Царя с рокада", "en": "tucks the king away", "fr": "met le roi à l'abri"}[lang])
    elif f["develops"]:
        c.append({"bg": "развива ", "en": "develops ", "fr": "développe "}[lang] + NAMES[lang][f["piece"]])
    for o in f["opens"]:
        c.append({"bg": "открива ", "en": "opens ", "fr": "libère "}[lang] + _obj(lang, o["piece"], o["sq"]))
    for o in f["blocks"]:
        w = _obj(lang, o["piece"], o["sq"])
        c.append({"bg": f"затваря {w} зад {NAMES['bg'][f['piece']]} на {f['to']}", "en": f"shuts in {w} behind {NAMES['en'][f['piece']]} on {f['to']}",
                  "fr": f"enferme {w} derrière {NAMES['fr'][f['piece']]} {f['to']}"}[lang])
    if f["offers"]:
        p = NAMES[lang][f["piece"]]
        if f.get("take") and f.get("back") and ply is not None:
            take = pv_txt(ply + 1, f["take"][:1])
            rest = pv_txt(ply + 2, f["take"][1:])
            c.append({"bg": f"предлага {p} на {f['to']}, но след {take} си я взима обратно ({rest})",
                      "en": f"offers {p} on {f['to']}, but after {take} wins it back ({rest})",
                      "fr": f"offre {p} {f['to']}, mais après {take} le reprend ({rest})"}[lang])
        else:
            c.append({"bg": f"предлага {p} на {f['to']}", "en": f"offers {p} on {f['to']}", "fr": f"offre {p} {f['to']}"}[lang])
    return c


def join(c, lang):
    if not c:
        return ""
    last = {"bg": " и ", "en": " and ", "fr": " et "}[lang]
    return c[0] if len(c) == 1 else ", ".join(c[:-1]) + last + c[-1]


def pv_txt(ply, sans):
    """Moves from half-move ply on: 2...dxc4 3.e3 b5."""
    out = []
    for i, s in enumerate(sans):
        p = ply + i
        out.append(f"{p // 2 + 1}.{s}" if p % 2 == 0 else (f"{p // 2 + 1}...{s}" if i == 0 else s))
    return " ".join(out)


def open_engine():
    path = sf_engine.find_stockfish()
    return sf_engine.open_engine(path, threads=2, hash_mb=64) if path else None
