"""Build the game-analysis pages from the skill's game_analysis/ archive (archive_game.py).

    python game_index.py USERNAME --out DIR [--home index.html]

Writes into DIR:
  games.html          every analysed game, newest first: date, colour, opponent and ratings, result and how it
                      ended, opening, moves, accuracy, mistakes; a click on a row opens that game's page
  game-<id>.html      one page per game (its analysis, boards and puzzles), with links back to the main report
                      and to games.html
The main report links to games.html (spec "games_page"); every page links back to --home (the main report's file
name next to these pages: index.html for the published artifact, report.html in a local folder).
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

import chess.pgn

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "game_analysis"
LANGS = ("bg", "en", "fr")
PER = 15  # games per page in the list


def T(bg, en, fr):
    return {"bg": bg, "en": en, "fr": fr}


HOW = [("checkmate", T("мат", "checkmate", "mat")), ("resignation", T("предаване", "resignation", "abandon")),
       ("on time", T("на време", "on time", "au temps")), ("abandoned", T("напускане", "abandoned", "partie quittée")),
       ("repetition", T("повторение", "repetition", "répétition")), ("agreement", T("споразумение", "agreement", "accord")),
       ("stalemate", T("пат", "stalemate", "pat")), ("insufficient", T("недостатъчно фигури", "insufficient material", "matériel insuffisant")),
       ("timeout vs insufficient", T("време срещу недостатъчно фигури", "timeout vs insufficient material", "temps contre matériel insuffisant"))]
RES = {"w": T("победа", "win", "victoire"), "l": T("загуба", "loss", "défaite"), "d": T("реми", "draw", "nulle")}


def info(folder, me):
    g = chess.pgn.read_game(open(folder / "game.pgn", encoding="utf-8"))
    h = g.headers
    white = h.get("White", "").lower() == me
    res = h.get("Result", "*")
    r = "d" if res == "1/2-1/2" else ("w" if (res == "1-0") == white else "l")
    term = h.get("Termination", "").lower()
    how = next((v for k, v in reversed(HOW) if k in term), T("", "", ""))
    sf = json.loads((folder / "sf_last.json").read_text(encoding="utf-8")) if (folder / "sf_last.json").exists() else {}
    ex = json.loads((folder / "last_extra.json").read_text(encoding="utf-8")) if (folder / "last_extra.json").exists() else {}
    mine = [m for m in sf.get("moves", []) if m.get("mine")]
    opening = h.get("ECOUrl", "").rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
    plies = len(list(g.mainline_moves()))
    return {"id": h.get("Link", "").rstrip("/").rsplit("/", 1)[-1], "folder": folder, "white": white, "r": r, "how": how,
            "when": f"{h.get('UTCDate', '')} {h.get('UTCTime', '')}", "date": h.get("UTCDate", "").replace(".", "-"),
            "opp": h["Black"] if white else h["White"], "opp_elo": h.get("BlackElo" if white else "WhiteElo", ""),
            "my_elo": h.get("WhiteElo" if white else "BlackElo", ""), "eco": h.get("ECO", ""), "opening": opening,
            "moves": (plies + 1) // 2, "acc": sf.get("accuracy"), "acc_opp": sf.get("accuracy_opp"),
            "blunders": sum(1 for m in mine if m.get("class") == "blunder"),
            "mistakes": sum(1 for m in mine if m.get("class") == "mistake"),
            "puzzles": len(ex.get("moments", [])), "link": h.get("Link", "")}


def build(spec, pgn, out_html):
    """Run build_report.py on a spec in a temporary folder (the game's PGN as last.pgn)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        if pgn:
            shutil.copyfile(pgn, tmp / "last.pgn")
        (tmp / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_report.py"), "--dir", str(tmp), "--spec", str(tmp / "spec.json"),
                            "--out", str(out_html)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            raise RuntimeError(r.stdout + r.stderr)


def add_opening_boards(spec, folder):
    """Games archived before the opening boards existed: add them from the archived last_extra.json, after the opening paragraphs;
    a game without the opening block at all gets the whole block (text and boards), before the comparison with earlier games."""
    ga = spec.get("game_analysis") or {}
    ex_file = folder / "last_extra.json"
    if not isinstance(ga.get("html"), dict) or not ex_file.exists() or "{{V:lgo" in json.dumps(ga["html"], ensure_ascii=False):
        return
    sys.path.insert(0, str(ROOT / "scripts"))
    import last_game_section as lgs
    X = json.loads(ex_file.read_text(encoding="utf-8"))
    boards, viewers = lgs.opening_boards(X)
    whole, whole_viewers = lgs.opening_html(X)
    whole = lgs.J(*whole) if whole else None
    compare_heads = {"bg": "<h3>Спрямо предишните", "en": "<h3>Against your previous", "fr": "<h3>Face à vos"}
    used = {}
    for lg, text in list(ga["html"].items()):
        head = lgs.OPENING_HEADS.get(lg)
        i = text.find(head) if head else -1
        if i >= 0 and viewers:  # the text is there: add the boards after it
            j = text.find("<h3>", i)
            j = len(text) if j < 0 else j
            ga["html"][lg] = text[:j] + boards[lg] + text[j:]
            used.update(viewers)
        elif i < 0 and whole:  # no opening block yet
            j = text.find(compare_heads.get(lg, "@@none@@"))
            j = len(text) if j < 0 else j
            ga["html"][lg] = text[:j] + whole[lg] + text[j:]
            used.update(whole_viewers)
    if used:
        spec["viewers"] = dict(spec.get("viewers") or {}, **used)


def nav(home, games=True):
    """Links back to the main report (and to the games list)."""
    a = f'<a href="{home}">'
    b = '<a href="games.html">'
    return T(f'{a}&larr; Към основния репорт</a>' + (f' &middot; {b}Всички анализирани партии</a>' if games else ""),
             f'{a}&larr; Back to the main report</a>' + (f' &middot; {b}All analysed games</a>' if games else ""),
             f'{a}&larr; Retour au rapport principal</a>' + (f' &middot; {b}Toutes les parties analysées</a>' if games else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--out", required=True)
    ap.add_argument("--home", default="index.html", help="file name of the main report next to these pages")
    ap.add_argument("--all", action="store_true", help="rebuild every game page, not only new or changed ones")
    a = ap.parse_args()
    me, out = a.username.strip().lower(), pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    games = [info(f, me) for f in sorted(ARCHIVE.iterdir()) if (f / "analysis_spec.json").exists() and (f / "game.pgn").exists()]
    games.sort(key=lambda x: x["when"], reverse=True)
    if not games:
        sys.exit("no archived games")
    base = json.loads((games[0]["folder"] / "analysis_spec.json").read_text(encoding="utf-8"))
    langs = base.get("langs") or ["en"]

    # one page per game; a page newer than its archive files and this script is kept (--all rebuilds every page)
    built = 0
    newest_code = max((ROOT / "scripts" / n).stat().st_mtime for n in ("game_index.py", "build_report.py", "last_game_section.py"))
    for gm in games:
        page = out / f"game-{gm['id']}.html"
        src = max((gm["folder"] / n).stat().st_mtime for n in ("analysis_spec.json", "game.pgn"))
        if not a.all and page.exists() and page.stat().st_mtime > max(src, newest_code):
            continue
        built += 1
        raw = (gm["folder"] / "analysis_spec.json").read_text(encoding="utf-8")
        # in the archive every game is just "the game", not "the latest game"
        for old, new in (("Последна партия", "Партия"), ("Latest game", "Game"), ("Dernière partie", "Partie"), ("Анализ на партия: ", "Партия: ")):
            raw = raw.replace(old, new)
        spec = json.loads(raw)
        spec["subtitle"] = nav(a.home)
        add_opening_boards(spec, gm["folder"])
        build(spec, gm["folder"] / "game.pgn", out / f"game-{gm['id']}.html")

    # the list
    th = lambda *c: "".join(f"<th>{x}</th>" for x in c)
    head = {lg: "<tr>" + th(*[{"bg": b, "en": e, "fr": f}[lg] for b, e, f in [
        ("Дата", "Date", "Date"), ("Цвят", "Colour", "Couleur"), ("Противник", "Opponent", "Adversaire"), ("Резултат", "Result", "Résultat"),
        ("Дебют", "Opening", "Ouverture"), ("Ходове", "Moves", "Coups"), ("Точност", "Accuracy", "Précision"),
        ("Гафове / грешки", "Blunders / mistakes", "Gaffes / erreurs"), ("Задачи", "Puzzles", "Problèmes")]]) + "</tr>" for lg in LANGS}
    rows = {lg: [] for lg in LANGS}
    for gm in games:
        page = f"game-{gm['id']}.html"
        tag = {"w": "w", "l": "l", "d": "n"}[gm["r"]]
        for lg in LANGS:
            col = {"bg": ("белите", "черните"), "en": ("White", "Black"), "fr": ("Blancs", "Noirs")}[lg][0 if gm["white"] else 1]
            piece = "&#9675;" if gm["white"] else "&#9679;"  # empty / full circle
            how = gm["how"][lg]
            acc = (f'{gm["acc"]:.0f}' if gm["acc"] is not None else "–") + " / " + (f'{gm["acc_opp"]:.0f}' if gm["acc_opp"] is not None else "–")
            rows[lg].append(
                f'<tr class="game-row" data-href="{page}" tabindex="0">'
                f'<td class="num">{gm["date"]}</td><td>{piece} {col}</td>'
                f'<td><a href="{page}">{gm["opp"]}</a> <span class="hint">({gm["opp_elo"]})</span><br><span class="hint">'
                + {"bg": "вие", "en": "you", "fr": "vous"}[lg] + f' {gm["my_elo"]}</span></td>'
                f'<td><span class="tag {tag}">{RES[gm["r"]][lg]}</span>' + (f'<br><span class="hint">{how}</span>' if how else "") + "</td>"
                f'<td>{gm["eco"]}<br><code class="op">{gm["opening"]}</code></td><td class="num">{gm["moves"]}</td>'
                f'<td class="num">{acc}</td><td class="num">{gm["blunders"]} / {gm["mistakes"]}</td><td class="num">{gm["puzzles"]}</td></tr>')
    n = len(games)
    w, l, d = (sum(1 for g in games if g["r"] == k) for k in "wld")
    html = {lg: ({"bg": f"<p>{n} анализирани партии, от най-новата към най-старата ({w} победи, {l} загуби, {d} реми). Кликнете ред, за да отворите анализа.</p>",
                  "en": f"<p>{n} analysed games, newest first ({w} wins, {l} losses, {d} draws). Click a row to open the analysis.</p>",
                  "fr": f"<p>{n} parties analysées, de la plus récente à la plus ancienne ({w} victoires, {l} défaites, {d} nulles). Cliquez une ligne pour ouvrir l'analyse.</p>"}[lg]
                 + {"bg": '<p class="hint">Точност: вие / противникът (Stockfish). Гафове и грешки: вашите ходове, които губят 20% / 10–20% от шанса за победа.</p>',
                    "en": '<p class="hint">Accuracy: you / the opponent (Stockfish). Blunders and mistakes: your moves that lose 20% / 10–20% of the winning chances.</p>',
                    "fr": '<p class="hint">Précision : vous / l\'adversaire (Stockfish). Gaffes et erreurs : vos coups qui perdent 20 % / 10–20 % des chances de gain.</p>'}[lg]
                 + '<style>.game-row{cursor:pointer}.game-row:hover td{background:var(--hover)}.game-row:focus-visible{outline:2px solid var(--accent)}.pager{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:12px}.pager button{min-width:36px;height:34px;border-radius:8px;border:1px solid var(--border-strong);background:var(--surface-2);color:var(--ink);font:600 14px var(--font);cursor:pointer}.pager button.on{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}.pager button:disabled{opacity:.35;cursor:default}.pager .hint{margin-left:8px}code.op{font:inherit;font-size:13px;color:var(--muted);background:none;padding:0;border:0}</style>'
                 + '<div class="scroll"><table>' + head[lg] + "".join(rows[lg]) + "</table></div>"
                 + '<div class="pager"></div>'
                 + "<script>document.querySelectorAll('.game-row').forEach(function(r){var go=function(){location.href=r.dataset.href;};"
                   "r.addEventListener('click',function(e){if(!e.target.closest('a'))go();});r.addEventListener('keydown',function(e){if(e.key==='Enter')go();});});"
                   # pagination: PER rows a page, buttons below the table, the page kept in the URL (#p2)
                   "document.querySelectorAll('main').forEach(function(m){var rows=[].slice.call(m.querySelectorAll('.game-row')),pg=m.querySelector('.pager'),PER=" + str(PER) + ","
                   "n=Math.ceil(rows.length/PER);if(!pg||n<2)return;var cur=0;"
                   "function show(i){cur=Math.max(0,Math.min(n-1,i));rows.forEach(function(r,k){r.hidden=Math.floor(k/PER)!==cur;});"
                   "pg.innerHTML='';var b=function(t,i,dis,act){var x=document.createElement('button');x.type='button';x.textContent=t;x.disabled=dis;if(act)x.className='on';"
                   "x.addEventListener('click',function(){show(i);history.replaceState(null,'','#p'+(i+1));m.querySelector('table').scrollIntoView({block:'start'});});pg.appendChild(x);};"
                   "b('\u2039',cur-1,cur===0);for(var i=0;i<n;i++)b(String(i+1),i,false,i===cur);b('\u203A',cur+1,cur===n-1);"
                   "var s=document.createElement('span');s.className='hint';s.textContent=(cur*PER+1)+'\u2013'+Math.min(rows.length,(cur+1)*PER)+' / '+rows.length;pg.appendChild(s);}"
                   "var h=/^#p([0-9]+)$/.exec(location.hash);show(h?+h[1]-1:0);});</script>")
            for lg in LANGS}
    spec = {k: base[k] for k in ("langs", "lang", "piece_words", "labels") if k in base}
    spec.update({"title": T("Анализ на партиите", "Game analyses", "Analyses de parties"), "subtitle": nav(a.home, games=False), "tiles": [],
                 "sections": [{"id": "games", "title": T("Анализирани партии", "Analysed games", "Parties analysées"),
                               "toc_title": T("Партии", "Games", "Parties"), "html": html}], "viewers": {}})
    build(spec, None, out / "games.html")
    print(f"games.html written, {built} of {len(games)} game pages (re)built in {out}")


if __name__ == "__main__":
    main()
