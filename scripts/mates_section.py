"""The "Mates" block of a game page, from mate_check.py's output.

    ensure(folder, username)          run mate_check.py for an archived game (mate_check.json in the folder)
    add_to_spec(spec, folder, pgn)    put the block into game_analysis.html of every language, right after the
                                      table of the player's mistakes (the first table), with step-through boards for the played and the fastest line
"""
import json
import pathlib
import subprocess
import sys

import chess
import chess.pgn

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

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
    "ended": dict(bg="Партията свърши (противникът се предаде или изтече времето), докато матът беше на дъската.",
                  en="The game ended (the opponent resigned or ran out of time) with the mate still on the board.",
                  fr="La partie s'est terminée (abandon ou temps) alors que le mat était encore sur l'échiquier."),
    "opp_ended": dict(bg="Противникът имаше {n} срещу вас, когато партията свърши.", en="The opponent had {n} against you when the game ended.",
                      fr="L'adversaire avait un {n} contre vous à la fin de la partie."),
    "v_played": dict(bg="Ход {m} · изиграно", en="Move {m} · played", fr="Coup {m} · joué"),
    "v_fast": dict(bg="Ход {m} · най-бързият мат", en="Move {m} · the fastest mate", fr="Coup {m} · le mat le plus rapide"),
    "n_start": dict(bg="Мат в {n}. Местете ходовете напред и назад.", en="Mate in {n}. Step the moves forward and back.",
                    fr="Mat en {n}. Avancez et reculez dans les coups."),
    "n_mate": dict(bg="Мат.", en="Mate.", fr="Mat."),
    "n_missed": dict(bg="Тук матът беше пропуснат.", en="The mate was missed here.", fr="Le mat a été manqué ici."),
    "end": dict(bg=" – мат", en=" – mate", fr=" – mat"),
}


