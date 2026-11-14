"""Small material-only search: alpha-beta + quiescence. Finds hanging pieces, forks and short mates
reliably; it is NOT a full engine (no positional judgement, weak in pawn endings)."""
import chess

VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
MATE = 1000


def material(board):
    """Material balance from the side to move's point of view."""
    s = 0
    for p, v in VAL.items():
        s += v * (len(board.pieces(p, chess.WHITE)) - len(board.pieces(p, chess.BLACK)))
    return s if board.turn == chess.WHITE else -s


def material_for(board, color):
    s = sum(VAL[p.piece_type] * (1 if p.color == color else -1) for p in board.piece_map().values())
    return s


def ordered(board, moves):
    def key(m):
        victim = board.piece_type_at(m.to_square) or (chess.PAWN if board.is_en_passant(m) else 0)
        return -(10 * VAL.get(victim, 0) + (9 if m.promotion else 0) + (5 if board.gives_check(m) else 0)
                 - VAL[board.piece_type_at(m.from_square)] / 10)
    return sorted(moves, key=key)


def qsearch(board, alpha, beta, ply):
    if board.is_checkmate():
        return -MATE + ply
    if board.is_check():
        moves, stand = list(board.legal_moves), None
    else:
        stand = material(board)
        if stand >= beta:
            return stand
        alpha = max(alpha, stand)
        moves = [m for m in board.legal_moves if board.is_capture(m) or m.promotion]
        if ply > 12:
            return stand
    if not moves:
        return stand if stand is not None else 0
    for m in ordered(board, moves):
        board.push(m)
        score = -qsearch(board, -beta, -alpha, ply + 1)
        board.pop()
        if score >= beta:
            return score
        alpha = max(alpha, score)
    return alpha


def search(board, depth, alpha=-MATE - 1, beta=MATE + 1, ply=0):
    if board.is_checkmate():
        return -MATE + ply
    if board.is_stalemate() or board.is_insufficient_material():
        return 0
    if depth == 0:
        return qsearch(board, alpha, beta, ply)
    for m in ordered(board, list(board.legal_moves)):
        board.push(m)
        score = -search(board, depth - 1, -beta, -alpha, ply + 1)
        board.pop()
        if score >= beta:
            return score
        alpha = max(alpha, score)
    return alpha


def best_and_played(board, played, depth=3):
    """(best score, best move, score after the played move), all from the mover's point of view."""
    board.push(played)
    played_score = -search(board, depth - 1, -MATE - 1, MATE + 1, 1)
    board.pop()
    best_score, best_move = played_score, played
    for m in ordered(board, list(board.legal_moves)):
        if m == played:
            continue
        board.push(m)
        score = -search(board, depth - 1, -MATE - 1, -best_score, 1)
        board.pop()
        if score > best_score:
            best_score, best_move = score, m
    return best_score, best_move, played_score


def pv(board, depth):
    """Principal line (SAN list) of the given depth from this position."""
    line, b = [], board.copy()
    for d in range(depth, 0, -1):
        if b.is_game_over():
            break
        best, bm = -MATE - 1, None
        for m in ordered(b, list(b.legal_moves)):
            b.push(m)
            s = -search(b, d - 1, -MATE - 1, -best, 1)
            b.pop()
            if s > best:
                best, bm = s, m
        line.append(b.san(bm))
        b.push(bm)
    return line
