"""Report section from OUT/explorer.json (explorer.py): your openings compared with the lichess database.

    import explorer_section
    sec, viewers = explorer_section.build(json.load(open(OUT / "explorer.json")), max_rows=6, boards=2)

Returns a section dict for report_spec.json ({"id": "explorer", ...}, every text {"bg", "en", "fr"}) and the
viewers it refers to ({{V:ex1}} ...); add them to the spec's "viewers". Every number comes from the file.
"""
import chess

import move_ideas

LANGS = ("bg", "en", "fr")
SPEEDS = {"rapid": ("рапид", "rapid", "rapide"), "blitz": ("блиц", "blitz", "blitz"), "bullet": ("бълет", "bullet", "bullet"),
          "correspondence": ("кореспондентски", "correspondence", "par correspondance")}


def T(bg, en, fr):
    return {"bg": bg, "en": en, "fr": fr}


def J(*parts):
    return {lg: "".join(p[lg] if isinstance(p, dict) else str(p) for p in parts) for lg in LANGS}


def pc(x, lg):
    """'52%' / '52 %' (French puts a space before %)."""
    if x is None:
        return "–"
    v = f"{x:.0f}"
    return f"{v} %" if lg == "fr" else f"{v}%"


def P(x):
    return {lg: pc(x, lg) for lg in LANGS}


def tag(x):
    return "n" if x is None else "w" if x >= 55 else "l" if x < 45 else "n"


def line_txt(sans):
    """['d4', 'd5', 'e3'] -> '1.d4 d5 2.e3'."""
    out = []
    for i, s in enumerate(sans):
        out.append(f"{i // 2 + 1}.{s}" if i % 2 == 0 else s)
    return " ".join(out)


def move_txt(ply, san):
    """The move with its number: 3.Bb5 or 3...Nf6."""
    return f"{ply // 2 + 1}.{san}" if ply % 2 == 0 else f"{ply // 2 + 1}...{san}"


def mv_cells(ply, san):
    m = move_txt(ply, san)
    return f'<span class="words-only">{m}</span> <code>{m}</code>'


def arrow(line, san, colour):
    b = chess.Board()
    for s in line:
        b.push_san(s)
    mv = b.parse_san(san)
    return [chess.square_name(mv.from_square), chess.square_name(mv.to_square), colour]


def _says(w, fr, san):
    """' 2.e3 opens ... .' for one move from w["ideas"], {} when there is nothing to say."""
    f = (w.get("ideas") or {}).get(san)
    if not f:
        return None
    out = {lg: move_ideas.join(move_ideas.clauses(f, lg, fr), lg) for lg in LANGS}
    return None if not out["en"] else {lg: f" {move_txt(fr, san)} {out[lg]}." for lg in LANGS}


def own_note(w, fr):
    return _says(w, fr, w["mine"][0]["san"]) or ""


def best_note(w, fr):
    """Why the better move is better: what it does, Stockfish's win % for both moves (your colour) and its main line."""
    ideas, best, mine = w.get("ideas") or {}, w["best"], w["mine"][0]["san"]
    head = _says(w, fr, best)
    head = {lg: head[lg].strip() for lg in LANGS} if head else J(move_txt(fr, best), T(" печели най-много в базата на вашето ниво.",
                                                                                      " scores best in the database at your level.",
                                                                                      " rapporte le plus dans la base à votre niveau."))
    b, m = ideas.get(best, {}), ideas.get(mine, {})
    if "wp" not in b or "wp" not in m:
        return head
    parts = [head, T(" Stockfish: ", " Stockfish: ", " Stockfish : "), P(b["wp"]), T(" срещу ", " against ", " contre "), P(m["wp"]), T(" за ", " for ", " pour "), move_txt(fr, mine), "."]
    if b.get("pv"):
        parts += [T(" Възможно продължение: ", " A likely line: ", " Suite possible : "), move_ideas.pv_txt(fr + 1, b["pv"]), "."]
    return J(*parts)