def ensure(folder, username):
    """mate_check.json for an archived game; returns True when it had to run."""
    folder = pathlib.Path(folder)
    if (folder / "mate_check.json").exists():
        return False
    r = subprocess.run([sys.executable, str(HERE / "mate_check.py"), username, "--pgn", str(folder / "game.pgn"),
                        "--out", str(folder / "mate_check.json")],
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


def _san(board, move):
    """'37...Rab8' – plain SAN with the move number (the builder adds the piece names to SAN in the text)."""
    n = board.fullmove_number
    return (f"{n}." if board.turn == chess.WHITE else f"{n}...") + board.san(move)


def _line(start, sans, lg):
    """The fastest line in SAN with move numbers."""
    b = start.copy(); out = []
    for i, s in enumerate(sans):
        m = b.parse_san(s)
        out.append(_san(b, m) if (i == 0 or b.turn == chess.WHITE) else s)
        b.push(m)
    return " ".join(out) + (TX["end"][lg] if b.is_checkmate() else "")


def block(folder, pgn, lg, viewers=None):
    folder = pathlib.Path(folder)
    eps = json.loads((folder / "mate_check.json").read_text(encoding="utf-8"))
    g = chess.pgn.read_game(open(pgn, encoding="utf-8"))
    moves = list(g.mainline_moves())
    h = f'<h3>{TX["head"][lg]}</h3>'
    if not eps:
        return h + f'<p class="hint">{TX["none"][lg]}</p>'
    me = None
    rows, boards = [], []
    sans, b0 = [], g.board()
    for m in moves:
        sans.append(b0.san(m)); b0.push(m)
    for e in eps:
        start = _board_at(moves, e["ply"])
        if me is None:
            me = start.turn if e["side"] == "me" else not start.turn
        mvno = f'{e["move_no"]}.' if e["white"] else f'{e["move_no"]}...'
        fastest = _line(start, e["fastest"], lg)
        if e["side"] == "me":
            if e.get("ended"):
                what = TX["ended"][lg]
            elif e["mated"] and not e["lost_moves"]:
                what = TX["fast"][lg].format(m=e["mate_move"])
            elif e["mated"]:
                what = TX["slow"][lg].format(m=e["mate_move"], e=e["earliest_mate_move"], k=e["lost_moves"])
            else:
                ms = e["missed"]
                b = _board_at(moves, ms["ply"]); mv = _san(b, moves[ms["ply"]])
                b.push(moves[ms["ply"]])
                what = TX["missed"][lg].format(mv=mv, ch=ms["chance_after"], mat=_material(b, me))
        else:
            if e.get("ended"):
                what = TX["opp_ended"][lg].format(n=TX["matein"][lg].format(n=e["mate_in"]))
            elif e["mated"]:
                what = TX["opp_mated"][lg].format(m=e["mate_move"])
            else:
                ms = e["missed"]; b = _board_at(moves, ms["ply"])
                what = TX["opp_missed"][lg].format(n=TX["matein"][lg].format(n=e["mate_in"]),
                                                   mv=_san(b, moves[ms["ply"]]))
        if e["side"] != "me":
            cls = "n"
        elif e.get("ended") or (e["mated"] and not e["lost_moves"]):
            cls = "w"
        else:
            cls = "n" if e["mated"] else "l"
        rows.append(f'<tr><td class="num">{mvno}</td><td><span class="tag {cls}">{TX["matein"][lg].format(n=e["mate_in"])}</span></td>'
                    f'<td>{what}</td><td>{fastest}</td></tr>')
        if e["side"] == "me" and not e.get("ended") and not (e["mated"] and not e["lost_moves"]) and viewers is not None:
            vp, vf = f'mate-{e["move_no"]}-played', f'mate-{e["move_no"]}-fastest'
            orient = "white" if me == chess.WHITE else "black"
            end = e["end_ply"] + 1 if e["mated"] else min(e["end_ply"] + 5, len(moves))
            start_note = {k: TX["n_start"][k].format(n=e["mate_in"]) for k in TX["n_start"]}
            notes_p = {str(e["ply"]): start_note}
            if e["mated"]:
                notes_p[str(end)] = dict(TX["n_mate"])
            else:
                notes_p[str(e["missed"]["ply"] + 1)] = dict(TX["n_missed"])
            viewers[vp] = {"moves": " ".join(sans[:end]), "orientation": orient, "from_ply": e["ply"], "to_ply": end,
                           "title": {k: TX["v_played"][k].format(m=mvno) for k in TX["v_played"]}, "notes": notes_p}
            fl = sans[:e["ply"]] + e["fastest"]
            viewers[vf] = {"moves": " ".join(fl), "orientation": orient, "from_ply": e["ply"],
                           "title": {k: TX["v_fast"][k].format(m=mvno) for k in TX["v_fast"]},
                           "notes": {str(e["ply"]): start_note, str(len(fl)): dict(TX["n_mate"])}}
            boards.append(f"{{{{V:{vp}}}}}{{{{V:{vf}}}}}")
    c = TX["cols"][lg]
    return (h + f'<p class="hint">{TX["intro"][lg]}</p>'
            + '<div class="scroll"><table><tr>' + "".join(f"<th>{x}</th>" for x in c) + "</tr>" + "".join(rows) + "</table></div>"
            + "".join(boards))


def add_to_spec(spec, folder, pgn):
    ga = spec.get("game_analysis") or {}
    if not isinstance(ga.get("html"), dict) or not (pathlib.Path(folder) / "mate_check.json").exists():
        return
    viewers = {}
    for lg, text in list(ga["html"].items()):
        if lg not in TX["head"] or f'<h3>{TX["head"][lg]}</h3>' in text:
            continue
        i = text.find("</table>")
        i = len(text) if i < 0 else i + len("</table>")
        if text[i:].startswith("</div>"):  # the table's scroll wrapper
            i += len("</div>")
        ga["html"][lg] = text[:i] + block(folder, pgn, lg, viewers) + text[i:]
    if viewers:
        spec["viewers"] = dict(spec.get("viewers") or {}, **viewers)
