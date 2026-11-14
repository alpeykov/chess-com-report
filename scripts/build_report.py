"""Assemble the single-file HTML report from a spec written by Claude.

usage: python build_report.py --dir OUT [--spec OUT/report_spec.json] [--out OUT/report.html]

The spec format is described in references/spec_format.md. Placeholders allowed inside any html field:
  {{CHART}}                      rating chart (main time class) from games.json
  {{V:viewer_id}}                step-through board defined in spec["viewers"]
  {{GOTO:viewer_id:frame:text}}  button that jumps that board to a frame (frame = ply + 1)
"""
import argparse
import html as H
import io
import json
import pathlib
import re
import chess
import chess.pgn
import chess.svg

COLORS = {"square light": "#f0d9b5", "square dark": "#b58863",
          "square light lastmove": "#f6eb72", "square dark lastmove": "#dcc34b"}
ARROW = {"green": "#15781B90", "red": "#D0201090", "blue": "#2050C080", "yellow": "#E0A00090"}
DEFS_RE = re.compile(r"<defs>.*?</defs>", re.S)

LABELS = {
    "en": dict(start="Start", move="Move", play="Play", pause="Pause", first="To start", prev="Back", next="Forward",
               last="To end", show="Show on the board", win="win", loss="loss", draw="draw", white="White", black="Black",
               game="Game", rating="Rating", now="Now", peak="Peak", vs="vs", axis="Games in order",
               chart="Rating, game by game", contents="Contents", game_analysis="Game analysis"),
    "fr": dict(start="Début", move="Coup", play="Lecture", pause="Pause", first="Au début", prev="Retour", next="Suivant",
               last="À la fin", show="Afficher sur l'échiquier", win="victoire", loss="défaite", draw="nulle",
               white="Blancs", black="Noirs", game="Partie", rating="Classement", now="Actuel", peak="Max", vs="contre",
               axis="Parties dans l'ordre", chart="Classement, partie par partie", contents="Sommaire",
               game_analysis="Analyse de partie"),
    "bg": dict(start="Начало", move="Ход", play="Пусни", pause="Пауза", first="Към началото", prev="Назад", next="Напред",
               last="Към края", show="Покажи хода на дъската", win="победа", loss="загуба", draw="реми", white="белите",
               black="черните", game="Партия", rating="Рейтинг", now="Сега", peak="Връх", vs="срещу",
               axis="Партии по ред", chart="Рейтинг, партия по партия", contents="Съдържание",
               game_analysis="Анализ на партия"),
}

