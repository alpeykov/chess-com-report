"""Make an animated GIF of a line of moves.

Starts from a position of a game PGN (after --from-ply half-moves) or a FEN, then
plays --line (SAN, space separated) or, without --line, the game's own moves up to
--to-ply. Each frame shows the board, the last move highlighted and a caption with
the move written as a piece name plus SAN (e.g. "72. Царица c5 (Qc5)").

  python make_gif.py --pgn data/last.pgn --from-ply 141 --out played.gif --title "Изиграно"
  python make_gif.py --pgn data/last.pgn --from-ply 142 --line "Qc5 Ke8 Kf6 Kd7" --out best.gif
"""
import argparse, os, sys
import chess, chess.pgn
from PIL import Image, ImageDraw, ImageFont

NAMES = {
    "bg": dict(K="Цар", Q="Царица", R="Топ", B="Офицер", N="Кон", pawn="пешка", takes="взима", mate="мат", check="шах",
               short="рокада", long="дълга рокада", white="белите", black="черните", start="Начална позиция"),
    "en": dict(K="King", Q="Queen", R="Rook", B="Bishop", N="Knight", pawn="pawn", takes="takes", mate="mate", check="check",
               short="castles", long="castles long", white="White", black="Black", start="Starting position"),
}
LIGHT, DARK = (240, 217, 181), (181, 136, 99)
HL_LIGHT, HL_DARK = (205, 210, 106), (170, 162, 58)
GLYPH = {"K": "\u2654", "Q": "\u2655", "R": "\u2656", "B": "\u2657", "N": "\u2658", "P": "\u2659"}


def font(names, size):
    for n in names:
        for d in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "/System/Library/Fonts"):
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def describe(board, move, lang):
    """Piece name + SAN, e.g. 'Царица взима c5+ (Qxc5+)'. board is BEFORE the move."""
    L = NAMES[lang]
    san = board.san(move)
    num = board.fullmove_number
    prefix = f"{num}." if board.turn == chess.WHITE else f"{num}..."
    if board.is_castling(move):
        words = L["long"] if board.is_queenside_castling(move) else L["short"]
    else:
        p = board.piece_at(move.from_square)
        sq = chess.square_name(move.to_square)
        if p.piece_type == chess.PAWN:
            words = (f"{L['pawn']} {L['takes']} {sq}" if board.is_capture(move) else f"{L['pawn']} {sq}")
            if move.promotion:
                words += f" = {L[chess.piece_symbol(move.promotion).upper()]}"
        else:
            name = L[p.symbol().upper()]
            words = f"{name} {L['takes']} {sq}" if board.is_capture(move) else f"{name} {sq}"
    b2 = board.copy(); b2.push(move)
    if b2.is_checkmate():
        words += f" – {L['mate']}"
    return f"{prefix} {words} ({san})"


def draw(board, last, caption, title, flip, sq=64):
    pad, top, bottom = 24, 64 if title else 34, 52
    W = sq * 8 + 2 * pad
    H = sq * 8 + top + bottom
    img = Image.new("RGB", (W, H), (38, 36, 33))
    d = ImageDraw.Draw(img)
    fpiece = font(["seguisym.ttf", "DejaVuSans.ttf", "Apple Symbols.ttf"], int(sq * 0.86))
    fcap = font(["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"], 22)
    ftitle = font(["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"], 22)
    fcoord = font(["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"], 13)
    if title:
        d.text((W / 2, 20), title, font=ftitle, fill=(240, 240, 240), anchor="mm")
    y0 = top
    hl = {last.from_square, last.to_square} if last else set()
    for r in range(8):
        for f in range(8):
            file_, rank = (7 - f, r) if flip else (f, 7 - r)
            s = chess.square(file_, rank)
            light = (file_ + rank) % 2 == 1
            col = (HL_LIGHT if light else HL_DARK) if s in hl else (LIGHT if light else DARK)
            x, y = pad + f * sq, y0 + r * sq
            d.rectangle([x, y, x + sq - 1, y + sq - 1], fill=col)
            p = board.piece_at(s)
            if p:
                g = GLYPH[p.symbol().upper()]
                cx, cy = x + sq / 2, y + sq / 2 + 2
                if p.color == chess.WHITE:
                    # white piece: filled glyph in white with a dark outline
                    d.text((cx, cy), "\u265a\u265b\u265c\u265d\u265e\u265f"["KQRBNP".index(p.symbol().upper())],
                           font=fpiece, fill=(255, 255, 255), anchor="mm", stroke_width=2, stroke_fill=(30, 30, 30))
                else:
                    d.text((cx, cy), "\u265a\u265b\u265c\u265d\u265e\u265f"["KQRBNP".index(p.symbol().upper())],
                           font=fpiece, fill=(20, 20, 20), anchor="mm", stroke_width=1, stroke_fill=(20, 20, 20))
            if board.is_check() and p and p.piece_type == chess.KING and p.color == board.turn:
                d.rectangle([x, y, x + sq - 1, y + sq - 1], outline=(220, 40, 40), width=4)
    for i in range(8):
        fl = "abcdefgh"[7 - i if flip else i]
        rk = str(i + 1 if flip else 8 - i)
        d.text((pad + i * sq + sq / 2, y0 + 8 * sq + 9), fl, font=fcoord, fill=(200, 200, 200), anchor="mm")
        d.text((pad / 2, y0 + i * sq + sq / 2), rk, font=fcoord, fill=(200, 200, 200), anchor="mm")
    d.text((W / 2, y0 + 8 * sq + 34), caption, font=fcap, fill=(255, 255, 255), anchor="mm")
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn"); ap.add_argument("--fen")
    ap.add_argument("--from-ply", type=int, default=0, help="start after this many half-moves of the PGN")
    ap.add_argument("--to-ply", type=int, help="without --line: play the game's moves up to this ply")
    ap.add_argument("--line", help="SAN moves to play from the start position")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--lang", default="bg", choices=list(NAMES))
    ap.add_argument("--flip", action="store_true", help="board from Black's side")
    ap.add_argument("--ms", type=int, default=1200, help="ms per frame")
    ap.add_argument("--hold", type=int, default=3500, help="ms on the last frame")
    a = ap.parse_args()

    game_moves = []
    if a.pgn:
        g = chess.pgn.read_game(open(a.pgn, encoding="utf-8"))
        board = g.board(); game_moves = list(g.mainline_moves())
        for m in game_moves[:a.from_ply]:
            board.push(m)
    else:
        board = chess.Board(a.fen) if a.fen else chess.Board()
    if a.line:
        moves = []
        b = board.copy()
        for s in a.line.split():
            m = b.parse_san(s); moves.append(m); b.push(m)
    else:
        moves = game_moves[a.from_ply:a.to_ply]

    L = NAMES[a.lang]
    frames, last = [], None
    side = L["white"] if board.turn == chess.WHITE else L["black"]
    frames.append(draw(board, None, f"{L['start']} – {side}", a.title, a.flip))
    for m in moves:
        cap = describe(board, m, a.lang)
        board.push(m)
        frames.append(draw(board, m, cap, a.title, a.flip))
    durations = [a.ms * 2] + [a.ms] * (len(frames) - 2) + [a.hold]
    frames[0].save(a.out, save_all=True, append_images=frames[1:], duration=durations[:len(frames)], loop=0, optimize=True)
    print(f"{a.out}: {len(frames)} frames")


if __name__ == "__main__":
    sys.exit(main())
