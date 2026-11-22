"""A separate statistics-only report for the games since a date, each number set against an earlier period.

usage: python period_report.py USERNAME --dir OUT --since 2026.11.16 [--before-from 2026.10.23] [--out FILE]

Reads OUT/games.pgn, OUT/sf_games.json and OUT/sf_moves.json (run stats/sf_scan first). Writes the games since the date
to OUT/period_<since>/ (games.pgn, games.json, summary.json, report_spec.json) and builds the page there with
build_report.py (default OUT/period_<since>/report.html). The comparison period is the games from --before-from (default:
the start of the history) up to the day before --since. No opinions in the text: tables, the rating chart of the period,
and the "Style change" section of style_section.py.
"""
import argparse
import collections
import io
import json
import pathlib
import statistics as st
import subprocess
import sys

import chess.pgn

import stats as S
import style_section

HERE = pathlib.Path(__file__).resolve().parent
LANGS = ["bg", "en", "fr"]


def T(bg, en, fr):
    return {"bg": bg, "en": en, "fr": fr}


def J(*parts):
    return {lg: "".join(p[lg] if isinstance(p, dict) else str(p) for p in parts) for lg in LANGS}


def _d(s):
    y, m, dd = s.split(".")
    return f"{dd}.{m}.{y}"


def _pgn_since(text, since):
    out, f = [], io.StringIO(text)
    while (g := chess.pgn.read_game(f)) is not None:
        if g.headers.get("UTCDate", g.headers.get("Date", "")) >= since:
            out.append(str(g))
    return "\n\n".join(out) + "\n"


def _mean(xs, nd=1):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), nd) if xs else None


def _pct(k, n):
    return round(100 * k / n) if n else None


def metrics(rows, sg):
    n = len(rows)
    g = [sg.get(r["link"]) for r in rows]
    gs = [x for x in g if x]
    cls = lambda x, c: x.get("classes", {}).get(c, 0)
    pe = lambda x, p: x.get("phase_errors", {}).get(p, 0)
    L = [r for r in rows if r["outcome"] == "loss"]
    W = [r for r in rows if r["outcome"] == "win"]
    days = collections.Counter(r["date"] for r in rows)
    main = collections.Counter(r["time_class"] for r in rows).most_common(1)[0][0]
    rated = [r["my_elo"] for r in rows if r["time_class"] == main and r["my_elo"]]
    t = S.tilt(rows)
    fe = [x["first_error_move"] for x in gs if x.get("first_error_move")]
    return dict(
        n=n, days=len(days), per_day=round(n / max(1, len(days)), 1), max_day=max(days.values()),
        score=S.pct(rows), w=len(W), d=sum(r["outcome"] == "draw" for r in rows), l=len(L),
        white=S.pct([r for r in rows if r["color"] == "white"]), black=S.pct([r for r in rows if r["color"] == "black"]),
        r_first=rated[0] if rated else None, r_last=rated[-1] if rated else None,
        r_max=max(rated) if rated else None, r_min=min(rated) if rated else None,
        opp=round(st.mean(r["opp_elo"] for r in rows if r["opp_elo"])) if any(r["opp_elo"] for r in rows) else None,
        moves=round(st.mean(r["plies"] for r in rows) / 2),
        acc=_mean(x["acc"] for x in gs), acc_opp=_mean(x.get("acc_opp") for x in gs),
        blund=_mean([cls(x, "blunder") for x in gs], 2), mist=_mean([cls(x, "mistake") for x in gs], 2),
        inacc=_mean([cls(x, "inaccuracy") for x in gs], 2),
        clean=_pct(sum(1 for x in gs if not cls(x, "blunder") and not cls(x, "mistake")), len(gs)),
        e_open=_mean([pe(x, "opening") for x in gs], 2), e_mid=_mean([pe(x, "middlegame") for x in gs], 2),
        e_end=_mean([pe(x, "endgame") for x in gs], 2),
        first_err=st.median(fe) if fe else None,
        exit_wp=_mean(x.get("exit_wp") for x in gs), spent=_mean(x.get("avg_spent") for x in gs),
        tt=_pct(sum(1 for x in gs if x.get("time_trouble")), len(gs)),
        mated=_pct(sum(r["how"] == "checkmate" for r in L), len(L)), resigned=_pct(sum(r["how"] == "resignation" for r in L), len(L)),
        l_time=_pct(sum(r["how"] == "time" for r in L), len(L)),
        qlost=_pct(sum(bool(r["qlost"]) for r in L), len(L)), short=_pct(sum(r["plies"] <= 30 for r in L), len(L)),
        w_mate=_pct(sum(r["how"] == "checkmate" for r in W), len(W)), w_resign=_pct(sum(r["how"] == "resignation" for r in W), len(W)),
        w_time=_pct(sum(r["how"] == "time" for r in W), len(W)),
        t_win=t["after_win"], t_1=t["after_1_loss"], t_2=t["after_2_losses"],
        gd=t["by_game_of_day"],
    )