CSS = """
:root{color-scheme:dark;--page:#262421;--surface:#312e2b;--surface-2:#1f1d1b;--ink:#f0efec;--ink-2:#c9c7bf;--muted:#8f8c84;
--accent:#81b64c;--accent-ink:#9ec27f;--good:#2fae2f;--bad:#d64545;--border:rgba(255,255,255,.08);--border-strong:rgba(255,255,255,.16);
--hover:#3a3733;--grid:#34312d;--axis:#45413c;--series:#5b9ee9}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1120px;margin:0 auto;padding:32px max(16px,env(safe-area-inset-right,0px)) 64px max(16px,env(safe-area-inset-left,0px))}
h1{font-size:30px;margin:0 0 4px;text-wrap:balance}
h2{font-size:23px;margin:48px 0 8px;padding-top:12px;border-top:1px solid var(--border);text-wrap:balance;scroll-margin-top:12px}
h3{font-size:18px;margin:24px 0 6px}p,li{color:var(--ink-2);max-width:75ch}b,strong{color:var(--ink)}
a{color:var(--series)}.sub{color:var(--muted);margin:0 0 20px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.tile .v{font-size:30px;font-weight:700;font-variant-numeric:tabular-nums}.tile .l{color:var(--muted);font-size:14px}
.panel{background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:16px}
.callout{background:var(--surface);border-left:4px solid var(--accent);border-radius:6px;padding:12px 16px;margin:20px 0}
.vgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-top:12px}.vgrid>*{min-width:0}
.lg{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px;align-items:start;margin-top:12px}
@media (max-width:860px){.lg{grid-template-columns:minmax(0,1fr)}}
table{border-collapse:collapse;width:100%;font-size:15px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:top}
th{color:var(--muted);font-weight:600}td{color:var(--ink-2)}td.num{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--ink)}
.scroll{overflow-x:auto}.hint{color:var(--muted);font-size:14px}
.tag{display:inline-block;font-size:12px;font-weight:700;padding:1px 8px;border-radius:99px;white-space:nowrap}
.tag.w{background:rgba(47,174,47,.18);color:#8fdc8f}.tag.l{background:rgba(214,69,69,.2);color:#f2a5a5}.tag.n{background:rgba(255,255,255,.08);color:var(--ink-2)}
.bars{display:grid;gap:8px;margin-top:10px;max-width:640px}
.bar{display:grid;grid-template-columns:170px 1fr 54px;gap:10px;align-items:center;font-size:14px;color:var(--ink-2)}
.bar .track{height:12px;background:var(--surface-2);border-radius:6px;overflow:hidden}.bar .fill{height:100%;background:var(--series);border-radius:6px}
.bar .fill.low{background:var(--bad)}.bar .pct{font-variant-numeric:tabular-nums;color:var(--ink);text-align:right}
@media (max-width:520px){.bar{grid-template-columns:110px 1fr 46px}}
.toc{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 8px}
.toc a{color:var(--ink);text-decoration:none;font-size:14px;font-weight:600;padding:6px 12px;border-radius:99px;background:var(--surface);border:1px solid var(--border-strong)}
.toc a:hover{background:var(--hover)}.toc a.hot{background:var(--accent);border-color:var(--accent);color:#1b1a18}
details.fold>summary{list-style:none;cursor:pointer}details.fold>summary::-webkit-details-marker{display:none}
details.fold>summary h2{display:flex;align-items:center;gap:10px}
details.fold>summary h2::after{content:"";width:9px;height:9px;margin-left:auto;flex:none;border:solid var(--muted);border-width:0 2px 2px 0;transform:rotate(45deg);transition:transform .2s}
details.fold:not([open])>summary h2::after{transform:rotate(-45deg)}
.goto{font:inherit;font-weight:700;color:var(--series);background:none;border:0;border-bottom:1px dashed currentColor;padding:0;cursor:pointer}
.goto:hover{color:var(--ink)}html{scroll-behavior:smooth}
.chart{width:100%;height:auto;display:block}.chart .grid{stroke:var(--grid)}.chart .axis{stroke:var(--axis)}
.chart .tick{fill:var(--muted);font:12px system-ui,sans-serif}.chart .line{fill:none;stroke:var(--series);stroke-width:1.6}
.chart .dot.win{fill:var(--good)}.chart .dot.loss{fill:var(--bad)}.chart .dot.draw{fill:var(--muted)}.chart .pt:hover .dot{r:5}
.chart .ann{fill:var(--ink);font:700 13px system-ui,sans-serif}.chart .peak{fill:none;stroke:var(--ink);stroke-width:2}
.viewer{margin:0;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:8px;outline:none}
.viewer:focus-visible{box-shadow:0 0 0 2px var(--accent)}.v-title{font-weight:700;font-size:16px}
.v-moves{font:600 13px/1.4 Consolas,ui-monospace,monospace;color:var(--accent-ink);min-height:1.4em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;direction:rtl;text-align:left}
.v-moves span{direction:ltr;unicode-bidi:bidi-override}.v-board svg{display:block;width:100%;height:auto;max-width:440px;border-radius:4px}
.v-cap{margin:0;min-height:3.1em;color:var(--ink-2);font-size:15px}.v-controls{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.v-controls button{font:600 15px system-ui,sans-serif;min-width:40px;height:38px;padding:0 10px;border-radius:8px;border:1px solid var(--border-strong);background:var(--surface-2);color:var(--ink);cursor:pointer}
.v-controls button:hover:not(:disabled){background:var(--hover)}.v-controls button:disabled{opacity:.35;cursor:default}
.v-count{min-width:64px;white-space:nowrap;text-align:center;font:700 15px system-ui,sans-serif;font-variant-numeric:tabular-nums}.v-play{margin-left:auto}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
"""

