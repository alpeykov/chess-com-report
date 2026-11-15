"""Assemble the single-file HTML report from a spec written by Claude.

usage: python build_report.py --dir OUT [--spec OUT/report_spec.json] [--out OUT/report.html]

The spec format is described in references/spec_format.md. Placeholders allowed inside any html field:
  {{CHART}}                      rating chart (main time class) from games.json
  {{V:viewer_id}}                step-through board defined in spec["viewers"]
  {{GOTO:viewer_id:frame:text}}  button that jumps that board to a frame (frame = ply + 1)

Several languages: set spec["langs"] (e.g. ["bg", "en", "fr"], the first is the default). Any text field
(title, subtitle, tile value/label, summary_html, sections' title/toc_title/html, game_analysis fields,
viewer titles and notes, footer_html) may then be a dict {"bg": ..., "en": ..., "fr": ...}; a plain string
is used for every language. The page gets a flag switcher and remembers the reader's choice.
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
import board_svg

COLORS = {"square light": "#f0d9b5", "square dark": "#b58863",
          "square light lastmove": "#f6eb72", "square dark lastmove": "#dcc34b"}
ARROW = {"green": "#15781B90", "red": "#D0201090", "blue": "#2050C080", "yellow": "#E0A00090"}
DEFS_RE = re.compile(r"<defs>.*?</defs>", re.S)
WORDS = None  # set in main() when spec["piece_words"] is on


def tr(v, lang, default=None):
    """Text for one language: dicts are {lang: text}; anything else is the same in every language."""
    if isinstance(v, dict):
        return v.get(lang, v.get(default, next(iter(v.values()), "")))
    return v

LABELS = {
    "en": dict(start="Start", move="Move", play="Play", pause="Pause", first="To start", prev="Back", next="Forward",
               last="To end", show="Show on the board", win="win", loss="loss", draw="draw", white="White", black="Black",
               game="Game", rating="Rating", now="Now", peak="Peak", vs="vs", axis="Games in order",
               chart="Rating, game by game", contents="Contents", game_analysis="Latest game", top="Back to top", white_chances="Your winning chances (White)", black_chances="Your winning chances (Black)", next_section="Next section", collapse="Collapse all", expand="Expand all",
               tip_open="Click the point to open the game", opening="Opening", moves="Moves", how_checkmate="checkmate", how_resignation="resignation", how_time="on time", how_abandoned="abandoned", how_draw="", how_other=""),
    "fr": dict(start="Début", move="Coup", play="Lecture", pause="Pause", first="Au début", prev="Retour", next="Suivant",
               last="À la fin", show="Afficher sur l'échiquier", win="victoire", loss="défaite", draw="nulle",
               white="Blancs", black="Noirs", game="Partie", rating="Classement", now="Actuel", peak="Max", vs="contre",
               axis="Parties dans l'ordre", chart="Classement, partie par partie", contents="Sommaire",
               game_analysis="Dernière partie", top="Haut de page", white_chances="Vos chances de gain (Blancs)", black_chances="Vos chances de gain (Noirs)", next_section="Section suivante", collapse="Tout replier", expand="Tout déplier",
               tip_open="Cliquez sur le point pour ouvrir la partie", opening="Ouverture", moves="Coups", how_checkmate="mat", how_resignation="abandon", how_time="au temps", how_abandoned="partie quittée", how_draw="", how_other=""),
    "bg": dict(start="Начало", move="Ход", play="Пусни", pause="Пауза", first="Към началото", prev="Назад", next="Напред",
               last="Към края", show="Покажи хода на дъската", win="победа", loss="загуба", draw="реми", white="белите",
               black="черните", game="Партия", rating="Рейтинг", now="Сега", peak="Връх", vs="срещу",
               axis="Партии по ред", chart="Рейтинг, партия по партия", contents="Съдържание",
               game_analysis="Последна партия", top="Към началото", white_chances="Вашият шанс за победа (белите)", black_chances="Вашият шанс за победа (черните)", next_section="Следващ раздел", collapse="Свий всички", expand="Разгъни всички",
               tip_open="Кликнете точката, за да отворите партията", opening="Дебют", moves="Ходове", how_checkmate="мат", how_resignation="предаване", how_time="на време", how_abandoned="напускане", how_draw="", how_other=""),
}

PIECE_WORDS = {
    "en": dict(K="King", Q="Queen", R="Rook", B="Bishop", N="Knight", takes="takes", pawn="pawn", short="castles",
               long="castles long"),
    "fr": dict(K="Roi", Q="Dame", R="Tour", B="Fou", N="Cavalier", takes="prend", pawn="pion", short="petit roque",
               long="grand roque"),
    "bg": dict(K="Цар", Q="Царица", R="Топ", B="Офицер", N="Кон", takes="взима", pawn="пешка", short="рокада",
               long="дълга рокада"),
}
TAG_RE = re.compile(r"(<[^>]+>)")
TOK_RE = re.compile(r"^(?P<pre>[(\[\"„“]*)(?P<num>\d+\.(?:\.\.)?)?(?P<core>[^\s]*?)(?P<ann>[+#]?[!?]*)(?P<punct>[.,;:)\]\"“”]*)$")
PIECE_RE = re.compile(r"^(?:(O-O-O|O-O)|([KQRBN])([a-h]?[1-8]?)(x?)([a-h][1-8])|([a-h])x([a-h][1-8])(?:=([QRBN]))?)$")
PAWN_RE = re.compile(r"^([a-h][1-8])(?:=([QRBN]))?$")


def words_for(spec, lang=None):
    """Write SAN moves in visible text with piece names.
    spec["piece_words"]: true -> names only ("Bxe4" -> "Bishop takes e4"); "both" -> names followed by the standard
    notation in small grey type; a dict overrides PIECE_WORDS[lang]. Text inside <code>...</code> is left as is
    and text inside <span class="words-only"> gets names without the grey notation, so a table can show the
    two in separate columns. Pawn pushes (e4) are named only after a move number or next to
    another move, so a plain square in a sentence ("the bishop on e4") stays as it is."""
    pw = spec.get("piece_words")
    if not pw:
        return None
    w = dict(PIECE_WORDS.get(lang or spec.get("lang", "en"), PIECE_WORDS["en"]))
    if isinstance(pw, dict):
        w.update(pw)
    both = pw == "both" or (isinstance(pw, dict) and pw.get("both"))

    def name(core, pawn_ok):
        m = PIECE_RE.match(core)
        if m:
            castle, pc, dis, x, to, pf, pto, prom = m.groups()
            if castle:
                return w["long"] if castle == "O-O-O" else w["short"]
            if pc:
                return f"{w[pc]}{' (' + dis + ')' if dis else ''} {w['takes'] + ' ' if x else ''}{to}"
            return f"{w['pawn']} {pf} {w['takes']} {pto}{'=' + w[prom] if prom else ''}"
        m = PAWN_RE.match(core)
        if m and pawn_ok:
            return f"{w['pawn']} {m.group(1)}{'=' + w[m.group(2)] if m.group(2) else ''}"
        return None

    def text(s, html, all_moves, names_only=False):
        parts = re.split(r"(\s+)", s)
        toks = [TOK_RE.match(x) if x and not x.isspace() else None for x in parts]
        movish = [bool(m and (PIECE_RE.match(m["core"]) or m["num"])) for m in toks]
        stop = [bool(m and m["punct"]) for m in toks]  # "e3," ends a move sequence
        out = []
        for i, (x, m) in enumerate(zip(parts, toks)):
            if not m:
                out.append(x)
                continue
            pj = next((j for j in range(i - 1, -1, -1) if toks[j]), None)
            nj = next((j for j in range(i + 1, len(parts)) if toks[j]), None)
            prev = pj is not None and movish[pj] and not stop[pj]
            nxt = nj is not None and movish[nj] and not m["punct"]
            nm = name(m["core"], all_moves or bool(m["num"]) or prev or nxt)
            if nm is None:
                out.append(x)
                continue
            san = f"{m['num'] or ''}{m['core']}{m['ann']}"
            extra = (f' <span class="san">({san})</span>' if html else f" ({san})") if both and not names_only else ""
            out.append(f"{m['pre']}{m['num'] or ''}{nm}{m['ann']}{extra}{m['punct']}")
        return "".join(out)

    def apply(s, all_moves=False):
        if all_moves:  # plain-text move list for the board header
            return text(s, False, True)
        out, stack = [], []  # stack of "code" / "words" / "" for open <code> and <span> tags
        for part in TAG_RE.split(s):
            if part.startswith("<"):
                low = part.lower()
                if low.startswith(("<code", "<script", "<style")):
                    stack.append("code")
                elif low.startswith("<span"):
                    stack.append("words" if "words-only" in low else "")
                elif low.startswith(("</code", "</span", "</script", "</style")) and stack:
                    stack.pop()
                out.append(part)
            elif "code" in stack:
                out.append(part)
            else:
                wo = "words" in stack  # a words-only cell holds one move, so a bare square there is a pawn move
                out.append(text(part, True, wo, names_only=wo))
        return "".join(out)
    return apply


FLAGS = {
    "bg": '<svg viewBox="0 0 30 18"><rect width="30" height="6" fill="#fff"/><rect y="6" width="30" height="6" fill="#00966E"/><rect y="12" width="30" height="6" fill="#D62612"/></svg>',
    "en": '<svg viewBox="0 0 60 36"><rect width="60" height="36" fill="#012169"/><path d="M0 0L60 36M60 0L0 36" stroke="#fff" stroke-width="7"/><path d="M0 0L60 36M60 0L0 36" stroke="#C8102E" stroke-width="3"/><path d="M30 0V36M0 18H60" stroke="#fff" stroke-width="11"/><path d="M30 0V36M0 18H60" stroke="#C8102E" stroke-width="6"/></svg>',
    "fr": '<svg viewBox="0 0 30 18"><rect width="10" height="18" fill="#0055A4"/><rect x="10" width="10" height="18" fill="#fff"/><rect x="20" width="10" height="18" fill="#EF4135"/></svg>',
}
LANG_NAMES = {"bg": "Български", "en": "English", "fr": "Français"}

CSS = """
:root{color-scheme:dark;--scene:BGSCENE;--page:#0c1117;--surface:#151d27;--surface-2:#10161e;--side:#182540;--side-line:#34507e;
--ink:#e8edf2;--ink-2:#c3ccd6;--muted:#93a1ae;--accent:#6d9dff;--accent-soft:#1c2b45;--accent-ink:#9dbcff;--on-accent:#0c1117;
--good:#4cc38a;--bad:#e5574c;--warn:#f0a64a;--border:#263241;--border-strong:#34465c;--hover:#1c2b45;--grid:#1c2633;--axis:#34465c;
--series:#6d9dff;--font:"Archivo",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"JetBrains Mono",ui-monospace,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;color:var(--ink);font:16px/1.55 var(--font);background:var(--page)}
body::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;background:var(--scene) center bottom/cover no-repeat}
body::after{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;background:linear-gradient(180deg,rgba(12,17,23,.35) 0%,rgba(12,17,23,.55) 55%,rgba(12,17,23,.25) 100%)}
.page,#to-top,#to-next{position:relative;z-index:1}#to-top,#to-next{position:fixed}
.page{max-width:1120px;margin:0 auto;padding:28px max(16px,env(safe-area-inset-right,0px)) 64px max(16px,env(safe-area-inset-left,0px));position:relative}
.langbar{position:absolute;top:28px;right:max(16px,env(safe-area-inset-right,0px));display:inline-flex;gap:2px;padding:3px;border-radius:10px;
background:var(--surface);border:1px solid var(--border-strong);z-index:3}
.langbar button{width:40px;height:30px;border:0;border-radius:7px;background:transparent;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0}
.langbar button svg{width:24px;height:15px;border-radius:2px;display:block;box-shadow:0 0 0 1px rgba(0,0,0,.35)}
.langbar button[aria-pressed="true"]{background:var(--accent-soft);box-shadow:inset 0 0 0 1.5px var(--accent)}
.langbar button:hover{background:var(--hover)}.langbar button:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
main[hidden]{display:none}
h1{font-size:30px;font-weight:800;letter-spacing:-.01em;margin:0 0 4px;text-wrap:balance;padding-right:150px}
h2{font-size:23px;font-weight:700;margin:48px 0 8px;padding-top:14px;border-top:1px solid var(--border);text-wrap:balance;scroll-margin-top:12px}
h3{font-size:18px;margin:24px 0 6px}p,li{color:var(--ink-2);max-width:75ch}b,strong{color:var(--ink)}
a{color:var(--accent)}.sub{color:var(--muted);margin:0 0 20px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.tile .v{font-size:30px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums}.tile:first-child .v{color:var(--accent)}
.tile .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.07em;font-weight:600}
.panel{background:var(--surface-2);border:1px solid var(--border);border-radius:12px;padding:16px}
.callout{background:var(--side);border:1px solid var(--side-line);border-radius:12px;padding:12px 16px;margin:20px 0}
.vgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-top:12px}.vgrid>*{min-width:0}
.lg{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px;align-items:start;margin-top:12px}
@media (max-width:860px){.lg{grid-template-columns:minmax(0,1fr)}}
section[id$="game-analysis"] .lg>div:first-child{position:sticky;top:12px;align-self:start;z-index:2}
@media (max-width:860px){section[id$="game-analysis"] .lg>div:first-child{top:0;z-index:4;background:var(--page);padding:6px 0;border-bottom:1px solid var(--border)}.lg .v-board svg,.lg .v-eval{max-width:250px;margin:0 auto}.lg .v-title,.lg .v-moves{display:none}.lg .v-cap{min-height:0;font-size:14px}.lg .viewer{padding:8px;gap:6px}}
@media (max-width:560px){h1{padding-right:0;margin-top:44px}}
table{border-collapse:collapse;width:100%;font-size:15px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.07em}td{color:var(--ink-2)}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--ink)}
.scroll{overflow-x:auto}tr.mv-row>td{border-bottom:0;padding-bottom:2px;vertical-align:middle}tr.mv-exp>td{padding-top:2px;padding-bottom:14px;font-size:14.5px;line-height:1.55}.hint{color:var(--muted);font-size:14px}
.tag{display:inline-block;font-size:12px;font-weight:700;padding:1px 8px;border-radius:99px;white-space:nowrap}
.tag.w{background:rgba(76,195,138,.16);color:#7ddcaa}.tag.l{background:rgba(229,87,76,.18);color:#f2a39b}.tag.n{background:var(--accent-soft);color:var(--accent-ink)}
.bars{display:grid;gap:8px;margin-top:10px;max-width:640px}
.bar{display:grid;grid-template-columns:170px 1fr 54px;gap:10px;align-items:center;font-size:14px;color:var(--ink-2)}
.bar .track{height:10px;background:var(--accent-soft);border-radius:5px;overflow:hidden}.bar .fill{height:100%;background:var(--accent);border-radius:5px}
.bar .fill.low{background:var(--bad)}.bar .pct{font-variant-numeric:tabular-nums;color:var(--ink);text-align:right}
@media (max-width:520px){.bar{grid-template-columns:110px 1fr 46px}}
.toc{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 8px}
.toc a{color:var(--ink);text-decoration:none;font-size:14px;font-weight:600;padding:6px 12px;border-radius:99px;background:var(--surface);border:1px solid var(--border-strong)}
.toc a:hover{background:var(--hover)}.toc a.hot{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
details.fold>summary{list-style:none;cursor:pointer}details.fold>summary::-webkit-details-marker{display:none}
details.fold>summary h2{display:flex;align-items:center;gap:10px}
details.fold>summary h2::after{content:"";width:9px;height:9px;margin-left:auto;flex:none;border:solid var(--muted);border-width:0 2px 2px 0;transform:rotate(45deg);transition:transform .2s}
details.fold:not([open])>summary h2::after{transform:rotate(-45deg)}
.goto{font:inherit;font-weight:700;color:var(--accent);background:none;border:0;border-bottom:1px dashed currentColor;padding:0;cursor:pointer}
.goto:hover{color:var(--ink)}.san{color:var(--muted);font-size:.85em;font-family:var(--mono)}code{font:600 13px var(--mono);color:var(--accent-ink)}html{scroll-behavior:smooth}
.chart{width:100%;height:auto;display:block}.chart .grid{stroke:var(--grid)}.chart .axis{stroke:var(--axis)}
.chart .tick{fill:var(--muted);font:12px var(--font)}.chart .line{fill:none;stroke:var(--series);stroke-width:1.8}
.chart .dot.win{fill:var(--good)}.chart .dot.loss{fill:var(--bad)}.chart .dot.draw{fill:var(--muted)}
.chart .ann{fill:var(--ink);font:700 13px var(--font)}.chart .peak{fill:none;stroke:var(--ink);stroke-width:2}
.viewer{margin:0;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:8px;outline:none}
.viewer:focus-visible{box-shadow:0 0 0 2px var(--accent)}.v-title{font-weight:700;font-size:16px}
.v-moves{font:600 13px/1.4 var(--mono);color:var(--accent-ink);min-height:1.4em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;direction:rtl;text-align:left}
.v-moves span{direction:ltr;unicode-bidi:bidi-override}.v-board svg{display:block;width:100%;height:auto;max-width:460px;border-radius:7px;box-shadow:0 6px 18px rgba(0,0,0,.45)}
.v-eval{cursor:ew-resize;max-width:460px;touch-action:pan-y;user-select:none;-webkit-user-select:none}.v-eval svg{display:block;width:100%;height:46px;border-radius:6px;border:1px solid var(--border)}.v-eval span{display:block;font-size:12px;color:var(--muted);margin-top:3px}.v-eval b{color:var(--ink)}
.v-cap{margin:0;min-height:3.1em;color:var(--ink-2);font-size:15px}.v-controls{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.v-controls button{font:600 15px var(--font);min-width:40px;height:38px;padding:0 10px;border-radius:8px;border:1px solid var(--border-strong);background:var(--surface-2);color:var(--ink);cursor:pointer}
.v-controls button:hover:not(:disabled){background:var(--hover)}.v-controls button:disabled{opacity:.35;cursor:default}
.v-controls .v-play{margin-left:auto;background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.v-count{min-width:64px;white-space:nowrap;text-align:center;font:700 15px var(--font);font-variant-numeric:tabular-nums}
.chart-wrap{position:relative}.chart .guide{stroke:var(--muted);stroke-dasharray:3 3}.chart .hot{fill:none;stroke:var(--ink);stroke-width:2}.chart .hit{cursor:pointer}.chart:focus{outline:none}
.chart-tip{position:absolute;z-index:5;pointer-events:none;min-width:210px;max-width:290px;background:var(--surface-2);border:1px solid var(--border-strong);border-radius:10px;padding:10px 12px;font-size:13px;line-height:1.5;color:var(--ink-2);box-shadow:0 6px 20px rgba(0,0,0,.5)}
.chart-tip .tt-h{display:flex;justify-content:space-between;gap:10px;color:var(--ink);font-weight:700;font-size:14px;margin-bottom:4px}.chart-tip .tt-r{display:flex;justify-content:space-between;gap:12px}.chart-tip .tt-r b{color:var(--ink);font-variant-numeric:tabular-nums;text-align:right}.chart-tip .up{color:#7ddcaa}.chart-tip .down{color:#f2a39b}.chart-tip .tt-f{color:var(--muted);font-size:12px;margin-top:6px}
.c1{--c:#6d9dff}.c2{--c:#34d3c1}.c3{--c:#b18cff}.c4{--c:#ff9a55}.c5{--c:#ff6fae}.c6{--c:#f0b44c}.c7{--c:#5fd68b}.c8{--c:#8b85ff}
nav.toc-card{background:var(--surface);border:1px solid var(--border);border-radius:14px;margin:22px 0;padding:0}
nav.toc-card>details>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:10px;padding:14px 22px;font-weight:700;font-size:18px}
nav.toc-card>details>summary::-webkit-details-marker{display:none}
nav.toc-card .fold-all{margin-left:auto;display:flex;gap:6px}nav.toc-card .fold-all button{font:600 12px var(--font);color:var(--accent-ink);background:var(--accent-soft);border:1px solid var(--border-strong);border-radius:99px;padding:3px 10px;cursor:pointer}nav.toc-card .fold-all button:hover{background:var(--hover)}
nav.toc-card>details>summary::after{content:"";width:9px;height:9px;margin-left:12px;border:solid var(--muted);border-width:0 2px 2px 0;transform:rotate(45deg);transition:transform .2s}
nav.toc-card>details:not([open])>summary::after{transform:rotate(-45deg)}
nav.toc-card ol{list-style:none;margin:0;padding:0 16px 16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:2px 12px}
nav.toc-card a{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--ink);font-weight:600;font-size:15px;padding:6px 10px;border-radius:8px;
border-left:3px solid transparent;transition:background .2s,border-color .2s,padding-left .2s}
nav.toc-card a .num{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:800;color:#0c1117;background:var(--c);flex:none}
nav.toc-card a:hover,nav.toc-card a.active{background:color-mix(in srgb,var(--c) 12%,var(--surface));border-left-color:var(--c);padding-left:14px}
section.card{content-visibility:auto;contain-intrinsic-size:auto 900px;background:var(--surface);border:1px solid var(--border);border-top:4px solid var(--c);border-radius:14px;padding:4px 24px 20px;margin:22px 0;scroll-margin-top:14px}
section.card>h2,section.card>details>summary>h2{display:flex;align-items:center;gap:12px;border:0;margin:16px 0 12px;padding:0}
h2 .num{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;flex:none;color:#0c1117;font-size:16px;font-weight:800;
background:linear-gradient(135deg,var(--c),color-mix(in srgb,var(--c) 60%,#000))}
section.card h3{color:var(--c)}
section.card .tile,section.card .viewer{background:var(--surface-2)}
#to-top,#to-next{position:fixed;right:18px;bottom:18px;width:44px;height:44px;border-radius:50%;border:1px solid var(--border-strong);background:var(--accent);color:var(--on-accent);
font:800 20px var(--font);cursor:pointer;opacity:0;pointer-events:none;transition:opacity .25s;box-shadow:0 6px 18px rgba(0,0,0,.45);z-index:6}
#to-top.show,#to-next.show{opacity:1;pointer-events:auto}#to-top{bottom:70px}
@media (max-width:600px){section.card{padding:4px 14px 14px}nav.toc-card ol{grid-template-columns:1fr}}
@media print{#to-top,#to-next,.langbar{display:none}section.card{break-inside:auto}}
.tabs .tab-btns{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 14px;border-bottom:1px solid var(--border);padding-bottom:8px}.tabs .tab-btns button{display:inline-flex;align-items:center;gap:8px;font:700 14px var(--font);color:var(--ink-2);background:var(--surface-2);border:1px solid var(--border-strong);border-radius:99px;padding:6px 14px;cursor:pointer}.tabs .tab-btns button svg{width:20px;height:13px;border-radius:2px}.tabs .tab-btns button[aria-selected="true"]{background:var(--accent-soft);color:var(--ink);box-shadow:inset 0 0 0 1.5px var(--accent)}.tabs .tab[hidden]{display:none}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
"""

JS = """
(function(){
  const LBL = JSON.parse(document.getElementById('labels').textContent);
  const FLAGS = JSON.parse(document.getElementById('flags').textContent);
  function evalGraph(root, ev, ply, L, jump, o){
    let g = root.querySelector('.v-eval');
    if (!g) { g = document.createElement('div'); g.className = 'v-eval'; root.querySelector('.v-board').after(g);
      // click, or press and drag along the graph, to move through the game
      let drag = false, last = -1;
      const at = function(e){ const r = g.getBoundingClientRect(), p = Math.round(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * (ev.length - 1));
        if (p !== last) { last = p; g._jump(p); } };
      g.addEventListener('pointerdown', function(e){ drag = true; last = -1; try { g.setPointerCapture(e.pointerId); } catch (_) {} at(e); e.preventDefault(); });
      g.addEventListener('pointermove', function(e){ if (drag) at(e); });
      ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(function(t){ g.addEventListener(t, function(){ drag = false; }); }); }
    g._jump = jump;
    const W = 360, H = 64, n = ev.length - 1, x = function(i){ return (i / Math.max(1, n)) * W; }, y = function(w){ return H - w / 100 * H; };
    let d = 'M0 ' + H; ev.forEach(function(w, i){ d += ' L' + x(i).toFixed(1) + ' ' + y(w).toFixed(1); }); d += ' L' + W + ' ' + H + ' Z';
    const cur = Math.min(ply, n), w = ev[cur];
    g.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none"><rect width="' + W + '" height="' + H + '" fill="#1b2433"/>'
      + '<path d="' + d + '" fill="#e8edf2" opacity=".85"/><line x1="0" x2="' + W + '" y1="' + H / 2 + '" y2="' + H / 2 + '" stroke="#6d9dff" stroke-dasharray="3 3" opacity=".6"/>'
      + '<line x1="' + x(cur) + '" x2="' + x(cur) + '" y1="0" y2="' + H + '" stroke="#f2b01e" stroke-width="2"/></svg>'
      + '<span>' + (o === 'b' ? L.black_chances : L.white_chances) + ': <b>' + Math.round(w) + '%</b></span>';
  }
  const LANGS = Object.keys(LBL);
  const data = JSON.parse(document.getElementById('viewer-data').textContent);
  document.querySelectorAll('[data-viewer]').forEach(function(root){
    const lang = root.closest('main').dataset.lang, L = LBL[lang];
    const v = data[root.dataset.viewer]; if (!v) return; const fr = v.frames;
    const board = root.querySelector('.v-board'), moves = root.querySelector('.v-moves'), cap = root.querySelector('.v-cap'),
          count = root.querySelector('.v-count'), btn = function(a){ return root.querySelector('[data-act="'+a+'"]'); }, play = btn('play');
    let i = 0, timer = null;
    function show(n){
      i = Math.max(0, Math.min(fr.length - 1, n));
      board.innerHTML = boardSVG(fr[i], v.o);
      if (v.ev) evalGraph(root, v.ev, fr[i].ply, L, function(p){ stop(); const k = fr.findIndex(function(f){ return f.ply === p; }); if (k >= 0) show(k); }, v.o); moves.innerHTML = '<span></span>'; moves.firstChild.textContent = fr[i].moves[lang];
      cap.innerHTML = fr[i].caption[lang];
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
    const main = g.closest('main'), root = document.getElementById('v-' + main.dataset.lang + '-' + g.dataset.goto);
    if (!root || !root._show) return;
    root._show(+g.dataset.ply);
    const r = root.getBoundingClientRect(); if (r.top < 0 || r.bottom > innerHeight) root.scrollIntoView({block: 'nearest'});
    root.focus({preventScroll: true});
  });
  document.querySelectorAll('.chart-wrap').forEach(function(wrap){
    const L = LBL[wrap.closest('main').dataset.lang];
    const svg = wrap.querySelector('svg'), tip = wrap.querySelector('.chart-tip'),
          data = JSON.parse(document.getElementById('chart-data').textContent),
          guide = svg.querySelector('.guide'), hot = svg.querySelector('.hot'), hit = svg.querySelector('.hit');
    const esc = function(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); };
    let cur = -1;
    function nearest(evt){
      const p = svg.createSVGPoint(); p.x = evt.clientX; p.y = evt.clientY;
      const q = p.matrixTransform(svg.getScreenCTM().inverse());
      let lo = 0, hi = data.length - 1;
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (data[mid].x < q.x) lo = mid; else hi = mid; }
      return Math.abs(data[lo].x - q.x) <= Math.abs(data[hi].x - q.x) ? lo : hi;
    }
    function show(i){
      cur = i; const d = data[i];
      guide.setAttribute('x1', d.x); guide.setAttribute('x2', d.x); guide.setAttribute('visibility', 'visible');
      hot.setAttribute('cx', d.x); hot.setAttribute('cy', d.y); hot.setAttribute('visibility', 'visible');
      const how = L['how_' + d.how] || '', ch = d.d > 0 ? '+' + d.d : String(d.d);
      const resCls = d.res === 'win' ? 'up' : d.res === 'loss' ? 'down' : '';
      let when = d.date;  // end of the game in the viewer's own time zone
      const dt = d.ts ? new Date(d.ts) : null;
      if (dt && !isNaN(dt)) {
        const lang = wrap.closest('main').dataset.lang || undefined;
        when = dt.toLocaleDateString(lang, {day: 'numeric', month: 'numeric', year: 'numeric'}) + ' · '
             + dt.toLocaleTimeString(lang, {hour: '2-digit', minute: '2-digit'});
      }
      tip.innerHTML = '<div class="tt-h"><span>' + esc(when) + '</span><span>' + esc(L.game) + ' ' + d.n + '</span></div>'
        + '<div class="tt-r"><span>' + esc(L.rating) + '</span><b>' + d.me + ' <span class="' + (d.d > 0 ? 'up' : d.d < 0 ? 'down' : '') + '">(' + ch + ')</span></b></div>'
        + '<div class="tt-r"><span class="' + resCls + '">' + esc(L[d.res]) + (how ? ', ' + esc(how) : '') + '</span><b>' + esc(L[d.color]) + '</b></div>'
        + '<div class="tt-r"><span>' + esc(L.vs) + ' ' + esc(d.opp) + '</span><b>' + d.oe + '</b></div>'
        + (d.op ? '<div class="tt-r"><span>' + esc(L.opening) + '</span><b style="font-weight:600">' + esc(d.op) + '</b></div>' : '')
        + (d.plies ? '<div class="tt-r"><span>' + esc(L.moves) + '</span><b>' + Math.ceil(d.plies / 2) + '</b></div>' : '')
        + (d.link ? '<div class="tt-f">' + esc(L.tip_open) + '</div>' : '');
      tip.hidden = false;
      const box = wrap.getBoundingClientRect(), r = svg.getBoundingClientRect(), sc = r.width / svg.viewBox.baseVal.width;
      const px = r.left - box.left + d.x * sc, py = r.top - box.top + d.y * sc, tw = tip.offsetWidth, th = tip.offsetHeight;
      let left = px + 14; if (left + tw > box.width) left = px - tw - 14; if (left < 0) left = Math.max(0, box.width - tw);
      let top = py - th / 2; top = Math.max(0, Math.min(top, box.height - th));
      tip.style.left = left + 'px'; tip.style.top = top + 'px';
    }
    function hide(){ cur = -1; tip.hidden = true; guide.setAttribute('visibility', 'hidden'); hot.setAttribute('visibility', 'hidden'); }
    let lastType = 'mouse';
    hit.addEventListener('pointermove', function(e){ show(nearest(e)); });
    hit.addEventListener('pointerdown', function(e){ lastType = e.pointerType; show(nearest(e)); });
    hit.addEventListener('pointerleave', function(e){ if (e.pointerType === 'mouse') hide(); });
    hit.addEventListener('click', function(e){ const d = data[nearest(e)]; if (d.link && lastType === 'mouse') window.open(d.link, '_blank', 'noopener'); });
    svg.setAttribute('tabindex', '0');
    svg.addEventListener('keydown', function(e){
      const k = {ArrowRight: 1, ArrowLeft: -1}[e.key];
      if (!k) { if (e.key === 'Escape') hide(); return; }
      show(Math.max(0, Math.min(data.length - 1, cur < 0 ? data.length - 1 : cur + k))); e.preventDefault();
    });
    svg.addEventListener('blur', hide);
  });
  function setLang(l){
    if (LANGS.indexOf(l) < 0) l = LANGS[0];
    document.querySelectorAll('main[data-lang]').forEach(function(m){ m.hidden = m.dataset.lang !== l; });
    document.querySelectorAll('.langbar button').forEach(function(b){ b.setAttribute('aria-pressed', String(b.dataset.lang === l)); });
    document.documentElement.lang = l;
    [['to-top', 'top'], ['to-next', 'next_section']].forEach(function(b){ const e = document.getElementById(b[0]); if (e) { e.title = LBL[l][b[1]]; e.setAttribute('aria-label', LBL[l][b[1]]); } });
    const h1 = document.querySelector('main[data-lang="' + l + '"] h1'); if (h1) document.title = h1.textContent;
    try { localStorage.setItem('chess-report-lang', l); } catch (e) {}
  }
  document.querySelectorAll('.langbar button').forEach(function(b){ b.addEventListener('click', function(){ setLang(b.dataset.lang); }); });
  let saved = null; try { saved = localStorage.getItem('chess-report-lang'); } catch (e) {}
  const qs = (location.search.match(/[?&]lang=([a-z]{2})/) || [])[1];
  setLang(qs || saved || LANGS[0]);
  document.querySelectorAll('nav.toc-card details').forEach(function(d){
    try { if (localStorage.getItem('chess-report-toc') === 'closed') d.open = false; } catch (e) {}
    d.addEventListener('toggle', function(){ try { localStorage.setItem('chess-report-toc', d.open ? 'open' : 'closed'); } catch (e) {} });
  });
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(function(entries){
      entries.forEach(function(en){
        if (!en.isIntersecting) return;
        const main = en.target.closest('main');
        main.querySelectorAll('nav.toc-card a').forEach(function(a){ a.classList.toggle('active', a.getAttribute('href') === '#' + en.target.id); });
      });
    }, {rootMargin: '-20% 0px -70% 0px'});
    document.querySelectorAll('section.card[id]').forEach(function(s){ io.observe(s); });
  }
  const topBtn = document.getElementById('to-top'), nextBtn = document.getElementById('to-next');
  function nextSection(){
    const main = document.querySelector('main:not([hidden])');
    const secs = main ? main.querySelectorAll('section.card') : [];
    for (let k = 0; k < secs.length; k++) if (secs[k].getBoundingClientRect().top > 90) return secs[k];
    return null;
  }
  if (nextBtn) nextBtn.addEventListener('click', function(){
    const s = nextSection();
    if (s) { s.scrollIntoView({behavior: 'smooth'}); setTimeout(function(){ s.scrollIntoView({behavior: 'auto'}); }, 700); }
    else window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'smooth'});
  });
  if (topBtn) {
    const onScroll = function(){
      topBtn.classList.toggle('show', window.scrollY > 500);
      if (nextBtn) nextBtn.classList.toggle('show', window.innerHeight + window.scrollY < document.documentElement.scrollHeight - 40);
    };
    window.addEventListener('scroll', onScroll, {passive: true});
    topBtn.addEventListener('click', function(){ window.scrollTo({top: 0}); });
    onScroll();
  }
  // tabs: <div class="tabs"><div class="tab" data-tab="bg" data-label="..">..</div>...</div>; the tab in the page's language opens first
  document.querySelectorAll('.tabs').forEach(function(box){
    const lang = box.closest('main').dataset.lang, tabs = Array.prototype.slice.call(box.querySelectorAll(':scope > .tab'));
    const bar = document.createElement('div'); bar.className = 'tab-btns'; bar.setAttribute('role', 'tablist');
    tabs.forEach(function(tb){
      const b = document.createElement('button'); b.type = 'button'; b.setAttribute('role', 'tab'); b.dataset.tab = tb.dataset.tab;
      b.innerHTML = (FLAGS[tb.dataset.tab] || '') + '<span></span>'; b.lastChild.textContent = tb.dataset.label || tb.dataset.tab;
      b.addEventListener('click', function(){ pick(tb.dataset.tab); }); bar.appendChild(b);
    });
    box.insertBefore(bar, box.firstChild);
    function pick(k){
      tabs.forEach(function(tb){ tb.hidden = tb.dataset.tab !== k; });
      bar.querySelectorAll('button').forEach(function(b){ b.setAttribute('aria-selected', String(b.dataset.tab === k)); });
    }
    pick(tabs.some(function(tb){ return tb.dataset.tab === lang; }) ? lang : tabs[0].dataset.tab);
  });
  function openTarget(id){
    const el = id && document.getElementById(id); if (!el) return;
    const d = el.tagName === 'DETAILS' ? el : el.querySelector(':scope > details.fold'); if (d) d.open = true;
  }
  document.querySelectorAll('.fold-all button').forEach(function(b){ b.addEventListener('click', function(e){
    e.preventDefault(); e.stopPropagation();
    b.closest('main').querySelectorAll('section.card > details.fold').forEach(function(d){ d.open = b.dataset.fold === 'open'; });
  }); });
  // sections off screen are not rendered (content-visibility), so their height is only estimated:
  // jump, let them render, then correct the position
  function go(id, smooth){
    const el = id && document.getElementById(id); if (!el) return;
    openTarget(id);
    el.scrollIntoView({behavior: smooth ? 'smooth' : 'auto'});
    setTimeout(function(){ el.scrollIntoView({behavior: 'auto'}); }, smooth ? 700 : 120);
  }
  document.querySelectorAll('nav.toc-card a').forEach(function(a){ a.addEventListener('click', function(e){
    e.preventDefault(); const id = a.getAttribute('href').slice(1); history.replaceState(null, '', '#' + id); go(id, true); }); });
  if (location.hash) setTimeout(function(){ go(location.hash.slice(1), false); }, 60);
})();
"""


def _bg_scene(variant):
    """CSS url() of the faded background scene ("night", "fog", "king"; "none" for a plain colour)."""
    import urllib.parse
    if not variant or variant == "none":
        return "none"
    return 'url("' + board_svg.background_uri(variant) + '")'


def _bg_piece(sym):
    """A large, flat piece silhouette in the accent colour for the page background (CSS url())."""
    import urllib.parse
    g = re.sub(r'(fill|stroke)="#(?:fff|000)"|(fill|stroke):#(?:ffffff|000000)', lambda m: (m.group(1) or m.group(2)) + ('="#6d9dff"' if m.group(1) else ":#6d9dff"),
               chess.svg.PIECES[sym])
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45">{g}</svg>'
    return 'url("data:image/svg+xml,' + urllib.parse.quote(svg) + '")'


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


def frames(game_or_moves, orient, notes, arrows, fills, from_ply=0, to_ply=None, langs=("en",), words=None):
    """Frames for plies from_ply..to_ply (position after `ply` half-moves). Notes keyed by ply-after (frame number);
    a note may be a {lang: text} dict. Captions and move lines are stored per language."""
    words = words or {}
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
        pos = {"fen": b.board_fen()}  # drawn in the browser by boardSVG() (board_svg.JS_BOARD)
        if b.move_stack:
            pos["lm"] = b.peek().uci()[:4]
        if b.is_check():
            pos["ck"] = chess.square_name(b.king(b.turn))
        if arrows.get(str(k)):
            pos["ar"] = arrows[str(k)]
        if fills.get(str(k)):
            pos["fl"] = fills[str(k)]
        start = max(0, k - 8)
        tmp = chess.Board()
        for m in moves[:start]:
            tmp.push(m)
        line = ("... " if start else "") + tmp.variation_san(moves[start:k]) if k else ""
        caps, lines = {}, {}
        for lang in langs:
            w, c = words.get(lang), tr(caption, lang, langs[0])
            caps[lang] = w(c) if w else c
            lines[lang] = w(line, True) if w else line
        out.append(dict(pos, moves=lines, caption=caps, ply=k))
    return out


def viewer_html(vid, title, L, lang):
    t = H.escape(title)
    return (f'<figure class="viewer" id="v-{lang}-{vid}" data-viewer="{vid}" tabindex="0" aria-label="{t}">'
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
    # date labels on the x axis: about 8, at the first game of a new day near evenly spaced points
    years = {s["date"][:4] for s in S}
    ticks, last_i = "", -10 ** 9
    for k in range(8):
        i = round(k * (n - 1) / 7)
        while i > 0 and S[i - 1]["date"] == S[i]["date"]:  # first game of that day
            i -= 1
        if i - last_i < n / 14:  # too close to the previous label
            continue
        last_i = i
        yy, mm, dd = (S[i]["date"].split(".") + ["", "", ""])[:3]
        label = f"{int(dd)}.{mm}" + (f".{yy[2:]}" if len(years) > 1 else "") if dd else S[i]["date"]
        ticks += (f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{h - btm}" y2="{h - btm + 5}" class="axis"/>'
                  f'<text x="{x(i):.1f}" y="{h - btm + 19}" class="tick" text-anchor="middle">{label}</text>')
    pts = "".join(f'<circle cx="{x(i):.1f}" cy="{y(s["my_elo"]):.1f}" r="2.6" class="dot {s["outcome"]}"/>'
                  for i, s in enumerate(S))
    pk = max(range(n), key=lambda i: S[i]["my_elo"])
    ann = (f'<circle cx="{x(pk):.1f}" cy="{y(S[pk]["my_elo"]):.1f}" r="5" class="peak"/>'
           f'<text x="{x(pk):.1f}" y="{y(S[pk]["my_elo"]) - 12:.1f}" class="ann" text-anchor="middle">{L["peak"]}: {S[pk]["my_elo"]}</text>'
           f'<text x="{x(n - 1) - 4:.1f}" y="{y(S[-1]["my_elo"]) - 12:.1f}" class="ann" text-anchor="end">{L["now"]}: {S[-1]["my_elo"]}</text>')
    # data for the hover card (one entry per point)
    data = []
    for i, s in enumerate(S):
        yy, mm, dd = (s["date"].split(".") + ["", "", ""])[:3]
        data.append({"x": round(x(i), 1), "y": round(y(s["my_elo"]), 1), "n": s["n"],
                     "date": f"{int(dd)}.{mm}.{yy}" if dd else s["date"],
                     "ts": f"{yy}-{mm}-{dd}T{s['end_time']}Z" if dd and s.get("end_time") else "",
                     "color": s["color"], "res": s["outcome"],
                     "how": s.get("how", ""), "opp": s["opp"], "oe": s["opp_elo"], "me": s["my_elo"],
                     "d": s["my_elo"] - S[i - 1]["my_elo"] if i else 0, "op": s.get("opening", ""),
                     "plies": s.get("plies", 0), "link": s.get("link", "")})
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return (f'<div class="chart-wrap"><svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="{L["chart"]}">{grid}'
            f'<line x1="{l}" x2="{w - r_}" y1="{h - btm}" y2="{h - btm}" class="axis"/>{ticks}<path d="{path}" class="line"/>{pts}{ann}'
            f'<line class="guide" x1="0" x2="0" y1="{t}" y2="{h - btm}" visibility="hidden"/>'
            f'<circle class="hot" r="5.5" cx="0" cy="0" visibility="hidden"/>'
            f'<rect class="hit" x="{l}" y="{t - 20}" width="{w - l - r_}" height="{h - btm - t + 20}" fill="transparent"/>'
            f'<text x="{(w + l) / 2}" y="{h - 8}" class="tick" text-anchor="middle">{L["axis"]} ({main_tc})</text></svg>'
            f'<div class="chart-tip" role="tooltip" hidden></div>'
            f'<script type="application/json" class="chart-data">{payload}</script></div>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--spec")
    ap.add_argument("--out")
    a = ap.parse_args()
    out = pathlib.Path(a.dir)
    spec = json.loads(pathlib.Path(a.spec or out / "report_spec.json").read_text(encoding="utf-8"))
    langs = spec.get("langs") or [spec.get("lang", "en")]
    first = langs[0]
    LL, words = {}, {}
    for lang in langs:
        L = dict(LABELS["en"])
        L.update(LABELS.get(lang, {}))
        lab = spec.get("labels", {})  # either {key: text} or {lang: {key: text}}
        L.update(lab.get(lang, {}) if any(k in LABELS for k in lab) else lab)
        LL[lang] = L
        words[lang] = words_for(spec, lang)
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
                    v.get("from_ply", 0), v.get("to_ply"), langs, words)
        vdata[vid] = {"frames": fr, "start": v.get("start_index", 0), "o": "b" if orient == chess.BLACK else "w"}
        if v.get("evals"):  # White's win % after each ply (sf_scan.py), drawn as a graph under the board
            # shown from the side of the board's orientation (the player's colour): Black sees 100 - White's %
            vdata[vid]["ev"] = [round(100 - w, 1) for w in v["evals"]] if orient == chess.BLACK else v["evals"]

    def block(lang):
        L, T = LL[lang], (lambda v: tr(v, lang, first))

        def fill(text):
            text = text.replace("{{CHART}}", rating_chart(rows, summary.get("main_time_class"), L) if rows else "")
            text = re.sub(r"\{\{V:([\w-]+)\}\}",
                          lambda m: viewer_html(m.group(1), T(viewers[m.group(1)].get("title", "")), L, lang), text)
            return re.sub(r"\{\{GOTO:([\w-]+):(\d+):([^}]*)\}\}",
                          lambda m: f'<button type="button" class="goto" data-goto="{m.group(1)}" data-ply="{m.group(2)}" '
                                    f'aria-label="{L["show"]}">{m.group(3)}</button>', text)

        toc, body = [], []
        secs = []  # (id, number, title, toc title, html, colour class)
        lead = [s for s in spec.get("sections", []) if s.get("before_game")]  # e.g. a rule for the reader's next session
        for s in lead:
            secs.append((f'{lang}-{s["id"]}', s.get("badge", "★"), T(s["title"]), T(s.get("toc_title", s["title"])), T(s["html"]), "c6"))
        if ga:
            secs.append((f"{lang}-game-analysis", "♞", T(ga["title"]), T(ga.get("toc_title", L["game_analysis"])), None, "c1"))
        k = 0
        for s in spec.get("sections", []):
            if s.get("before_game"):
                continue
            title = T(s["title"])
            m = re.match(r"^(\d+)\.\s*(.*)$", title)
            num, title = (m.group(1), m.group(2)) if m else (str(k + 1), title)
            secs.append((f'{lang}-{s["id"]}', num, title, T(s.get("toc_title", s["title"])), T(s["html"]), f"c{k % 8 + 1}"))
            k += 1
        for sid, num, title, toc_t, _, cc in secs:
            toc.append(f'<li><a href="#{sid}" class="{cc}"><span class="num">{num}</span>{H.escape(re.sub(r"^\d+\.\s*", "", toc_t))}</a></li>')
        tiles = "".join(f'<div class="tile"><div class="v">{T(t_["value"])}</div><div class="l">{T(t_["label"])}</div></div>'
                        for t_ in spec.get("tiles", []))
        head = (f'<h1>{H.escape(T(spec["title"]))}</h1><p class="sub">{T(spec.get("subtitle", ""))}</p>'
                f'<nav class="toc-card" aria-label="{L["contents"]}"><details open><summary>{L["contents"]}'
                f'<span class="fold-all"><button type="button" data-fold="open">{L["expand"]}</button>'
                f'<button type="button" data-fold="close">{L["collapse"]}</button></span></summary>'
                f'<ol>{"".join(toc)}</ol></details></nav>')
        if tiles:
            body.append(f'<div class="tiles">{tiles}</div>')
            if spec.get("score_note"):
                body.append(f'<p class="hint" style="margin:-6px 0 12px">{T(spec["score_note"])}</p>')
        if spec.get("summary_html"):
            body.append(f'<div class="callout">{T(spec["summary_html"])}</div>')
        for sid, num, title, _, html_, cc in secs:
            if html_ is None:  # the game analysis, collapsible
                body.append(f'<section class="card {cc}" id="{sid}"><details class="fold" open><summary><h2><span class="num">{num}</span>'
                            f'{H.escape(title)}</h2></summary><p class="sub">{T(ga.get("sub_html", ""))}</p><div class="lg"><div>{{{{V:game}}}}</div>'
                            f'<div>{T(ga["html"])}</div></div></details></section>')
            else:
                body.append(f'<section class="card {cc}" id="{sid}"><details class="fold" open><summary><h2><span class="num">{num}</span>'
                            f'{H.escape(title)}</h2></summary>{html_}</details></section>')
        if spec.get("footer_html"):
            body.append(f'<p class="hint" style="margin-top:32px">{T(spec["footer_html"])}</p>')
        content = fill(head + "".join(body))
        if words.get(lang):
            content = words[lang](content)
        leftover = re.search(r"\{\{[^}]*\}\}", content)
        assert not leftover, f"unresolved placeholder: {leftover.group(0)}"
        return f'<main data-lang="{lang}" lang="{lang}">{content}</main>'

    mains = "".join(block(lang) for lang in langs)
    # the chart data is the same in every language: keep one copy
    chart_json = re.findall(r'<script type="application/json" class="chart-data">(.*?)</script>', mains, re.S)
    mains = re.sub(r'<script type="application/json" class="chart-data">.*?</script>', "", mains, flags=re.S)
    shared = f'<script type="application/json" id="chart-data">{chart_json[0]}</script>' if chart_json else ""
    switcher = ""
    if len(langs) > 1:
        switcher = ('<div class="langbar" role="group" aria-label="Language">' + "".join(
            f'<button type="button" data-lang="{lg}" aria-pressed="{str(lg == first).lower()}" '
            f'title="{LANG_NAMES.get(lg, lg)}" aria-label="{LANG_NAMES.get(lg, lg)}">{FLAGS.get(lg, lg.upper())}</button>'
            for lg in langs) + "</div>")
    payload = json.dumps(vdata, ensure_ascii=False).replace("</", "<\\/")
    icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' "
            "rx='14' fill='%231f5fd6'/%3E%3Ctext x='32' y='51' font-size='50' text-anchor='middle' fill='%23ffffff'%3E%E2%99%9E"
            "%3C/text%3E%3C/svg%3E")
    fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" '
             'href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap">')
    page = (f'<!doctype html><html lang="{first}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            f'<title>{H.escape(tr(spec.get("page_title", spec["title"]), first, first))}</title><link rel="icon" type="image/svg+xml" href="{icon}">'
            f'{fonts}<style>{CSS.replace("BGSCENE", _bg_scene(spec.get("background", "night")))}</style></head><body><div class="page">{switcher}{mains}</div>'
            f'<button type="button" id="to-top" aria-label="{LL[first]["top"]}" title="{LL[first]["top"]}">&#8593;</button>'
            f'<button type="button" id="to-next" aria-label="{LL[first]["next_section"]}" title="{LL[first]["next_section"]}">&#8595;</button>'
            f'<svg width="0" height="0" style="position:absolute" aria-hidden="true">{board_svg.page_defs()}</svg>'
            f'<script type="application/json" id="labels">{json.dumps(LL, ensure_ascii=False)}</script>'
            f'<script type="application/json" id="flags">{json.dumps(FLAGS)}</script>'
            f'{shared}<script type="application/json" id="viewer-data">{payload}</script><script>{board_svg.JS_BOARD}{JS}</script></body></html>')
    dest = pathlib.Path(a.out or out / "report.html")
    dest.write_text(page, encoding="utf-8")
    counts = ", ".join("%s=%d" % (k, len(v["frames"])) for k, v in vdata.items())
    print(f"{dest} written, {len(page) // 1024} KB, viewers: {counts}")


if __name__ == "__main__":
    main()
