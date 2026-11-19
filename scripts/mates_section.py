"""The "Mates" block of a game page, from mate_check.py's output.

    ensure(folder, username)          run mate_check.py for an archived game (mate_check.json + GIFs in the folder)
    add_to_spec(spec, folder, pgn)    put the block into game_analysis.html of every language, right after the
                                      table of the player's mistakes (the first table), GIFs inline as data URIs
"""
import base64
import json
import pathlib
import subprocess
import sys

import chess
import chess.pgn

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_gif import NAMES, describe  # noqa: E402

VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
TX = {
    "head": dict(bg="Матове", en="Mates", fr="Mats"),
    "none": dict(bg="Stockfish не намира форсиран мат в тази партия – за никоя от страните.",
                 en="Stockfish finds no forced mate in this game, for either side.",
                 fr="Stockfish ne trouve aucun mat forcé dans cette partie, d'aucun côté."),
    "intro": dict(bg="Всеки форсиран мат в партията (Stockfish): пропуснатите и по-бавните, с най-бързия вариант.",
                  en="Every forced mate in the game (Stockfish): missed and slower ones, with the fastest line.",
                  fr="Chaque mat forcé de la partie (Stockfish) : manqués et plus lents, avec la ligne la plus rapide."),
    "cols": dict(bg=("Ход", "Мат", "Какво стана", "Най-бързо"), en=("Move", "Mate", "What happened", "Fastest"),
                 fr=("Coup", "Mat", "Ce qui s'est passé", "Le plus rapide")),
    "matein": dict(bg="мат в {n}", en="mate in {n}", fr="mat en {n}"),
    "fast": dict(bg="Матирахте по най-бързия начин (ход {m}).", en="You mated the fastest way (move {m}).",
                 fr="Vous avez maté au plus vite (coup {m})."),
    "slow": dict(bg="<b>По-бавен мат:</b> мат на ход {m}, а най-бързият беше на ход {e} ({k} хода по-късно).",
                 en="<b>Slower mate:</b> mate on move {m}, the fastest was on move {e} ({k} moves later).",
                 fr="<b>Mat plus lent :</b> mat au coup {m}, le plus rapide était au coup {e} ({k} coups plus tard)."),
    "missed": dict(bg="<b>Пропуснат мат</b> с {mv}. След хода: шанс {ch}% за вас, фигури {mat}.",
                   en="<b>Missed mate</b> with {mv}. After the move: {ch}% for you, material {mat}.",
                   fr="<b>Mat manqué</b> avec {mv}. Après le coup : {ch} % pour vous, matériel {mat}."),
    "opp_missed": dict(bg="Противникът имаше {n} срещу вас и го пропусна с {mv}.",
                       en="The opponent had {n} against you and missed it with {mv}.",
                       fr="L'adversaire avait un {n} contre vous et l'a manqué avec {mv}."),
    "opp_mated": dict(bg="Противникът ви направи мат на ход {m}.", en="The opponent mated you on move {m}.",
                      fr="L'adversaire vous a maté au coup {m}."),
    "gif_played": dict(bg="Изиграно", en="Played", fr="Joué"),
    "gif_fast": dict(bg="Най-бързо", en="Fastest", fr="Le plus rapide"),
    "end": dict(bg=" – мат", en=" – mate", fr=" – mat"),
}