JS = """
(function(){
  const L = JSON.parse(document.getElementById('labels').textContent);
  const data = JSON.parse(document.getElementById('viewer-data').textContent);
  document.querySelectorAll('[data-viewer]').forEach(function(root){
    const v = data[root.dataset.viewer]; if (!v) return; const fr = v.frames;
    const board = root.querySelector('.v-board'), moves = root.querySelector('.v-moves'), cap = root.querySelector('.v-cap'),
          count = root.querySelector('.v-count'), btn = function(a){ return root.querySelector('[data-act="'+a+'"]'); }, play = btn('play');
    let i = 0, timer = null;
    function show(n){
      i = Math.max(0, Math.min(fr.length - 1, n));
      board.innerHTML = fr[i].svg; moves.innerHTML = '<span></span>'; moves.firstChild.textContent = fr[i].moves;
      cap.innerHTML = fr[i].caption;
      const ply = fr[i].ply;
      count.textContent = (ply === 0 ? L.start : L.move + ' ' + Math.ceil(ply / 2) + (ply % 2 ? '.' : '...')) + ' · ' + (i + 1) + ' / ' + fr.length;
      btn('first').disabled = btn('prev').disabled = i === 0;
      btn('last').disabled = btn('next').disabled = i === fr.length - 1;
      if (i === fr.length - 1) stop();
    }
    function stop(){ if (timer) { clearInterval(timer); timer = null; } play.textContent = '\\u25B6\\uFE0E ' + L.play; }
    function start(){ if (i === fr.length - 1) show(0); timer = setInterval(function(){ show(i + 1); }, 1600); play.textContent = '\\u275A\\u275A ' + L.pause; }
    root.addEventListener('click', function(e){
      const b = e.target.closest('button'); if (!b) return; const a = b.dataset.act;
      if (a === 'play') { timer ? stop() : start(); return; }
      stop(); show(a === 'first' ? 0 : a === 'last' ? fr.length - 1 : a === 'prev' ? i - 1 : i + 1);
    });
    root.addEventListener('keydown', function(e){
      const k = {ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: fr.length - 1}[e.key];
      if (k !== undefined) { stop(); show(k); e.preventDefault(); }
    });
    root._show = function(ply){ stop(); let k = fr.findIndex(function(f){ return f.ply === ply; }); show(k < 0 ? 0 : k); };
    show(v.start || 0);
  });
  document.addEventListener('click', function(e){
    const g = e.target.closest('[data-goto]'); if (!g) return;
    const root = document.getElementById('v-' + g.dataset.goto); if (!root || !root._show) return;
    root._show(+g.dataset.ply);
    const r = root.getBoundingClientRect(); if (r.top < 0 || r.bottom > innerHeight) root.scrollIntoView({block: 'nearest'});
    root.focus({preventScroll: true});
  });
  function openTarget(id){ const el = id && document.getElementById(id); if (el && el.tagName === 'DETAILS') el.open = true; }
  document.querySelectorAll('.toc a').forEach(function(a){ a.addEventListener('click', function(){ openTarget(a.getAttribute('href').slice(1)); }); });
  openTarget(location.hash.slice(1));
})();
"""


def load_games(out):
    rows = json.loads((out / "games.json").read_text(encoding="utf-8")) if (out / "games.json").exists() else []
    pgns = {}
    for name in ("games.pgn", "last.pgn"):
        p = out / name
        if p.exists():
            f = io.StringIO(p.read_text(encoding="utf-8"))
            while (g := chess.pgn.read_game(f)) is not None:
                pgns[g.headers.get("Link", "")] = g
                if name == "last.pgn":
                    pgns["__last__"] = g
    return rows, pgns


def frames(game_or_moves, orient, notes, arrows, fills, from_ply=0, to_ply=None):
    """Frames for plies from_ply..to_ply (position after `ply` half-moves). Notes keyed by ply-after (frame number)."""
    if isinstance(game_or_moves, str):
        b0 = chess.Board()
        moves = []
        for s in game_or_moves.split():
            moves.append(b0.push_san(s))
    else:
        moves = list(game_or_moves.mainline_moves())
    to_ply = len(moves) if to_ply is None else min(to_ply, len(moves))
    b, out, caption = chess.Board(), [], ""
    for k in range(0, to_ply + 1):
        if k > 0:
            b.push(moves[k - 1])
        caption = notes.get(str(k), caption)  # a caption stays until the next note
        if k < from_ply:
            continue
        check = b.king(b.turn) if b.is_check() else None
        arr = [chess.svg.Arrow(chess.parse_square(a), chess.parse_square(z), color=ARROW.get(c, c))
               for a, z, c in arrows.get(str(k), [])]
        fill = {chess.parse_square(s): ARROW.get(c, c) for s, c in fills.get(str(k), {}).items()}
        svg = chess.svg.board(b, orientation=orient, lastmove=b.peek() if b.move_stack else None, check=check,
                              arrows=arr, fill=fill, size=400, colors=COLORS)
        start = max(0, k - 8)
        tmp = chess.Board()
        for m in moves[:start]:
            tmp.push(m)
        line = ("... " if start else "") + tmp.variation_san(moves[start:k]) if k else ""
        out.append({"svg": DEFS_RE.sub("", svg, count=1), "moves": line, "caption": caption, "ply": k})
    return out


