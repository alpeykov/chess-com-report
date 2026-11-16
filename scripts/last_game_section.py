"""Extra blocks for the latest-game section, from OUT/last_extra.json (last_game.py).

    import last_game_section
    html, viewers = last_game_section.build(json.load(open(OUT / "last_extra.json")), max_puzzles=6)

`html` is a {"bg", "en", "fr"} dict to append to game_analysis["html"]; `viewers` are the puzzle boards
({{V:lgp1}} ...) to add to the spec's "viewers". GOTO buttons point at the game viewer ("game").
Every number comes from the file; moves are written in SAN with their numbers, so the builder adds the names.
"""
LANGS = ("bg", "en", "fr")


def T(bg, en, fr):
    return {"bg": bg, "en": en, "fr": fr}


def J(*parts):
    return {lg: "".join(p[lg] if isinstance(p, dict) else str(p) for p in parts) for lg in LANGS}


def pc(x, lg):
    if x is None:
        return "–"
    v = f"{x:.0f}"
    return f"{v} %" if lg == "fr" else f"{v}%"


def P(x):
    return {lg: pc(x, lg) for lg in LANGS}


def num(x, lg, d=1):
    if x is None:
        return "–"
    s = f"{x:.{d}f}".rstrip("0").rstrip(".") if d else f"{x:.0f}"
    return s.replace(".", ",") if lg in ("bg", "fr") else s


def N(x, d=1):
    return {lg: num(x, lg, d) for lg in LANGS}


def mv(ply, san):
    return f"{ply // 2 + 1}.{san}" if ply % 2 == 0 else f"{ply // 2 + 1}...{san}"


def line(ply, sans):
    out = []
    for i, s in enumerate(sans):
        p = ply + i
        out.append(f"{p // 2 + 1}.{s}" if p % 2 == 0 else (f"{p // 2 + 1}...{s}" if i == 0 else s))
    return " ".join(out)


SUBJ = {"bg": dict(P="пешката", N="конят", B="офицерът", R="топът", Q="царицата", K="царят"),
        "en": dict(P="the pawn", N="the knight", B="the bishop", R="the rook", Q="the queen", K="the king"),
        "fr": dict(P="le pion", N="le cavalier", B="le fou", R="la tour", Q="la dame", K="le roi")}
OBJ = {"bg": dict(P="пешката", N="коня", B="офицера", R="топа", Q="царицата", K="царя"),
       "en": SUBJ["en"], "fr": SUBJ["fr"]}
MOT = {"hanging": T("незащитена фигура", "undefended piece", "pièce non défendue"), "fork": T("вилка", "fork", "fourchette"),
       "mate": T("мат", "mate", "mat"), "back_rank_mate": T("мат на последния ред", "back-rank mate", "mat du couloir"),
       "pin": T("свързване", "pin", "clouage"), "skewer": T("шиш", "skewer", "enfilade"),
       "discovered": T("открито нападение", "discovered attack", "attaque à la découverte"), "promotion": T("промоция", "promotion", "promotion")}
VERDICT = {"punished": ("w", T("наказана", "punished", "punie")), "partly": ("n", T("отчасти", "partly", "en partie")),
           "missed": ("l", T("пропусната", "missed", "manquée"))}


def de(sq):
    return f"d'{sq}" if sq[0] in "ae" else f"de {sq}"


def words(m):
    """'the pawn from d4 takes the queen on e5' without a move number (a move that was not played)."""
    out = {}
    for lg in LANGS:
        s = SUBJ[lg][m["piece"]]
        s = s[0].upper() + s[1:]
        if m["takes"]:
            t = OBJ[lg][m["takes"]]
            out[lg] = {"bg": f"{s} от {m['from']} взима {t} на {m['to']}", "en": f"{s} from {m['from']} takes {t} on {m['to']}",
                       "fr": f"{s} {de(m['from'])} prend {t} en {m['to']}"}[lg]
        else:
            out[lg] = {"bg": f"{s} от {m['from']} отива на {m['to']}", "en": f"{s} from {m['from']} goes to {m['to']}",
                       "fr": f"{s} {de(m['from'])} va en {m['to']}"}[lg]
        if m["mate"]:
            out[lg] += {"bg": " с мат", "en": " with mate", "fr": " avec mat"}[lg]
        elif m["check"]:
            out[lg] += {"bg": " с шах", "en": " with check", "fr": " avec échec"}[lg]
    return out