def fmt(v, unit=""):
    if v is None:
        return "–"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f"{v}{unit}"


def arrow(a, b, better):
    """better: +1 if higher is better, -1 if lower is better, 0 neutral."""
    if a is None or b is None or a == b or better == 0:
        return '<td class="num"></td>'
    up = b > a
    good = up == (better > 0)
    return f'<td class="num"><span class="tag {"w" if good else "l"}">{"▲" if up else "▼"} {fmt(round(abs(b - a), 2))}</span></td>'


def table(head_old, head_new, lines):
    out = [J('<div class="scroll"><table><tr><th></th><th>', head_old, "</th><th>", head_new, "</th><th>",
             T("Промяна", "Change", "Évolution"), "</th></tr>")]
    for lab, a, b, unit, better in lines:
        out.append(J("<tr><td>", lab, f'</td><td class="num">{fmt(a, unit)}</td><td class="num">{fmt(b, unit)}</td>',
                     arrow(a, b, better), "</tr>"))
    out.append("</table></div>")
    return J(*out)


def rec_cell(r):
    return "–" if not r or not r["n"] else f'{r["score_pct"]}% <span class="hint">({r["n"]})</span>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--since", required=True, help="first day of the new period, YYYY.MM.DD")
    ap.add_argument("--before-from", help="first day of the comparison period (default: the whole history before --since)")
    ap.add_argument("--out", help="HTML file (default OUT/period_<since>/report.html)")
    a = ap.parse_args()
    me = a.username.strip().lower()
    D = pathlib.Path(a.dir)
    P = D / f"period_{a.since.replace('.', '-')}"
    P.mkdir(exist_ok=True)
    text = (D / "games.pgn").read_text(encoding="utf-8")
    (P / "games.pgn").write_text(_pgn_since(text, a.since), encoding="utf-8")
    allrows = S.rows_from(text, me)
    new = [r for r in allrows if r["date"] >= a.since]
    old = [r for r in allrows if r["date"] < a.since and (a.before_from is None or r["date"] >= a.before_from)]
    if len(new) < 5 or len(old) < 5:
        raise SystemExit(f"Too few games: {len(old)} before, {len(new)} since {a.since}")
    for k, r in enumerate(new, 1):
        r["n"] = k
    (P / "games.json").write_text(json.dumps(new, ensure_ascii=False, indent=0), encoding="utf-8")
    (P / "summary.json").write_text(json.dumps(S.summary(new), ensure_ascii=False, indent=1), encoding="utf-8")
    sg = {x["link"]: x for x in json.loads((D / "sf_games.json").read_text(encoding="utf-8"))}
    o, n = metrics(old, sg), metrics(new, sg)
    span = lambda rs: f"{_d(rs[0]['date'])} – {_d(rs[-1]['date'])}"
    ho = J(T("Преди", "Before", "Avant"), f'<br><span class="hint">{span(old)} · {len(old)}</span>')
    hn = J(T("След", "Since", "Depuis"), f'<br><span class="hint">{span(new)} · {len(new)}</span>')

    secs = []
    # 1. results
    res = table(ho, hn, [
        (T("Партии на ден (средно)", "Games a day (average)", "Parties par jour (moyenne)"), o["per_day"], n["per_day"], "", 0),
        (T("Най-много партии за ден", "Most games in a day", "Le plus de parties en un jour"), o["max_day"], n["max_day"], "", 0),
        (T("Успеваемост", "Score", "Score"), o["score"], n["score"], "%", 1),
        (T("Победи / равни / загуби", "Wins / draws / losses", "Victoires / nulles / défaites"), None, None, "", 0),
        (T("С белите", "With White", "Avec les Blancs"), o["white"], n["white"], "%", 1),
        (T("С черните", "With Black", "Avec les Noirs"), o["black"], n["black"], "%", 1),
        (T("Рейтинг в началото", "Rating at the start", "Classement au début"), o["r_first"], n["r_first"], "", 0),
        (T("Рейтинг в края", "Rating at the end", "Classement à la fin"), o["r_last"], n["r_last"], "", 1),
        (T("Най-висок / най-нисък рейтинг", "Highest / lowest rating", "Classement max / min"), None, None, "", 0),
        (T("Среден рейтинг на противника", "Average opponent rating", "Classement moyen de l'adversaire"), o["opp"], n["opp"], "", 0),
        (T("Ходове на партия (средно)", "Moves a game (average)", "Coups par partie (moyenne)"), o["moves"], n["moves"], "", 0),
    ])
    # fill in the two text rows (no numeric change), in table order
    for lg in LANGS:
        res[lg] = res[lg].replace('<td class="num">–</td><td class="num">–</td><td class="num"></td>',
                                  f'<td class="num">{o["w"]} / {o["d"]} / {o["l"]}</td><td class="num">{n["w"]} / {n["d"]} / {n["l"]}</td><td class="num"></td>', 1)
        res[lg] = res[lg].replace('<td class="num">–</td><td class="num">–</td><td class="num"></td>',
                                  f'<td class="num">{o["r_max"]} / {o["r_min"]}</td><td class="num">{n["r_max"]} / {n["r_min"]}</td><td class="num"></td>', 1)
    days = collections.OrderedDict()
    for r in new:
        days.setdefault(r["date"], []).append(r)
    drows = []
    for dt, rs in days.items():
        acc = _mean(sg[r["link"]]["acc"] for r in rs if r["link"] in sg)
        el = [r["my_elo"] for r in rs if r["my_elo"]]
        drows.append(f'<tr><td>{_d(dt)}</td><td class="num">{len(rs)}</td><td class="num">'
                     f'{sum(r["outcome"] == "win" for r in rs)} / {sum(r["outcome"] == "draw" for r in rs)} / {sum(r["outcome"] == "loss" for r in rs)}</td>'
                     f'<td class="num">{S.pct(rs)}%</td><td class="num">{fmt(acc, "%")}</td>'
                     f'<td class="num">{el[0] if el else "–"} → {el[-1] if el else "–"}</td></tr>')
    daytab = J('<h3>', T("По дни", "By day", "Par jour"), '</h3><div class="scroll"><table><tr><th>', T("Ден", "Day", "Jour"),
               "</th><th>", T("Партии", "Games", "Parties"), "</th><th>", T("П / Р / З", "W / D / L", "V / N / D"), "</th><th>",
               T("Успеваемост", "Score", "Score"), "</th><th>", T("Точност", "Accuracy", "Précision"), "</th><th>",
               T("Рейтинг", "Rating", "Classement"), "</th></tr>", "".join(drows), "</table></div>")
    secs.append(dict(id="results", title=T("1. Резултати", "1. Results", "1. Résultats"), toc_title=T("Резултати", "Results", "Résultats"),
                     html=J("{{CHART}}", res, daytab)))

    # 2. style change
    sec_st, viewers = style_section.build(D, me, since=a.since, before_from=a.before_from)
    if sec_st:
        sec_st["title"] = J("2. ", sec_st["title"])
        secs.append(sec_st)

    # 3. accuracy and mistakes
    acc = table(ho, hn, [
        (T("Точност", "Accuracy", "Précision"), o["acc"], n["acc"], "%", 1),
        (T("Точност на противника", "Opponent's accuracy", "Précision de l'adversaire"), o["acc_opp"], n["acc_opp"], "%", -1),
        (T("Груби грешки на партия", "Blunders a game", "Gaffes par partie"), o["blund"], n["blund"], "", -1),
        (T("Грешки на партия", "Mistakes a game", "Erreurs par partie"), o["mist"], n["mist"], "", -1),
        (T("Неточности на партия", "Inaccuracies a game", "Imprécisions par partie"), o["inacc"], n["inacc"], "", -1),
        (T("Партии без грешка и груба грешка", "Games without a mistake or blunder", "Parties sans erreur ni gaffe"), o["clean"], n["clean"], "%", 1),
        (T("Грешки в дебюта (на партия)", "Mistakes in the opening (a game)", "Erreurs dans l'ouverture (par partie)"), o["e_open"], n["e_open"], "", -1),
        (T("Грешки в средата на партията", "Mistakes in the middlegame", "Erreurs en milieu de partie"), o["e_mid"], n["e_mid"], "", -1),
        (T("Грешки в ендшпила", "Mistakes in the endgame", "Erreurs en finale"), o["e_end"], n["e_end"], "", -1),
        (T("Първа грешка на ход (медиана)", "First mistake on move (median)", "Première erreur au coup (médiane)"), o["first_err"], n["first_err"], "", 1),
        (T("Шанс след 10-ия ход", "Chances after move 10", "Chances après le 10e coup"), o["exit_wp"], n["exit_wp"], "%", 1),
        (T("Секунди на ход (средно)", "Seconds a move (average)", "Secondes par coup (moyenne)"), o["spent"], n["spent"], "", 0),
        (T("Партии с недостиг на време", "Games in time trouble", "Parties en zeitnot"), o["tt"], n["tt"], "%", -1),
    ])
    secs.append(dict(id="accuracy", title=T("3. Точност и грешки", "3. Accuracy and mistakes", "3. Précision et erreurs"),
                     toc_title=T("Точност", "Accuracy", "Précision"),
                     html=J(T("<p>По Stockfish. Груба грешка = спад на шанса с 30% или повече, грешка = 20–30%, неточност = 10–20%.</p>",
                              "<p>By Stockfish. Blunder = a drop of 30% or more in winning chances, mistake = 20–30%, inaccuracy = 10–20%.</p>",
                              "<p>Selon Stockfish. Gaffe = baisse des chances de 30 % ou plus, erreur = 20–30 %, imprécision = 10–20 %.</p>"), acc)))

    # 4. how games end
    end = table(ho, hn, [
        (T("Загуби с мат", "Losses by mate", "Défaites par mat"), o["mated"], n["mated"], "%", -1),
        (T("Загуби с предаване", "Losses by resignation", "Défaites par abandon"), o["resigned"], n["resigned"], "%", 0),
        (T("Загуби на време", "Losses on time", "Défaites au temps"), o["l_time"], n["l_time"], "%", -1),
        (T("Загуби с изгубена царица", "Losses with the queen lost", "Défaites avec la dame perdue"), o["qlost"], n["qlost"], "%", -1),
        (T("Загуби до 15-ия ход", "Losses within 15 moves", "Défaites en 15 coups ou moins"), o["short"], n["short"], "%", -1),
        (T("Победи с мат", "Wins by mate", "Victoires par mat"), o["w_mate"], n["w_mate"], "%", 0),
        (T("Победи с предаване", "Wins by resignation", "Victoires par abandon"), o["w_resign"], n["w_resign"], "%", 0),
        (T("Победи на време", "Wins on time", "Victoires au temps"), o["w_time"], n["w_time"], "%", 0),
    ])
    secs.append(dict(id="endings", title=T("4. Как свършват партиите", "4. How games end", "4. Comment finissent les parties"),
                     toc_title=T("Край на партиите", "Endings", "Fins"),
                     html=J(T("<p>Процент от загубите (горе) и от победите (долу).</p>", "<p>Share of the losses (top) and of the wins (bottom).</p>",
                              "<p>Part des défaites (en haut) et des victoires (en bas).</p>"), end)))

    # 5. openings
    def op_rows(sel_old, sel_new, key, label_of):
        c = collections.Counter(key(r) for r in sel_new if key(r))
        out = []
        for k, _ in c.most_common(6):
            ro = S.rec([r for r in sel_old if key(r) == k])
            rn = S.rec([r for r in sel_new if key(r) == k])
            out.append(f'<tr><td>{label_of(k)}</td><td class="num">{rec_cell(ro)}</td><td class="num">{rec_cell(rn)}</td></tr>')
        return "".join(out)

    first = lambda r, i: r["first"][i] if len(r["first"]) > i else None
    ow, nw = [r for r in old if r["color"] == "white"], [r for r in new if r["color"] == "white"]
    ob, nb = [r for r in old if r["color"] == "black"], [r for r in new if r["color"] == "black"]
    head = J('<div class="scroll"><table><tr><th></th><th>', ho, "</th><th>", hn, "</th></tr>")
    ops = J(T("<p>Успеваемост и брой партии.</p>", "<p>Score and number of games.</p>", "<p>Score et nombre de parties.</p>"),
            "<h3>", T("С белите: първи ход и отговор", "With White: first move and reply", "Avec les Blancs : premier coup et réponse"), "</h3>", head,
            op_rows(ow, nw, lambda r: " ".join(r["first"][:2]) if len(r["first"]) > 1 else None, lambda k: f"1.{k.split()[0]} {k.split()[1]}"),
            "</table></div>")
    for opp_first in ("e4", "d4"):
        so = [r for r in ob if first(r, 0) == opp_first]
        sn = [r for r in nb if first(r, 0) == opp_first]
        if sn:
            ops = J(ops, "<h3>", T(f"С черните срещу 1.{opp_first}", f"With Black against 1.{opp_first}", f"Avec les Noirs contre 1.{opp_first}"), "</h3>", head,
                    op_rows(so, sn, lambda r: first(r, 1), lambda k: f"1...{k}"), "</table></div>")
    secs.append(dict(id="openings", title=T("5. Дебюти", "5. Openings", "5. Ouvertures"), toc_title=T("Дебюти", "Openings", "Ouvertures"),
                     html=ops))

    # 6. tilt and volume
    tl = J('<div class="scroll"><table><tr><th></th><th>', ho, "</th><th>", hn, "</th></tr>")
    for lab, k in [(T("След победа", "After a win", "Après une victoire"), "t_win"), (T("След 1 загуба", "After 1 loss", "Après 1 défaite"), "t_1"),
                   (T("След 2 загуби подред", "After 2 losses in a row", "Après 2 défaites de suite"), "t_2")]:
        tl = J(tl, "<tr><td>", lab, f'</td><td class="num">{rec_cell(o[k])}</td><td class="num">{rec_cell(n[k])}</td></tr>')
    for lab, k in [(T("Партии 1–5 за деня", "Games 1–5 of the day", "Parties 1–5 de la journée"), "games_1_5"),
                   (T("Партии 6–20 за деня", "Games 6–20 of the day", "Parties 6–20 de la journée"), "games_6_20"),
                   (T("Партия 21 и нататък", "Game 21 and later", "Partie 21 et suivantes"), "games_21_plus")]:
        tl = J(tl, "<tr><td>", lab, f'</td><td class="num">{rec_cell(o["gd"].get(k))}</td><td class="num">{rec_cell(n["gd"].get(k))}</td></tr>')
    tl = J(tl, "</table></div>")
    secs.append(dict(id="tilt", title=T("6. След загуба и много партии", "6. After a loss and long days", "6. Après une défaite et longues journées"),
                     toc_title=T("Тилт", "Tilt", "Tilt"),
                     html=J(T("<p>Успеваемост на следващата партия в същия ден и според това коя поред е партията за деня.</p>",
                              "<p>Score of the next game on the same day, and by the game's place in the day.</p>",
                              "<p>Score de la partie suivante le même jour, et selon le rang de la partie dans la journée.</p>"), tl)))

    spec = {
        "langs": LANGS, "piece_words": "both", "background": "night",
        "title": T(f"Статистика от {_d(a.since)}: {a.username}", f"Statistics since {_d(a.since)}: {a.username}", f"Statistiques depuis le {_d(a.since)} : {a.username}"),
        "page_title": T(f"{a.username} от {_d(a.since)}", f"{a.username} since {_d(a.since)}", f"{a.username} depuis le {_d(a.since)}"),
        "subtitle": T(f"{len(new)} партии ({span(new)}) срещу {len(old)} преди ({span(old)})",
                      f"{len(new)} games ({span(new)}) vs {len(old)} before ({span(old)})",
                      f"{len(new)} parties ({span(new)}) contre {len(old)} avant ({span(old)})"),
        "tiles": [
            {"value": f'{n["r_first"]} → {n["r_last"]}', "label": T("Рейтинг", "Rating", "Classement")},
            {"value": f'{n["score"]}%', "label": T(f"Успеваемост (преди {o['score']}%)", f"Score (before {o['score']}%)", f"Score (avant {o['score']} %)")},
            {"value": f'{n["acc"]}%', "label": T(f"Точност (преди {o['acc']}%)", f"Accuracy (before {o['acc']}%)", f"Précision (avant {o['acc']} %)")},
            {"value": str(len(new)), "label": T(f"Партии за {n['days']} дни", f"Games in {n['days']} days", f"Parties en {n['days']} jours")},
        ],
        "summary_html": T("<p>Само числа: всяка таблица сравнява партиите след началото на смяната на стила с тези преди това. "
                          "Зелената стрелка е подобрение, червената – влошаване.</p>",
                          "<p>Numbers only: every table compares the games since the style change began with the games before it. "
                          "A green arrow is an improvement, a red one a step back.</p>",
                          "<p>Uniquement des chiffres : chaque tableau compare les parties depuis le changement de style avec celles d'avant. "
                          "Une flèche verte est un progrès, une rouge un recul.</p>"),
        "sections": secs, "viewers": viewers,
        "footer_html": T("Данни: публичното API на chess.com, Stockfish.", "Data: chess.com public API, Stockfish.", "Données : API publique chess.com, Stockfish."),
    }
    (P / "report_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    out = a.out or str(P / "report.html")
    subprocess.run([sys.executable, str(HERE / "build_report.py"), "--dir", str(P), "--spec", str(P / "report_spec.json"), "--out", out], check=True)
    print(f"{len(old)} games before, {len(new)} since {a.since} -> {out}")


if __name__ == "__main__":
    main()