def ensure(folder, username):
    """mate_check.json (and the GIFs) for an archived game; returns True when it had to run."""
    folder = pathlib.Path(folder)
    if (folder / "mate_check.json").exists():
        return False
    r = subprocess.run([sys.executable, str(HERE / "mate_check.py"), username, "--pgn", str(folder / "game.pgn"),
                        "--out", str(folder / "mate_check.json"), "--gifs", str(folder)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(r.stdout + r.stderr)
    return True


def _board_at(moves, ply):
    b = chess.Board()
    for m in moves[:ply]:
        b.push(m)
    return b


def _material(board, me):
    s = sum(VAL.get(p.piece_type, 0) * (1 if p.color == me else -1) for p in board.piece_map().values())
    return f"{s:+d}" if s else "0"


def _line(start, sans, lg):
    """The fastest line: the first move as a piece name + SAN, then SAN with move numbers."""
    b = start.copy(); out = []
    for i, s in enumerate(sans):
        m = b.parse_san(s)
        if i == 0:
            out.append(describe(b, m, "en" if lg == "fr" else lg))
        else:
            n = b.fullmove_number
            out.append((f"{n}." if b.turn == chess.WHITE else (f"{n}..." if i == 0 else "")) + s)
        b.push(m)
    return " ".join(out) + (TX["end"][lg] if b.is_checkmate() else "")


def _gif(path):
    return "data:image/gif;base64," + base64.b64encode(pathlib.Path(path).read_bytes()).decode()


def block(folder, pgn, lg):
    folder = pathlib.Path(folder)
    eps = json.loads((folder / "mate_check.json").read_text(encoding="utf-8"))
    g = chess.pgn.read_game(open(pgn, encoding="utf-8"))
    moves = list(g.mainline_moves())
    gid = g.headers.get("Link", "game").rstrip("/").split("/")[-1]
    h = f'<h3>{TX["head"][lg]}</h3>'
    if not eps:
        return h + f'<p class="hint">{TX["none"][lg]}</p>'
    me = None
    rows, gifs = [], []
    for e in eps:
        start = _board_at(moves, e["ply"])
        if me is None:
            me = start.turn if e["side"] == "me" else not start.turn
        mvno = f'{e["move_no"]}.' if e["white"] else f'{e["move_no"]}...'
        fastest = _line(start, e["fastest"], lg)
        if e["side"] == "me":
            if e["mated"] and not e["lost_moves"]:
                what = TX["fast"][lg].format(m=e["mate_move"])
            elif e["mated"]:
                what = TX["slow"][lg].format(m=e["mate_move"], e=e["earliest_mate_move"], k=e["lost_moves"])
            else:
                ms = e["missed"]
                b = _board_at(moves, ms["ply"]); mv = describe(b, moves[ms["ply"]], "en" if lg == "fr" else lg)
                b.push(moves[ms["ply"]])
                what = TX["missed"][lg].format(mv=mv, ch=ms["chance_after"], mat=_material(b, me))
        else:
            if e["mated"]:
                what = TX["opp_mated"][lg].format(m=e["mate_move"])
            else:
                ms = e["missed"]; b = _board_at(moves, ms["ply"])
                what = TX["opp_missed"][lg].format(n=TX["matein"][lg].format(n=e["mate_in"]),
                                                   mv=describe(b, moves[ms["ply"]], "en" if lg == "fr" else lg))
        cls = ("w" if not e["lost_moves"] else "n") if e["side"] == "me" and e["mated"] else ("l" if e["side"] == "me" else "n")
        rows.append(f'<tr><td class="num">{mvno}</td><td><span class="tag {cls}">{TX["matein"][lg].format(n=e["mate_in"])}</span></td>'
                    f'<td>{what}</td><td>{fastest}</td></tr>')
        base = folder / f'mate-{gid}-{e["move_no"]}'
        if e["side"] == "me" and (base.with_name(base.name + "-played.gif")).exists():
            gifs.append(f'<figure class="mategif"><img alt="" src="{_gif(base.with_name(base.name + "-played.gif"))}">'
                        f'<figcaption>{mvno} {TX["gif_played"][lg]}</figcaption></figure>'
                        f'<figure class="mategif"><img alt="" src="{_gif(base.with_name(base.name + "-fastest.gif"))}">'
                        f'<figcaption>{mvno} {TX["gif_fast"][lg]}</figcaption></figure>')
    c = TX["cols"][lg]
    return (h + f'<p class="hint">{TX["intro"][lg]}</p>'
            + '<style>.mategifs{display:flex;flex-wrap:wrap;gap:12px;margin-top:10px}.mategif{margin:0;max-width:100%}'
              '.mategif img{max-width:100%;height:auto;border-radius:8px;display:block}.mategif figcaption{font-size:13px;color:var(--muted);margin-top:4px}</style>'
            + '<div class="scroll"><table><tr>' + "".join(f"<th>{x}</th>" for x in c) + "</tr>" + "".join(rows) + "</table></div>"
            + (f'<div class="mategifs">{"".join(gifs)}</div>' if gifs else ""))


def add_to_spec(spec, folder, pgn):
    ga = spec.get("game_analysis") or {}
    if not isinstance(ga.get("html"), dict) or not (pathlib.Path(folder) / "mate_check.json").exists():
        return
    for lg, text in list(ga["html"].items()):
        if lg not in TX["head"] or 'class="mategifs"' in text or f'<h3>{TX["head"][lg]}</h3>' in text:
            continue
        i = text.find("</table>")
        i = len(text) if i < 0 else i + len("</table>")
        if text[i:].startswith("</div>"):  # the table's scroll wrapper
            i += len("</div>")
        ga["html"][lg] = text[:i] + block(folder, pgn, lg) + text[i:]