MAT = {"bg": {"P": ("пешка", "пешки"), "N": ("кон", "коня"), "B": ("офицер", "офицера"), "R": ("топ", "топа"), "Q": ("царица", "царици"), "m": ("лека фигура", "леки фигури")},
       "en": {"P": ("pawn", "pawns"), "N": ("knight", "knights"), "B": ("bishop", "bishops"), "R": ("rook", "rooks"), "Q": ("queen", "queens"), "m": ("minor piece", "minor pieces")},
       "fr": {"P": ("pion", "pions"), "N": ("cavalier", "cavaliers"), "B": ("fou", "fous"), "R": ("tour", "tours"), "Q": ("dame", "dames"), "m": ("pièce mineure", "pièces mineures")}}


def mat_words(d):
    """{"B": -1, "P": 1} -> 'a bishop down and a pawn up'; equal -> 'level material'."""
    d = dict(d)
    if d.get("N") and d.get("B") and (d["N"] > 0) != (d["B"] > 0):  # a knight for a bishop: count them together
        m = d.pop("N") + d.pop("B")
        if m:
            d["m"] = m
    FR1 = {"P": "un pion", "N": "un cavalier", "B": "un fou", "R": "une tour", "Q": "une dame", "m": "une pièce mineure"}
    out = {}
    for lg in LANGS:
        items = []
        for k in ("Q", "R", "m", "B", "N", "P"):  # most valuable first: "a rook down and a pawn up"
            n = d.get(k, 0)
            if not n:
                continue
            one, many = MAT[lg][k]
            w = {"bg": one, "en": "a " + one, "fr": FR1[k]}[lg] if abs(n) == 1 else f"{abs(n)} {many}"
            items.append({"bg": f"{w} {'повече' if n > 0 else 'по-малко'}", "en": f"{w} {'up' if n > 0 else 'down'}",
                          "fr": f"{w} de {'plus' if n > 0 else 'moins'}"}[lg])
        if not items:
            out[lg] = {"bg": "с равни фигури", "en": "level on material", "fr": "à égalité de matériel"}[lg]
        else:
            sep = {"bg": " и ", "en": " and ", "fr": " et "}[lg]
            out[lg] = {"bg": "с ", "en": "", "fr": "avec "}[lg] + sep.join(items)
    return out


def clock_txt(sec):
    if sec is None:
        return "–"
    return f"{int(sec) // 60}:{int(sec) % 60:02d}"