def build(E, max_rows=6, boards=2):
    p, st = E["params"], E["exit_stats"]
    sp = [SPEEDS.get(s, (s, s, s)) for s in p["speeds"].split(",")]
    speeds = T(", ".join(s[0] for s in sp), ", ".join(s[1] for s in sp), ", ".join(s[2] for s in sp))
    rs = [int(x) for x in p["ratings"].split(",")]
    band = f"{rs[0]}–{rs[-1] + 199}" if len(rs) > 1 else f"{rs[0]}–{rs[0] + 199}"
    n = sum(s["games"] for s in st.values())
    moves = p["max_ply"] // 2

    html = [T(f"<p>Първите {moves} хода от вашите {n} партии са сравнени с партиите в <a href=\"https://lichess.org/analysis#explorer\" target=\"_blank\" rel=\"noopener\">базата на lichess</a> "
              f"на играчи с рейтинг {band} в lichess ({speeds['bg']}; рейтингът в lichess обикновено е с около 400 точки по-висок от този в chess.com). "
              f"<b>Известен ход</b> тук значи ход, изигран поне {p['min_games']} пъти в тези партии. Успеваемостта в базата е за страната, която играе хода.</p>",
              f"<p>The first {moves} moves of your {n} games are compared with the <a href=\"https://lichess.org/analysis#explorer\" target=\"_blank\" rel=\"noopener\">lichess database</a> "
              f"of players rated {band} on lichess ({speeds['en']}; lichess ratings are usually about 400 points higher than chess.com ones). "
              f"<b>A known move</b> here means one played at least {p['min_games']} times in those games. Database scores are for the side that plays the move.</p>",
              f"<p>Les {moves} premiers coups de vos {n} parties sont comparés à la <a href=\"https://lichess.org/analysis#explorer\" target=\"_blank\" rel=\"noopener\">base lichess</a> "
              f"des joueurs classés {band} sur lichess ({speeds['fr']} ; le classement lichess est en général environ 400 points au-dessus de celui de chess.com). "
              f"<b>Un coup connu</b> est ici un coup joué au moins {p['min_games']} fois dans ces parties. Les scores de la base sont ceux du camp qui joue le coup.</p>")]

    # ---- where the known moves end
    html += ["<h3>", T("Кой излиза пръв от известните ходове", "Who leaves the known moves first", "Qui quitte les coups connus en premier"), "</h3>",
             '<div class="scroll"><table><tr><th>', T("Цвят", "Colour", "Couleur"), "</th><th>", T("Партии", "Games", "Parties"), "</th><th>",
             T("Среден ход", "Average move", "Coup moyen"), "</th><th>", T("Излизате вие", "You leave", "Vous sortez"), "</th><th>",
             T("Излиза противникът", "Opponent leaves", "L'adversaire sort"), "</th><th>", T(f"Известни до {moves}-ия ход", f"Known to move {moves}", f"Connus jusqu'au coup {moves}"), "</th></tr>"]
    for col, name in (("white", T("Белите", "White", "Blancs")), ("black", T("Черните", "Black", "Noirs"))):
        s = st.get(col)
        if not s:
            continue
        cell = lambda k, sc: J(f'<td class="num">{s[k]} <span class="tag {tag(sc)}">', P(sc), "</span></td>")
        html += ["<tr><td>", name, f'</td><td class="num">{s["games"]}</td><td class="num">{s["avg_exit_move"] or "–"}</td>',
                 cell("me", s["score_me"]), cell("opp", s["score_opp"]), cell("none", s["score_none"]), "</tr>"]
    html.append("</table></div>")
    html.append(T("<p class=\"hint\">Числото е броят партии, а цветното поле е вашата успеваемост в тях.</p>",
                  "<p class=\"hint\">The number is the count of games, the coloured box your score in them.</p>",
                  "<p class=\"hint\">Le nombre est celui des parties, la case colorée votre score dans ces parties.</p>"))
    tot = lambda k: sum(s[k] for s in st.values())
    me_n, opp_n = tot("me"), tot("opp")
    w_me = [s["score_me"] for s in st.values() if s["score_me"] is not None]
    w_op = [s["score_opp"] for s in st.values() if s["score_opp"] is not None]
    if w_me and w_op:
        a = sum(s["score_me"] * s["me"] for s in st.values() if s["score_me"] is not None) / max(1, me_n)
        b = sum(s["score_opp"] * s["opp"] for s in st.values() if s["score_opp"] is not None) / max(1, opp_n)
        if a + 3 < b:
            html.append(T(f"<p>Когато <b>вие</b> излезете първи от известните ходове, успеваемостта ви е {pc(a, 'bg')}; когато излезе противникът, {pc(b, 'bg')}. "
                          "Вашите собствени ходове в дебюта струват точки: таблицата отдолу показва къде.</p>",
                          f"<p>When <b>you</b> leave the known moves first, you score {pc(a, 'en')}; when the opponent does, {pc(b, 'en')}. "
                          "Your own opening ideas cost points: the table below shows where.</p>",
                          f"<p>Quand <b>vous</b> quittez les coups connus en premier, votre score est de {pc(a, 'fr')} ; quand c'est l'adversaire, {pc(b, 'fr')}. "
                          "Vos propres idées d'ouverture coûtent des points : le tableau ci-dessous montre où.</p>"))
        elif b + 3 < a:
            html.append(T(f"<p>Когато <b>вие</b> излезете първи от известните ходове, успеваемостта ви е {pc(a, 'bg')}; когато излезе противникът, {pc(b, 'bg')}. "
                          "Наказвате неизвестните ходове на противника по-слабо, отколкото играете своите.</p>",
                          f"<p>When <b>you</b> leave the known moves first, you score {pc(a, 'en')}; when the opponent does, {pc(b, 'en')}. "
                          "You punish the opponent's unusual moves less well than you play your own.</p>",
                          f"<p>Quand <b>vous</b> quittez les coups connus en premier, votre score est de {pc(a, 'fr')} ; quand c'est l'adversaire, {pc(b, 'fr')}. "
                          "Vous punissez moins bien les coups inhabituels de l'adversaire que vous ne jouez les vôtres.</p>"))
        else:
            html.append(T(f"<p>Няма голяма разлика дали първи излизате вие ({pc(a, 'bg')}) или противникът ({pc(b, 'bg')}).</p>",
                          f"<p>It makes little difference whether you leave the known moves first ({pc(a, 'en')}) or the opponent does ({pc(b, 'en')}).</p>",
                          f"<p>Peu de différence entre vous ({pc(a, 'fr')}) et l'adversaire ({pc(b, 'fr')}) pour la sortie des coups connus.</p>"))

    # ---- your choices that score below the alternative
    weak = E["weak"][:max_rows]
    viewers = {}
    if weak:
        html += ["<h3>", T("Ходове с по-добра алтернатива", "Moves with a better-scoring alternative", "Coups avec une meilleure alternative"), "</h3>",
                 T("<p>Позиции, които сте имали поне 3 пъти. Вашият обичаен ход печели по-малко в базата от друг ход, който играчите на вашето ниво също играят често.</p>",
                   "<p>Positions you had at least 3 times. Your usual move scores less in the database than another move players at your level also play often.</p>",
                   "<p>Positions rencontrées au moins 3 fois. Votre coup habituel rapporte moins dans la base qu'un autre coup que les joueurs de votre niveau jouent souvent aussi.</p>"),
                 '<div class="scroll"><table><tr><th>', T("Позиция след", "Position after", "Position après"), "</th><th>",
                 T("Вашият ход", "Your move", "Votre coup"), "</th><th>", T("Пъти / ваша успеваемост", "Times / your score", "Fois / votre score"), "</th><th>",
                 T("В базата", "Database", "Base"), "</th><th>", T("По-добре", "Better", "Mieux"), "</th><th>", T("В базата", "Database", "Base"), "</th></tr>"]
        for i, w in enumerate(weak, 1):
            m, bd = w["mine"][0], w["best_db"]
            pos = line_txt(w["line"]) if w["line"] else T("(начална позиция)", "(start position)", "(position initiale)")
            html += ["<tr><td>", pos, "</td><td>", mv_cells(w["ply"], m["san"]), f'</td><td class="num">{m["times"]} / <span class="tag {tag(m["score"])}">', P(m["score"]),
                     '</span></td><td class="num">', P(m["db"][2]), "</td><td>", mv_cells(w["ply"], w["best"]), '</td><td class="num"><b>', P(bd[2]), "</b> ",
                     J('<span class="hint">(', T("играе се в ", "played in ", "joué dans "), P(bd[1]), ")</span>"), "</td></tr>"]
        html.append("</table></div>")
        # boards for the largest ones
        bl = []
        for i, w in enumerate(weak[:boards], 1):
            vid = f"ex{i}"
            fr = len(w["line"])
            m = w["mine"][0]
            viewers[vid] = {
                "moves": " ".join(w["line"] + [w["best"]]), "orientation": "white" if w["white"] else "black", "start_index": fr,
                "title": J(T("Позиция след ", "Position after ", "Position après "), line_txt(w["line"]) if w["line"] else T("(начална позиция)", "(start position)", "(position initiale)")),
                "notes": {str(fr): J(T("Вие: ", "You: ", "Vous : "), move_txt(fr, m["san"]), f" ({m['times']}×, ", T("база ", "database ", "base "), P(m["db"][2]),
                                     T("). По-добре: ", "). Better: ", "). Mieux : "), move_txt(fr, w["best"]), " (", P(w["best_db"][2]), ").",
                                     # the most played move too, when it is neither yours nor the best one
                                     J(T(" Най-играният: ", " Most played: ", " Le plus joué : "), move_txt(fr, w["popular"]), " (",
                                       T("в ", "in ", "dans "), P(w["popular_db"][1]), T(" от партиите, ", " of games, ", " des parties, "), P(w["popular_db"][2]), ").")
                                     if w["popular"] not in (m["san"], w["best"]) and w["popular_db"] else "", own_note(w, fr)),
                          str(fr + 1): best_note(w, fr)},
                "arrows": {str(fr): [arrow(w["line"], m["san"], "red"), arrow(w["line"], w["best"], "green")]},
            }
            bl.append(f"{{{{V:{vid}}}}}")
        html += ['<div class="vgrid">', "".join(bl), "</div>",
                 T("<p class=\"hint\">Червено: вашият обичаен ход. Зелено: ходът с най-добра успеваемост в базата. Процентите от Stockfish са шансовете ви за победа с вашия цвят.</p>",
                   "<p class=\"hint\">Red: your usual move. Green: the move that scores best in the database. Stockfish percentages are your winning chances with your colour.</p>",
                   "<p class=\"hint\">Rouge : votre coup habituel. Vert : le coup qui rapporte le plus dans la base. Les pourcentages de Stockfish sont vos chances de gain avec votre couleur.</p>")]

    # ---- your own departures
    nov = E["novelties"][:5]
    if len(nov) >= 2:  # a single repeated departure is not a pattern
        html += ["<h3>", T("Къде излизате от известните ходове", "Where you leave the known moves", "Où vous quittez les coups connus"), "</h3>",
                 T("<p>Ваши ходове, които играчите на вашето ниво почти не играят (по-малко от ", "<p>Your moves that players at your level hardly ever play (fewer than ",
                   "<p>Vos coups que les joueurs de votre niveau ne jouent presque jamais (moins de "),
                 str(p["min_games"]), T(" партии), изиграни поне два пъти:</p>", " games), played at least twice:</p>", " parties), joués au moins deux fois :</p>"),
                 '<div class="scroll"><table><tr><th>', T("Позиция след", "Position after", "Position après"), "</th><th>", T("Вашият ход", "Your move", "Votre coup"),
                 "</th><th>", T("Партии", "Games", "Parties"), "</th><th>", T("Успеваемост", "Score", "Score"), "</th></tr>"]
        for x in nov:
            pos = line_txt(x["line"]) if x["line"] else T("(начална позиция)", "(start position)", "(position initiale)")
            html += ["<tr><td>", pos, "</td><td>", mv_cells(len(x["line"]), x["san"]), f'</td><td class="num">{x["games"]}</td>',
                     f'<td class="num"><span class="tag {tag(x["score"])}">', P(x["score"]), "</span></td></tr>"]
        html.append("</table></div>")

    sec = {"id": "explorer", "title": T("Дебютите в базата на lichess", "Your openings in the lichess database", "Vos ouvertures dans la base lichess"),
           "toc_title": T("База lichess", "Lichess database", "Base lichess"), "html": J(*html)}
    return sec, viewers
