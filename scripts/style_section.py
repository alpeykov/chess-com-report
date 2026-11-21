"""Report section "Style change": compares the player's opening habits before and after a date.

Measures, per game, from the player's side (first 40 own moves):
  - castling: the move number and side, or none;
  - bishops: the move when both bishops have left their starting squares, bishop moves in the first 10 moves;
  - mistakes (Stockfish win-% drop >= 20) before move 20, and how many of them were played with the king still
    on its starting square (castling moves themselves not counted).
Every number comes from OUT/games.pgn, OUT/sf_games.json and OUT/sf_moves.json.

build(folder, username, since, before_from=None) -> (section dict, viewers dict)
"""
import json
import pathlib
import statistics as st

import chess
import chess.pgn

LANGS = ["bg", "en", "fr"]


def T(bg, en, fr):
    return {"bg": bg, "en": en, "fr": fr}


def J(*parts):
    return {lg: "".join(p[lg] if isinstance(p, dict) else str(p) for p in parts) for lg in LANGS}


def _games(folder, me):
    rows = []
    with open(folder / "games.pgn", encoding="utf-8") as f:
        while True:
            g = chess.pgn.read_game(f)
            if g is None:
                break
            h = g.headers
            white = h["White"].lower() == me
            col = chess.WHITE if white else chess.BLACK
            res = h["Result"]
            sc = 0.5 if res == "1/2-1/2" else (1 if (res == "1-0") == white else 0)
            b = g.board()
            castle = side = None
            bdev, b10, nmy = {}, 0, 0
            start = {chess.C1, chess.F1} if white else {chess.C8, chess.F8}
            for m in g.mainline_moves():
                if b.turn == col:
                    nmy += 1
                    p = b.piece_at(m.from_square)
                    if b.is_castling(m) and castle is None:
                        castle, side = nmy, ("O-O" if b.is_kingside_castling(m) else "O-O-O")
                    if p.piece_type == chess.BISHOP:
                        if m.from_square in start and m.from_square not in bdev:
                            bdev[m.from_square] = nmy
                        if nmy <= 10:
                            b10 += 1
                b.push(m)
                if nmy >= 40:
                    break
            rows.append(dict(date=h.get("UTCDate", h.get("Date")), white=white, sc=sc, castle=castle, side=side,
                             both=max(bdev.values()) if len(bdev) == 2 else None, b10=b10, link=h.get("Link"),
                             opp=h["Black"] if white else h["White"]))
    return rows


def _king_home(fen, white):
    b = chess.Board(fen)
    return b.king(chess.WHITE if white else chess.BLACK) == (chess.E1 if white else chess.E8)


def _stats(rs):
    n = len(rs)
    c = [r["castle"] for r in rs if r["castle"]]
    a = [r for r in rs if r.get("acc") is not None]
    return dict(
        n=n, score=round(100 * sum(r["sc"] for r in rs) / n, 1),
        c8=round(100 * sum(1 for x in c if x <= 8) / n), cmed=st.median(c) if c else None,
        never=round(100 * sum(1 for r in rs if not r["castle"]) / n),
        both10=round(100 * sum(1 for r in rs if r["both"] and r["both"] <= 10) / n),
        b10=round(st.mean(r["b10"] for r in rs), 1),
        acc=round(st.mean(r["acc"] for r in a), 1) if a else None,
        early=round(sum(r["early"] for r in a) / len(a), 2) if a else None,
        center=round(sum(r["center"] for r in a) / len(a), 2) if a else None)


def _fmt_med(x):
    return "–" if x is None else (str(int(x)) if float(x).is_integer() else f"{x:.1f}")


def _arrows(m):
    b = chess.Board(m["fen"])
    out = [[m["uci"][:2], m["uci"][2:4], "red"]]
    try:
        bm = b.parse_san(m["best"])
        out.append([chess.square_name(bm.from_square), chess.square_name(bm.to_square), "green"])
    except Exception:
        pass
    return out


def _rnd(x):
    return "–" if x is None else str(int(x + 0.5))


def _d(s):
    y, m, dd = s.split(".")
    return f"{dd}.{m}.{y}"