def build(X, max_puzzles=6):
    white = X["white"]
    side = T("белите", "White", "les Blancs") if white else T("черните", "Black", "les Noirs")
    Side = T("Белите", "White", "Les Blancs") if white else T("Черните", "Black", "Les Noirs")
    games_m = X.get("motif_games") or 0
    html, viewers = [], {}
    M = X["moments"]

    # ---- 1. puzzles
    pz = sorted(M, key=lambda m: (not m["missed_mate"], -(m["best_wp"] - m["after"])))[:max_puzzles]
    pz.sort(key=lambda m: m["ply"])
    if pz:
        import chess
        html += ["<h3>", T("Задачи от партията", "Puzzles from the game", "Problèmes tirés de la partie"), "</h3>",
                 T("<p>Позициите, в които имаше по-добър ход. Кликнете фигура и после полето, на което да отиде. "
                   "„Покажи отговора“ показва решението, а после стрелките показват продължението.</p>",
                   "<p>The positions where there was a better move. Click a piece, then the square it should go to. "
                   "“Show the answer” shows the solution; then the arrows play through the line.</p>",
                   "<p>Les positions où il y avait un meilleur coup. Cliquez une pièce, puis la case où elle doit aller. "
                   "« Montrer la réponse » affiche la solution ; ensuite les flèches déroulent la suite.</p>"), '<div class="vgrid">']
        for i, m in enumerate(pz, 1):
            vid = f"lgp{i}"
            b = chess.Board()
            sans = []
            for u in X["moves"][:m["ply"]]:
                mv_ = chess.Move.from_uci(u)
                sans.append(b.san(mv_))
                b.push(mv_)
            p = m["ply"]
            prompt = J(Side, T(" са на ход. В партията: ", " to move. In the game: ", " au trait. Dans la partie : "), mv(p, m["played"]["san"]), ". ",
                       T("Има мат в един ход!", "There is mate in one!", "Il y a mat en un coup !") if m["missed_mate"] else
                       T("Намерете по-добрия ход.", "Find the better move.", "Trouvez le meilleur coup."))
            expl = J(mv(p, m["best"]["san"]), ": ",
                     T("мат.", "mate.", "mat.") if m["best"]["mate"] else
                     J(T("шанс ", "chances ", "chances "), P(m["best_wp"]), T(" вместо ", " instead of ", " au lieu de "), P(m["after"]),
                       T(" след ", " after ", " après "), mv(p, m["played"]["san"]), ". ",
                       T("Продължение: ", "Line: ", "Suite : "), line(p, m["solution"]), ".",
                       J(T(" Това е вечен шах: давате фигура, но царицата ви дава шах след шах и белият цар не може да се скрие, така че партията е реми.",
                           " This is a perpetual check: you give up material, but your queen checks again and again and the king cannot hide, so the game is a draw.",
                           " C'est un échec perpétuel : vous donnez du matériel, mais votre dame donne échec sur échec et le roi ne peut pas se cacher, donc la partie est nulle.")
                         if white is False else
                         T(" Това е вечен шах: давате фигура, но царицата ви дава шах след шах и черният цар не може да се скрие, така че партията е реми.",
                           " This is a perpetual check: you give up material, but your queen checks again and again and the king cannot hide, so the game is a draw.",
                           " C'est un échec perpétuel : vous donnez du matériel, mais votre dame donne échec sur échec et le roi ne peut pas se cacher, donc la partie est nulle."))
                       if m.get("perpetual") else "",
                       J(T(" Без жертва: ", " Without the sacrifice: ", " Sans sacrifice : "), mv(p, m["alt"]["san"]), " (", P(m["alt"]["wp"]), ").")
                       if m.get("perpetual") and m.get("alt") and m["alt"]["wp"] > m["after"] + 5 else ""))
            if "mat_before" in m and not m["best"]["mate"]:
                expl = J(expl, T(" Фигури: сега сте ", " Material: now you are ", " Matériel : maintenant vous êtes "), mat_words(m["mat_before"]),
                         T("; в края на показания вариант сте ", "; at the end of the line shown you are ", " ; à la fin de la suite montrée vous êtes "), mat_words(m["mat_end"]), ".")
            viewers[vid] = {"moves": " ".join(sans + m["solution"]), "orientation": "white" if white else "black", "from_ply": p,
                            "title": J(T("Ход ", "Move ", "Coup "), m["move_no"], " · ", side, T(" на ход", " to move", " au trait")),
                            "notes": {str(p): prompt, str(p + 1): expl},
                            "arrows": {str(p + 1): [[m["best"]["from"], m["best"]["to"], "green"]]},
                            "puzzle": {"ok": m["ok"]}}
            html.append(f"{{{{V:{vid}}}}}")
        html.append("</div>")

    # ---- 2, 3, 5. key moments up close: clock, threat, what the move allowed, motifs
    if M:
        html += ["<h3>", T("Ключовите моменти отблизо", "The key moments up close", "Les moments clés de près"), "</h3>",
                 J(T(f"<p><b>Заплаха</b> е ходът, който противникът би изиграл, ако беше на ход още веднъж; шансът до нея е вашият, ако не реагирате. "
                     f"<b>Мотивът</b> показва колко пъти същото се е случвало в последните {games_m} партии.</p>",
                     f"<p>The <b>threat</b> is the move the opponent would play if it were their turn again; the chances next to it are yours if you ignore it. "
                     f"The <b>motif</b> shows how many times the same thing happened in your last {games_m} games.</p>",
                     f"<p>La <b>menace</b> est le coup que l'adversaire jouerait s'il avait de nouveau le trait ; les chances à côté sont les vôtres si vous l'ignorez. "
                     f"Le <b>motif</b> indique combien de fois la même chose est arrivée dans vos {games_m} dernières parties.</p>")),
                 '<div class="scroll"><table><tr><th>', T("Ход", "Move", "Coup"), "</th><th>", T("Време", "Time", "Temps"), "</th><th>",
                 T("Заплаха преди хода", "Threat before the move", "Menace avant le coup"), "</th><th>",
                 T("Ходът ви позволи", "Your move allowed", "Votre coup a permis"), "</th><th>", T("Мотив", "Motif", "Motif"), "</th></tr>"]
        for m in M:
            p, t, al = m["ply"], m["threat"], m["allowed"]
            cls = "l" if m["class"] == "blunder" else "n"
            tm = J(f'{num(m["spent"], "en", 0)} s', '<br><span class="hint">', T("остават ", "left ", "reste "), clock_txt(m["clock"]), "</span>")
            # a threat counts when it is real and your move did not simply move the attacked piece away
            if t and not m["missed_mate"] and m["before"] - t["wp"] >= 15 and m["played"]["from"] != t["to"]:
                th = J(words(t), ' <span class="hint">(', P(t["wp"]), ")</span>")
            else:
                th = T("—", "—", "—")
            if m["missed_mate"]:
                alw = J(T("пропуснат мат: ", "missed mate: ", "mat manqué : "), mv(p, m["best"]["san"]))
            elif al:
                alw = J(line(p + 1, al["line"][:2]),(T(" <b>(заплахата)</b>", " <b>(the threat)</b>", " <b>(la menace)</b>")
                                                   if t and al["uci"] == t["uci"] and m["before"] - t["wp"] >= 15 else ""))
            else:
                alw = ""
            mot = []
            if m["missed_mate"]:
                n = m["seen_missed"].get("mate", 0) + m["seen_missed"].get("back_rank_mate", 0)
                mot.append(J(T("пропуснат мат", "missed mate", "mat manqué"), ' <span class="hint">(', n, T(" пъти)", " times)", " fois)"), "</span>"))
            else:
                for tg, n in m["seen_allowed"].items():
                    if tg in MOT:
                        mot.append(J(T("позволихте: ", "allowed: ", "permis : "), MOT[tg], ' <span class="hint">(', n, T(" пъти)", " times)", " fois)"), "</span>"))
                for tg, n in m["seen_missed"].items():
                    if tg in MOT:
                        mot.append(J(T("пропуснахте: ", "missed: ", "manqué : "), MOT[tg], ' <span class="hint">(', n, T(" пъти)", " times)", " fois)"), "</span>"))
            html += [f'<tr><td class="num">{{{{GOTO:game:{p}:{m["move_no"]}}}}}</td><td class="num">', tm, "</td><td>", th, "</td><td>",
                     f'<span class="tag {cls}">', P(m["before"]), " → ", P(m["after"]), "</span> ", alw, "</td><td>",
                     J(*[J(x, "<br>") for x in mot]) if mot else "—", "</td></tr>"]
        html.append("</table></div>")

        c = X["clock"]
        cmp_ = (X.get("compare") or {}).get("avg", {})
        html.append(J(
            T("<p><b>Часовникът:</b> мислихте средно ", "<p><b>The clock:</b> you spent on average ", "<p><b>La pendule :</b> vous avez réfléchi en moyenne "),
            N(c["avg"]), T(" секунди на ход", " seconds a move", " secondes par coup"),
            J(T(" (в предишните партии ", " (in your previous games ", " (dans vos parties précédentes "), N(cmp_.get("spent")), ")") if cmp_.get("spent") else "",
            T(". Преди грешките: средно ", ". Before your mistakes: on average ", ". Avant vos erreurs : en moyenne "), N(c["errors_avg"]),
            T(" секунди; ", " seconds; ", " secondes ; "), c["errors_fast"], T(" от ", " of ", " sur "), c["errors"],
            T(" са изиграни за по-малко от 10 секунди. Най-дълго мислихте на ", " were played in under 10 seconds. Your longest think was on move ",
              " ont été joués en moins de 10 secondes. Votre plus longue réflexion : au "),
            f"{c['max_move']}", T("-ия ход (", " (", "e coup ("), N(c["max"], 0), T(" s), а накрая ви оставаха ", " s), and at the end you had ",
                                                                                 " s), et à la fin il vous restait "),
            clock_txt(c["left"]), T(" минути.</p>", " minutes left.</p>", " minutes.</p>")))

    # ---- 4. the opponent's mistakes
    O = X["opp"]
    if O:
        k = sum(1 for o in O if o["verdict"] == "punished")
        html += ["<h3>", T("Грешките на противника", "The opponent's mistakes", "Les erreurs de l'adversaire"), "</h3>",
                 J(T("<p>Наказахте ", "<p>You punished ", "<p>Vous avez puni "), k, T(" от ", " of ", " sur "), len(O),
                   T(" грешки на противника: след вашия отговор спечеленото остана.</p>", " of the opponent's mistakes: after your reply the gain stayed.</p>",
                     " erreurs de l'adversaire : après votre réponse, le gain est resté.</p>")),
                 '<div class="scroll"><table><tr><th>', T("Ход", "Move", "Coup"), "</th><th>", T("Противникът", "Opponent", "Adversaire"), "</th><th>",
                 T("Вашият шанс", "Your chances", "Vos chances"), "</th><th>", T("Вашият отговор", "Your reply", "Votre réponse"), "</th><th>",
                 T("По-добре", "Better", "Mieux"), "</th></tr>"]
        for o in O:
            p = o["ply"]
            cls, lab = VERDICT[o["verdict"]]
            better = J(line(p + 1, o["best_line"][:3]), ' <span class="hint">(', P(o["best_wp"]), ")</span>") if o["verdict"] != "punished" else "—"
            html += [f'<tr><td class="num">{{{{GOTO:game:{p + 1}:{p // 2 + 1}}}}}</td><td>', mv(p, o["move"]["san"]), '</td><td class="num">',
                     P(o["before"]), " → ", P(o["after"]), "</td><td>", mv(p + 1, o["reply"]["san"]), f' <span class="tag {cls}">', lab, " ", P(o["after_reply"]),
                     "</span></td><td>", better, "</td></tr>"]
        html.append("</table></div>")

    # ---- 6. the opening against the lichess database
    op = X.get("opening")
    if op and op["steps"]:
        prm = op["params"]
        rs = [int(x) for x in prm["ratings"].split(",")]
        band = f"{rs[0]}–{rs[-1] + 199}"
        html += ["<h3>", T("Дебютът спрямо базата на lichess", "The opening against the lichess database", "L'ouverture face à la base lichess"), "</h3>"]
        known = [s["san"] for s in op["steps"] if s["db"] and s["db"][0] >= prm["min_games"]]
        ex = op["steps"][-1] if op["exit_ply"] is not None else None
        txt = [T(f"<p>Сравнено с партиите на играчи с рейтинг {band} в lichess. Известни ходове (поне {prm['min_games']} партии): ",
                 f"<p>Compared with the games of players rated {band} on lichess. Known moves (at least {prm['min_games']} games): ",
                 f"<p>Comparé aux parties des joueurs classés {band} sur lichess. Coups connus (au moins {prm['min_games']} parties) : "),
               line(0, known) if known else "—", ". "]
        if ex:
            n = ex["db"][0] if ex["db"] else 0
            who = T("Вие излязохте първи", "You left them first", "Vous en êtes sorti le premier") if op["who"] == "me" else \
                T("Противникът излезе първи", "The opponent left them first", "L'adversaire en est sorti le premier")
            txt += [who, T(" с ", " with ", " avec "), mv(ex["ply"], ex["san"]), " (", n, T(" партии в базата", " games in the database", " parties dans la base"),
                     J(T("; най-играният ход там е ", "; the most played move there is ", " ; le coup le plus joué est "), mv(ex["ply"], ex["popular"]))
                     if ex.get("popular") and ex["popular"] != ex["san"] else "", ")."]
        txt.append("</p>")
        html += txt
        rare_opp = [s for s in op["steps"] if not s["mine"] and s["db"] and s["best_db"] and s["db"][1] < 5 and s["best"] != s["san"]]
        for s in rare_opp[:1]:
            html.append(J(T("<p>Противникът изигра рядкото ", "<p>The opponent played the rare ", "<p>L'adversaire a joué le rare "), mv(s["ply"], s["san"]),
                          T(" (в ", " (in ", " (dans "), P(s["db"][1]), T(" от партиите). Успеваемостта му в базата е ", " of games). It scores ",
                                                                            " des parties). Il rapporte "), P(s["db"][2]),
                          T(" срещу ", " in the database, against ", " dans la base, contre "),P(s["best_db"][2]), T(" за ", " for ", " pour "), mv(s["ply"], s["best"]),
                          T(": такъв ход дава шанс да вземете инициативата.</p>", ": a move like that gives you a chance to take the initiative.</p>",
                            " : un tel coup vous donne l'occasion de prendre l'initiative.</p>")))
        for s in op["weaker"]:
            html.append(J("<p>", mv(s["ply"], s["san"]), T(" печели ", " scores ", " rapporte "), P(s["db"][2]), T(" в базата, а ", " in the database, while ", " dans la base, alors que "),
                          mv(s["ply"], s["best"]), T(" печели ", " scores ", " rapporte "), P(s["best_db"][2]), T(" (играе се в ", " (played in ", " (joué dans "),
                          P(s["best_db"][1]), T(" от партиите).</p>", " of games).</p>", " des parties).</p>")))

    # ---- 7. against the previous games
    cp = X.get("compare")
    if cp:
        a, t = cp["avg"], cp["this"]
        rows = [(T("Точност (вие)", "Accuracy (you)", "Précision (vous)"), "acc", True, 1),
                (T("Точност (противникът)", "Accuracy (opponent)", "Précision (adversaire)"), "acc_opp", None, 1),
                (T("Грешки и гафове", "Mistakes and blunders", "Erreurs et gaffes"), "errors", False, 1),
                (T("&nbsp;&nbsp;от тях гафове", "&nbsp;&nbsp;of which blunders", "&nbsp;&nbsp;dont gaffes"), "blunders", False, 1),
                (T("&nbsp;&nbsp;в дебюта", "&nbsp;&nbsp;in the opening", "&nbsp;&nbsp;dans l'ouverture"), "err_opening", False, 1),
                (T("&nbsp;&nbsp;в средата на играта", "&nbsp;&nbsp;in the middlegame", "&nbsp;&nbsp;au milieu de partie"), "err_middlegame", False, 1),
                (T("&nbsp;&nbsp;в ендшпила", "&nbsp;&nbsp;in the endgame", "&nbsp;&nbsp;en finale"), "err_endgame", False, 1),
                (T("Първа грешка на ход", "First mistake on move", "Première erreur au coup"), "first_error", True, 0),
                (T("Секунди на ход", "Seconds per move", "Secondes par coup"), "spent", None, 1)]
        html += ["<h3>", J(T("Спрямо предишните ", "Against your previous ", "Face à vos "), cp["games"], T(" партии", " games", " parties précédentes")), "</h3>",
                 '<div class="scroll"><table><tr><th></th><th>', T("Тази партия", "This game", "Cette partie"), "</th><th>",
                 J(T("Средно за ", "Average of ", "Moyenne de "), cp["games"], T(" партии", " games", " parties")), "</th></tr>"]
        for lab, k, up, d in rows:
            tv, av = t.get(k), a.get(k)
            tg = "n"
            if up is not None and tv is not None and av is not None:
                better = tv > av if up else tv < av
                tg = "w" if better and abs(tv - av) >= (3 if k == "acc" else 1 if k == "first_error" else 0.5) else "l" if not better and abs(tv - av) >= (3 if k == "acc" else 1 if k == "first_error" else 0.5) else "n"
            pct = k in ("acc", "acc_opp")
            show = (lambda v: P(v)) if pct else (lambda v: N(v, d))
            html += ["<tr><td>", lab, f'</td><td class="num"><span class="tag {tg}">', show(tv), '</span></td><td class="num">', show(av), "</td></tr>"]
        html.append("</table></div>")
        ph = max(("err_opening", "err_middlegame", "err_endgame"), key=lambda k: (t.get(k) or 0) - (a.get(k) or 0))
        phn = {"err_opening": T("дебюта", "the opening", "l'ouverture"), "err_middlegame": T("средата на играта", "the middlegame", "le milieu de partie"),
               "err_endgame": T("ендшпила", "the endgame", "la finale")}[ph]
        if (t.get("errors") or 0) >= 1.5 * (a.get("errors") or 0) + 1:
            html.append(J(T("<p>Грешките бяха повече от обикновено (", "<p>More mistakes than usual (", "<p>Plus d'erreurs que d'habitude ("), t["errors"],
                          T(" срещу средно ", " against an average of ", " contre une moyenne de "), N(a["errors"]),
                          T("), най-вече в ", "), above all in ", "), surtout dans "), phn, ".</p>"))
        elif (t.get("errors") or 0) + 1 <= (a.get("errors") or 0):
            html.append(T("<p>Грешките бяха по-малко от обикновено.</p>", "<p>Fewer mistakes than usual.</p>", "<p>Moins d'erreurs que d'habitude.</p>"))
    return J(*html), viewers