def viewer_html(vid, title, L):
    t = H.escape(title)
    return (f'<figure class="viewer" id="v-{vid}" data-viewer="{vid}" tabindex="0" aria-label="{t}">'
            f'<figcaption class="v-title">{t}</figcaption><div class="v-moves" aria-live="polite"></div><div class="v-board"></div>'
            f'<p class="v-cap" aria-live="polite"></p><div class="v-controls">'
            f'<button type="button" data-act="first" aria-label="{L["first"]}">&#9198;</button>'
            f'<button type="button" data-act="prev" aria-label="{L["prev"]}">&#9664;</button>'
            f'<span class="v-count" aria-live="polite">1 / 1</span>'
            f'<button type="button" data-act="next" aria-label="{L["next"]}">&#9654;</button>'
            f'<button type="button" data-act="last" aria-label="{L["last"]}">&#9197;</button>'
            f'<button type="button" data-act="play" class="v-play">&#9654;&#xFE0E; {L["play"]}</button></div></figure>')


def rating_chart(rows, main_tc, L):
    S = [r for r in rows if r["time_class"] == main_tc and r["my_elo"]]
    if len(S) < 2:
        return ""
    w, h, l, r_, t, btm = 1000, 340, 56, 24, 34, 50
    n = len(S)
    x = lambda i: l + i * (w - l - r_) / (n - 1)
    lo = max(0, (min(s["my_elo"] for s in S) - 50) // 100 * 100)
    hi = (max(s["my_elo"] for s in S) + 150) // 100 * 100
    y = lambda v: t + (hi - v) * (h - t - btm) / (hi - lo)
    step = max(100, ((hi - lo) // 4) // 100 * 100)
    grid = "".join(f'<line x1="{l}" x2="{w - r_}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                   f'<text x="{l - 10}" y="{y(v) + 4:.1f}" class="tick" text-anchor="end">{v}</text>'
                   for v in range(int(lo), int(hi) + 1, int(step)))
    path = "M" + " L".join(f"{x(i):.1f},{y(s['my_elo']):.1f}" for i, s in enumerate(S))
    pts = "".join(
        f'<g class="pt"><title>{L["game"]} {s["n"]} ({s["date"]}), {L[s["color"]]}: {L[s["outcome"]]} {L["vs"]} '
        f'{H.escape(s["opp"])} ({s["opp_elo"]}). {L["rating"]}: {s["my_elo"]}.</title>'
        f'<circle cx="{x(i):.1f}" cy="{y(s["my_elo"]):.1f}" r="7" fill="transparent"/>'
        f'<circle cx="{x(i):.1f}" cy="{y(s["my_elo"]):.1f}" r="2.6" class="dot {s["outcome"]}"/></g>' for i, s in enumerate(S))
    pk = max(range(n), key=lambda i: S[i]["my_elo"])
    ann = (f'<circle cx="{x(pk):.1f}" cy="{y(S[pk]["my_elo"]):.1f}" r="5" class="peak"/>'
           f'<text x="{x(pk):.1f}" y="{y(S[pk]["my_elo"]) - 12:.1f}" class="ann" text-anchor="middle">{L["peak"]}: {S[pk]["my_elo"]}</text>'
           f'<text x="{x(n - 1) - 4:.1f}" y="{y(S[-1]["my_elo"]) - 12:.1f}" class="ann" text-anchor="end">{L["now"]}: {S[-1]["my_elo"]}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="{L["chart"]}">{grid}'
            f'<line x1="{l}" x2="{w - r_}" y1="{h - btm}" y2="{h - btm}" class="axis"/><path d="{path}" class="line"/>{pts}{ann}'
            f'<text x="{(w + l) / 2}" y="{h - 8}" class="tick" text-anchor="middle">{L["axis"]} ({main_tc})</text></svg>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--spec")
    ap.add_argument("--out")
    a = ap.parse_args()
    out = pathlib.Path(a.dir)
    spec = json.loads(pathlib.Path(a.spec or out / "report_spec.json").read_text(encoding="utf-8"))
    L = dict(LABELS["en"])
    L.update(LABELS.get(spec.get("lang", "en"), {}))
    L.update(spec.get("labels", {}))
    rows, pgns = load_games(out)
    by_n = {r["n"]: r for r in rows}
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8")) if (out / "summary.json").exists() else {}

    viewers, vdata = spec.get("viewers", {}), {}
    ga = spec.get("game_analysis")
    if ga and ga.get("viewer"):
        viewers = dict(viewers, **{"game": ga["viewer"]})
    for vid, v in viewers.items():
        if "moves" in v:
            src = v["moves"]
        elif v.get("game") == "last":
            src = pgns["__last__"]
        else:
            src = pgns[by_n[int(v["game"])]["link"]]
        orient = chess.BLACK if v.get("orientation", "white") == "black" else chess.WHITE
        fr = frames(src, orient, v.get("notes", {}), v.get("arrows", {}), v.get("fills", {}),
                    v.get("from_ply", 0), v.get("to_ply"))
        vdata[vid] = {"frames": fr, "start": v.get("start_index", 0)}

    def fill(text):
        text = text.replace("{{CHART}}", rating_chart(rows, summary.get("main_time_class"), L) if rows else "")
        text = re.sub(r"\{\{V:([\w-]+)\}\}", lambda m: viewer_html(m.group(1), viewers[m.group(1)].get("title", ""), L), text)
        return re.sub(r"\{\{GOTO:([\w-]+):(\d+):([^}]*)\}\}",
                      lambda m: f'<button type="button" class="goto" data-goto="{m.group(1)}" data-ply="{m.group(2)}" '
                                f'aria-label="{L["show"]}">{m.group(3)}</button>', text)

    toc, body = [], []
    if ga:
        toc.append(f'<a class="hot" href="#game-analysis">{L["game_analysis"]}</a>')
    for s in spec.get("sections", []):
        if s.get("toc", True):
            toc.append(f'<a href="#{s["id"]}">{H.escape(s.get("toc_title", s["title"]))}</a>')
    tiles = "".join(f'<div class="tile"><div class="v">{t["value"]}</div><div class="l">{t["label"]}</div></div>'
                    for t in spec.get("tiles", []))
    head = (f'<h1>{H.escape(spec["title"])}</h1><p class="sub">{spec.get("subtitle", "")}</p>'
            f'<nav class="toc" aria-label="{L["contents"]}">{"".join(toc)}</nav>')
    if ga:
        body.append(f'<details class="fold" id="game-analysis" open><summary><h2>{H.escape(ga["title"])}</h2></summary>'
                    f'<p class="sub">{ga.get("sub_html", "")}</p><div class="lg"><div>{{{{V:game}}}}</div><div>{ga["html"]}</div></div>'
                    f'</details>')
    if tiles:
        body.append(f'<div class="tiles">{tiles}</div>')
    if spec.get("summary_html"):
        body.append(f'<div class="callout">{spec["summary_html"]}</div>')
    for s in spec.get("sections", []):
        body.append(f'<h2 id="{s["id"]}">{H.escape(s["title"])}</h2>{s["html"]}')
    if spec.get("footer_html"):
        body.append(f'<p class="hint" style="margin-top:32px">{spec["footer_html"]}</p>')
    content = fill(head + "".join(body))
    leftover = re.search(r"\{\{[^}]*\}\}", content)
    assert not leftover, f"unresolved placeholder: {leftover.group(0)}"

    defs = DEFS_RE.search(chess.svg.board(chess.Board(), check=chess.E1)).group(0)
    payload = json.dumps(vdata, ensure_ascii=False).replace("</", "<\\/")
    icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' "
            "rx='14' fill='%23769656'/%3E%3Ctext x='32' y='51' font-size='50' text-anchor='middle' fill='%23ffffff'%3E%E2%99%9E"
            "%3C/text%3E%3C/svg%3E")
    page = (f'<!doctype html><html lang="{spec.get("lang", "en")}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            f'<title>{H.escape(spec.get("page_title", spec["title"]))}</title><link rel="icon" type="image/svg+xml" href="{icon}">'
            f'<style>{CSS}</style></head><body><main>{content}</main>'
            f'<svg width="0" height="0" style="position:absolute" aria-hidden="true">{defs}</svg>'
            f'<script type="application/json" id="labels">{json.dumps(L, ensure_ascii=False)}</script>'
            f'<script type="application/json" id="viewer-data">{payload}</script><script>{JS}</script></body></html>')
    dest = pathlib.Path(a.out or out / "report.html")
    dest.write_text(page, encoding="utf-8")
    counts = ", ".join("%s=%d" % (k, len(v["frames"])) for k, v in vdata.items())
    print(f"{dest} written, {len(page) // 1024} KB, viewers: {counts}")


if __name__ == "__main__":
    main()