def build(folder, username, since, before_from=None, examples=3):
    folder = pathlib.Path(folder)
    me = username.lower()
    rows = _games(folder, me)
    sg = {g["link"]: g for g in json.loads((folder / "sf_games.json").read_text(encoding="utf-8"))}
    sm = json.loads((folder / "sf_moves.json").read_text(encoding="utf-8"))
    mine = {}
    for m in sm:
        if m.get("mine"):
            mine.setdefault(m["link"], []).append(m)
    for r in rows:
        g = sg.get(r["link"])
        r["acc"] = g["acc"] if g else None
        big = [m for m in mine.get(r["link"], []) if m["drop"] >= 20 and m["ply"] <= 40]
        r["early"] = len(big)
        r["cmoves"] = [m for m in big if _king_home(m["fen"], r["white"]) and not m["san"].startswith("O-O")]
        r["center"] = len(r["cmoves"])
    new = [r for r in rows if r["date"] >= since]
    old = [r for r in rows if r["date"] < since and (before_from is None or r["date"] >= before_from)]
    if len(new) < 10 or len(old) < 10:
        return None, {}
    o, n = _stats(old), _stats(new)
    span_old = f"{_d(min(r['date'] for r in old))} – {_d(max(r['date'] for r in old))}"
    span_new = f"{_d(min(r['date'] for r in new))} – {_d(max(r['date'] for r in new))}"

    def tr(lab, a, b, unit=""):
        return J("<tr><td>", lab, f'</td><td class="num">{a}{unit}</td><td class="num">{b}{unit}</td></tr>')

    table = J('<div class="scroll"><table><tr><th>', T("Навик", "Habit", "Habitude"), "</th><th>", span_old,
              f' <span class="hint">({o["n"]})</span></th><th>', span_new, f' <span class="hint">({n["n"]})</span></th></tr>',
              tr(T("Рокада до 8-ия ход", "Castled by move 8", "Roque avant le 8e coup"), o["c8"], n["c8"], "%"),
              tr(T("Ход на рокадата (медиана)", "Castling move (median)", "Coup du roque (médiane)"), _fmt_med(o["cmed"]), _fmt_med(n["cmed"])),
              tr(T("Без рокада", "Never castled", "Pas de roque"), o["never"], n["never"], "%"),
              tr(T("Двата офицера извадени до 10-ия ход", "Both bishops out by move 10", "Les deux fous sortis avant le 10e coup"), o["both10"], n["both10"], "%"),
              tr(T("Ходове с офицер в първите 10 хода", "Bishop moves in the first 10 moves", "Coups de fou dans les 10 premiers coups"), o["b10"], n["b10"]),
              tr(T("Грешки до 20-ия ход (на партия)", "Mistakes before move 20 (per game)", "Erreurs avant le 20e coup (par partie)"), o["early"], n["early"]),
              tr(T("… от тях с цар още на e1/e8", "… of them with the king still on e1/e8", "… dont avec le roi encore en e1/e8"), o["center"], n["center"]),
              tr(T("Точност", "Accuracy", "Précision"), o["acc"], n["acc"], "%"),
              tr(T("Успеваемост", "Score", "Score"), o["score"], n["score"], "%"),
              "</table></div>")

    def grp(lab, key):
        a = [r for r in new if key(r)]
        return J("<tr><td>", lab, f'</td><td class="num">{len(a)}</td><td class="num">'
                 f'{round(100 * sum(r["sc"] for r in a) / len(a)) if a else "–"}%</td></tr>')

    split = J('<div class="scroll"><table><tr><th>', T(f"От {_d(since)}", f"Since {_d(since)}", f"Depuis le {_d(since)}"), "</th><th>",
              T("Партии", "Games", "Parties"), "</th><th>", T("Успеваемост", "Score", "Score"), "</th></tr>",
              grp(T("Рокада до 8-ия ход", "Castled by move 8", "Roque avant le 8e coup"), lambda r: r["castle"] and r["castle"] <= 8),
              grp(T("Рокада между 9-ия и 14-ия ход", "Castled on moves 9–14", "Roque entre le 9e et le 14e coup"), lambda r: r["castle"] and 9 <= r["castle"] <= 14),
              grp(T("Рокада след 14-ия ход или без рокада", "Castled after move 14 or never", "Roque après le 14e coup ou jamais"), lambda r: not r["castle"] or r["castle"] > 14),
              grp(T("Поне една грешка с цар в центъра", "At least one mistake with the king in the centre", "Au moins une erreur avec le roi au centre"), lambda r: r["center"] > 0),
              grp(T("Без грешка с цар в центъра", "No mistake with the king in the centre", "Aucune erreur avec le roi au centre"), lambda r: r["acc"] is not None and r["center"] == 0),
              "</table></div>")

    # examples: the biggest mistakes with the king at home since the date
    ex = sorted(((m, r) for r in new for m in r["cmoves"]), key=lambda x: -x[0]["drop"])[:examples]
    viewers, boards = {}, []
    for k, (m, r) in enumerate(ex, 1):
        vid = f"style-ex{k}"
        g = None
        with open(folder / "games.pgn", encoding="utf-8") as f:
            while True:
                gg = chess.pgn.read_game(f)
                if gg is None or gg.headers.get("Link") == r["link"]:
                    g = gg
                    break
        if g is None:
            continue
        b = g.board()
        sans = []
        for mv in g.mainline_moves():
            sans.append(b.san(mv))
            b.push(mv)
        ply = m["ply"]
        num = f"{m['move_no']}." if r["white"] else f"{m['move_no']}..."
        viewers[vid] = {"moves": " ".join(sans[:min(len(sans), ply + 3)]), "orientation": "white" if r["white"] else "black",
                        "from_ply": ply, "to_ply": min(len(sans), ply + 3),
                        "title": J(T("срещу ", "vs ", "contre "), r["opp"], f", {_d(r['date'])}"),
                        "arrows": {str(ply): _arrows(m)},
                        "notes": {str(ply): J(T("Царят е още в центъра. По-добре: ", "The king is still in the centre. Better: ", "Le roi est encore au centre. Mieux : "), f"{num}{m['best']}")}}
        boards.append(J("<li>", f'<a href="{r["link"]}" target="_blank" rel="noopener">', T("срещу ", "vs ", "contre "), r["opp"], "</a> (", _d(r["date"]), "): ",
                        f"{num}{m['san']}", T(f" – шанс {m['before']:.0f}% → {m['after']:.0f}%. Продължение: ", f" – chances {m['before']:.0f}% → {m['after']:.0f}%. Continuation: ",
                                               f" – chances {m['before']:.0f} % → {m['after']:.0f} %. Suite : "),
                        m.get("after_line", ""), T(". По-добре: ", ". Better: ", ". Mieux : "), f"{num}{m['best']}.</li>"))

    ratio = round(n["center"] / o["center"], 1) if o["center"] else None
    late = [r for r in new if not r["castle"] or r["castle"] > 14]
    mid = [r for r in new if r["castle"] and 9 <= r["castle"] <= 14]
    pct = lambda x: round(100 * sum(r["sc"] for r in x) / len(x)) if x else 0
    html = J(
        T(f"<p>От {_d(since)} променяте стила си: повече игра с офицерите и рокада без бързане. Тук са навиците ви преди и след това "
          f"({o['n']} срещу {n['n']} партии, от ваша страна, първите ходове на всяка партия; грешка = спад на шанса с 20% или повече по Stockfish).</p>",
          f"<p>Since {_d(since)} you have been changing your style: more play with the bishops and no rush to castle. These are your habits before and after "
          f"({o['n']} vs {n['n']} games, your side, the first moves of each game; mistake = a drop of 20% or more in winning chances by Stockfish).</p>",
          f"<p>Depuis le {_d(since)} vous changez de style : plus de jeu avec les fous et pas de hâte pour roquer. Voici vos habitudes avant et après "
          f"({o['n']} contre {n['n']} parties, de votre côté, les premiers coups de chaque partie ; erreur = baisse de 20 % ou plus des chances selon Stockfish).</p>"),
        table,
        T(f"<p><b>Офицерите:</b> двата офицера са навън до 10-ия ход в {n['both10']}% от партиите (преди {o['both10']}%) – промяната работи. "
          f"Ходовете с офицер в първите 10 хода са {n['b10']} (преди {o['b10']}): внимавайте да не местите един офицер два-три пъти – всеки офицер с един ход на добро поле.</p>"
          f"<p><b>Рокадата:</b> рокирате обикновено на {_rnd(n['cmed'])}-ия ход (преди на {_rnd(o['cmed'])}-ия). Проблемът не е, че е по-късна – партиите с рокада след 14-ия ход или без рокада имат {pct(late)}%, "
          f"а тези с рокада между 9-ия и 14-ия ход {pct(mid)}%. Проблемът е, че докато царят е в центъра, правите {n['center']} грешки на партия (преди {o['center']}"
          + (f", {ratio} пъти повече" if ratio else "") + ").</p>",
          f"<p><b>Bishops:</b> both bishops are out by move 10 in {n['both10']}% of games (before {o['both10']}%) – the change works. "
          f"Bishop moves in the first 10 moves are {n['b10']} (before {o['b10']}): avoid moving the same bishop two or three times – each bishop with one move to a good square.</p>"
          f"<p><b>Castling:</b> you usually castle on move {_rnd(n['cmed'])} (before move {_rnd(o['cmed'])}). Castling later is not the problem – games with castling after move 14 or none score {pct(late)}%, "
          f"those with castling on moves 9–14 {pct(mid)}%. The problem is that while the king is in the centre you make {n['center']} mistakes a game (before {o['center']}"
          + (f", {ratio} times as many" if ratio else "") + ").</p>",
          f"<p><b>Les fous :</b> les deux fous sont sortis avant le 10e coup dans {n['both10']} % des parties (avant {o['both10']} %) – le changement marche. "
          f"Les coups de fou dans les 10 premiers coups sont {n['b10']} (avant {o['b10']}) : évitez de jouer le même fou deux ou trois fois – chaque fou en un coup sur une bonne case.</p>"
          f"<p><b>Le roque :</b> vous roquez le plus souvent au {_rnd(n['cmed'])}e coup (avant au {_rnd(o['cmed'])}e). Roquer plus tard n'est pas le problème – les parties avec roque après le 14e coup ou sans roque font {pct(late)} %, "
          f"celles avec roque entre le 9e et le 14e coup {pct(mid)} %. Le problème : tant que le roi est au centre, vous faites {n['center']} erreurs par partie (avant {o['center']}"
          + (f", {ratio} fois plus" if ratio else "") + ").</p>"),
        split,
        T("<h3>Грешки с цар в центъра</h3><ul>", "<h3>Mistakes with the king in the centre</h3><ul>", "<h3>Erreurs avec le roi au centre</h3><ul>"),
        *boards, "</ul>", "".join(f"{{{{V:{v}}}}}" for v in viewers),
        T("<div class=\"callout\"><p style=\"margin:0\"><b>Как да продължите:</b> запазете новия стил с офицерите. „Без бързане с рокадата“ значи първо конете и офицерите, после рокада – около 8–10-ия ход, освен ако има конкретна причина да чакате. "
          "Докато царят е в центъра, преди всеки ход проверете: пешката f2/f7, шах по линия e и шах по диагоналите към e1/e8 (Bb4+, Qh5+, Qa4+).</p></div>",
          "<div class=\"callout\"><p style=\"margin:0\"><b>How to go on:</b> keep the new bishop style. “No rush to castle” means knights and bishops first, then castle – around move 8–10, unless there is a concrete reason to wait. "
          "While the king is in the centre, check before every move: the f2/f7 pawn, a check on the e-file and checks on the diagonals to e1/e8 (Bb4+, Qh5+, Qa4+).</p></div>",
          "<div class=\"callout\"><p style=\"margin:0\"><b>Pour la suite :</b> gardez le nouveau style avec les fous. « Pas de hâte pour roquer » veut dire d'abord les cavaliers et les fous, puis le roque – vers le 8e–10e coup, sauf raison concrète d'attendre. "
          "Tant que le roi est au centre, vérifiez avant chaque coup : le pion f2/f7, un échec sur la colonne e et les échecs sur les diagonales vers e1/e8 (Bb4+, Qh5+, Qa4+).</p></div>"))
    sec = dict(id="style", title=T("Смяна на стила: офицери и рокада", "Style change: bishops and castling", "Changement de style : fous et roque"),
               toc_title=T("Смяна на стила", "Style change", "Changement de style"), html=html)
    return sec, viewers
