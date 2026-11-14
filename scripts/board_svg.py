"""Wooden board with metal pieces, drawn as SVG.

DEFS goes into the page once (piece shapes, wood textures, gradients); render() returns one small SVG per position
that refers to them with <use>. Pieces are the python-chess (Colin M.L. Burnett) shapes with a silver / dark-steel
finish; the board has maple and walnut squares with grain and a dark wooden frame with coordinates on all sides.
"""
import base64
import pathlib
import re
import chess
import chess.svg

S, M = 40, 20  # square size, frame width
N = 8 * S + 2 * M
ARROW_COLORS = {"green": "#2f9e44", "red": "#e03131", "blue": "#3b82f6", "yellow": "#f2b01e"}
FILL_COLORS = {"green": "rgba(47,158,68,.45)", "red": "rgba(224,49,49,.45)", "blue": "rgba(59,130,246,.45)",
               "yellow": "rgba(242,176,30,.5)"}


def _piece_symbol(sym):
    svg = re.sub(r"\s+", " ", chess.svg.PIECES[sym])
    svg = re.sub(r' (id|class)="[^"]+"', "", svg)
    if sym.isupper():  # silver
        svg = re.sub(r'fill="#fff"|fill:#ffffff', lambda m: 'fill="url(#mW)"' if m.group(0).startswith('fill="') else "fill:url(#mW)", svg)
        svg = re.sub(r'stroke="#000"|stroke:#000000', lambda m: 'stroke="#2b2b2b"' if m.group(0).startswith('stroke="') else "stroke:#2b2b2b", svg)
        svg = svg.replace("fill:#000000", "fill:#2b2b2b")
    else:  # dark steel
        svg = re.sub(r'fill="#000"|fill:#000000', lambda m: 'fill="url(#mB)"' if m.group(0).startswith('fill="') else "fill:url(#mB)", svg)
        svg = re.sub(r'stroke="#000"|stroke:#000000', lambda m: 'stroke="#0a0a0a"' if m.group(0).startswith('stroke="') else "stroke:#0a0a0a", svg)
        svg = re.sub(r'stroke="#fff"|#ececec', lambda m: 'stroke="#a7adb5"' if m.group(0).startswith('stroke="') else "#a7adb5", svg)
    return f'<symbol id="pc-{sym}" viewBox="0 0 45 45">{svg}</symbol>'


ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"


def asset_uri(name):
    """data: URI of a picture in the skill's assets folder (pre-rendered WebP, see assets/README.md)."""
    return "data:image/webp;base64," + base64.b64encode((ASSETS / name).read_bytes()).decode()


# Wood and frame textures are small pre-rendered pictures: a live SVG noise filter looks the same but makes
# the browser repaint every visible board while scrolling.
DEFS = (
    "<defs>"
    '<linearGradient id="mW" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/>'
    '<stop offset=".4" stop-color="#e4e6ea"/><stop offset=".72" stop-color="#a9adb4"/><stop offset="1" stop-color="#f1f2f4"/></linearGradient>'
    '<linearGradient id="mB" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8a9099"/>'
    '<stop offset=".33" stop-color="#3a3e45"/><stop offset=".7" stop-color="#16181c"/><stop offset="1" stop-color="#4c5159"/></linearGradient>'
    f'<pattern id="woodL" patternUnits="userSpaceOnUse" x="{M}" y="{M}" width="{8 * S}" height="{8 * S}">'
    f'<image href="{{L}}" width="{8 * S}" height="{8 * S}" preserveAspectRatio="none"/></pattern>'
    f'<pattern id="woodD" patternUnits="userSpaceOnUse" x="{M}" y="{M}" width="{8 * S}" height="{8 * S}">'
    f'<image href="{{D}}" width="{8 * S}" height="{8 * S}" preserveAspectRatio="none"/></pattern>'
    f'<pattern id="woodF" patternUnits="userSpaceOnUse" width="{N}" height="{N}">'
    f'<image href="{{F}}" width="{N}" height="{N}" preserveAspectRatio="none"/></pattern>'
    '<radialGradient id="checkGlow"><stop offset="0" stop-color="#ff3b30" stop-opacity=".95"/>'
    '<stop offset=".55" stop-color="#ff3b30" stop-opacity=".45"/><stop offset="1" stop-color="#ff3b30" stop-opacity="0"/></radialGradient>'
    + "".join(_piece_symbol(s) for s in "KQRBNPkqrbnp")
    + "</defs>"
)


def page_defs():
    """DEFS with the textures filled in (call once per page)."""
    return (DEFS.replace("{L}", asset_uri("wood-light.webp")).replace("{D}", asset_uri("wood-dark.webp"))
            .replace("{F}", asset_uri("wood-frame.webp")))


# The same board drawn in the browser from a few bytes per position (see JS_BOARD); render() below is the
# Python version, kept for tests and other uses.
JS_BOARD = r"""
function boardSVG(f, o){
  const S=40, M=20, N=360, AC={green:'#2f9e44',red:'#e03131',blue:'#3b82f6',yellow:'#f2b01e'},
        FC={green:'rgba(47,158,68,.45)',red:'rgba(224,49,49,.45)',blue:'rgba(59,130,246,.45)',yellow:'rgba(242,176,30,.5)'};
  const xy=function(sq){ const fi=sq.charCodeAt(0)-97, r=+sq[1]-1; return o==='b' ? [M+(7-fi)*S, M+r*S] : [M+fi*S, M+(7-r)*S]; };
  let dark=''; for (let r=0;r<8;r++) for (let c=0;c<8;c++) if ((r+c)%2===1) dark+='M'+(M+c*S)+' '+(M+r*S)+'h40v40h-40z';
  const h=['<svg viewBox="0 0 360 360" xmlns="http://www.w3.org/2000/svg" class="wb"><rect width="360" height="360" rx="7" fill="url(#woodF)"/>',
    '<rect x="18" y="18" width="324" height="324" fill="#24150c"/><rect x="20" y="20" width="320" height="320" fill="url(#woodL)"/>',
    '<path d="'+dark+'" fill="url(#woodD)"/>'];
  const sqr=function(sq,fill){ const p=xy(sq); h.push('<rect x="'+p[0]+'" y="'+p[1]+'" width="40" height="40" fill="'+fill+'"/>'); };
  if (f.lm) { sqr(f.lm.slice(0,2),'rgba(255,206,64,.45)'); sqr(f.lm.slice(2,4),'rgba(255,206,64,.45)'); }
  for (const k in (f.fl||{})) sqr(k, FC[f.fl[k]]||f.fl[k]);
  if (f.ck) sqr(f.ck,'url(#checkGlow)');
  const files=o==='b'?'hgfedcba':'abcdefgh', ranks=o==='b'?'12345678':'87654321';
  let lab=''; for (let i=0;i<8;i++){ const c=M+i*S+S/2;
    lab+='<text x="'+c+'" y="14">'+files[i]+'</text><text x="'+c+'" y="355">'+files[i]+'</text><text x="10" y="'+(c+4)+'">'+ranks[i]+'</text><text x="350" y="'+(c+4)+'">'+ranks[i]+'</text>'; }
  h.push('<g fill="#e9d6b6" font-family="Archivo,system-ui,sans-serif" font-size="11" font-weight="700" text-anchor="middle">'+lab+'</g>');
  let sh='', pcs='', r=7, c=0;
  for (const ch of f.fen) {
    if (ch==='/') { r--; c=0; continue; }
    if (ch>='1' && ch<='8') { c+=+ch; continue; }
    const p=xy(String.fromCharCode(97+c)+(r+1));
    sh+='<ellipse cx="'+(p[0]+21)+'" cy="'+(p[1]+35.5)+'" rx="12.5" ry="3.2"/>';
    pcs+='<use href="#pc-'+ch+'" x="'+p[0]+'" y="'+p[1]+'" width="40" height="40"/>';
    c++;
  }
  h.push('<g fill="rgba(0,0,0,.38)">'+sh+'</g>'+pcs);
  (f.ar||[]).forEach(function(a){
    const p1=xy(a[0]), p2=xy(a[1]), x1=p1[0]+20, y1=p1[1]+20, x2=p2[0]+20, y2=p2[1]+20, col=AC[a[2]]||a[2];
    const dx=x2-x1, dy=y2-y1, ln=Math.max(1e-6,Math.hypot(dx,dy)), ux=dx/ln, uy=dy/ln, hx=x2-ux*13, hy=y2-uy*13, px=-uy*8, py=ux*8;
    h.push('<g opacity=".85"><line x1="'+x1+'" y1="'+y1+'" x2="'+hx+'" y2="'+hy+'" stroke="'+col+'" stroke-width="7" stroke-linecap="round"/>'
      +'<polygon points="'+x2+','+y2+' '+(hx+px)+','+(hy+py)+' '+(hx-px)+','+(hy-py)+'" fill="'+col+'"/></g>');
  });
  h.push('</svg>'); return h.join('');
}
"""


def _xy(sq, orient):
    f, r = chess.square_file(sq), chess.square_rank(sq)
    if orient == chess.WHITE:
        return M + f * S, M + (7 - r) * S
    return M + (7 - f) * S, M + r * S


def _arrow(a, z, color, orient):
    (x1, y1), (x2, y2) = [(x + S / 2, y + S / 2) for x, y in (_xy(a, orient), _xy(z, orient))]
    c = ARROW_COLORS.get(color, color)
    dx, dy = x2 - x1, y2 - y1
    ln = max(1e-6, (dx * dx + dy * dy) ** .5)
    ux, uy = dx / ln, dy / ln
    hx, hy = x2 - ux * 13, y2 - uy * 13  # head base
    px, py = -uy * 8, ux * 8
    return (f'<g opacity=".85"><line x1="{x1:.1f}" y1="{y1:.1f}" x2="{hx:.1f}" y2="{hy:.1f}" stroke="{c}" stroke-width="7" '
            f'stroke-linecap="round"/><polygon points="{x2:.1f},{y2:.1f} {hx + px:.1f},{hy + py:.1f} {hx - px:.1f},{hy - py:.1f}" '
            f'fill="{c}"/></g>')


def render(board, orient=chess.WHITE, lastmove=None, check=None, arrows=(), fills=None):
    """arrows: [(from_square, to_square, colour)], fills: {square: colour}."""
    out = [f'<svg viewBox="0 0 {N} {N}" xmlns="http://www.w3.org/2000/svg" class="wb">',
           f'<rect width="{N}" height="{N}" rx="7" fill="url(#woodF)"/>',
           f'<rect x="{M - 2}" y="{M - 2}" width="{8 * S + 4}" height="{8 * S + 4}" fill="#24150c"/>']
    for sq in chess.SQUARES:
        x, y = _xy(sq, orient)
        light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
        out.append(f'<rect x="{x}" y="{y}" width="{S}" height="{S}" fill="url(#{"woodL" if light else "woodD"})"/>')
    if lastmove:
        for sq in (lastmove.from_square, lastmove.to_square):
            x, y = _xy(sq, orient)
            out.append(f'<rect x="{x}" y="{y}" width="{S}" height="{S}" fill="rgba(255,206,64,.45)"/>')
    for sq, col in (fills or {}).items():
        x, y = _xy(sq, orient)
        out.append(f'<rect x="{x}" y="{y}" width="{S}" height="{S}" fill="{FILL_COLORS.get(col, col)}"/>')
    if check is not None:
        x, y = _xy(check, orient)
        out.append(f'<rect x="{x}" y="{y}" width="{S}" height="{S}" fill="url(#checkGlow)"/>')
    files = "abcdefgh" if orient == chess.WHITE else "hgfedcba"
    ranks = "87654321" if orient == chess.WHITE else "12345678"
    lab = []
    for i in range(8):
        c = M + i * S + S / 2
        lab.append(f'<text x="{c}" y="{M - 6}">{files[i]}</text><text x="{c}" y="{N - 5}">{files[i]}</text>'
                   f'<text x="{M / 2}" y="{c + 4}">{ranks[i]}</text><text x="{N - M / 2}" y="{c + 4}">{ranks[i]}</text>')
    out.append('<g fill="#e9d6b6" font-family="Archivo,system-ui,sans-serif" font-size="11" font-weight="700" '
               f'text-anchor="middle">{"".join(lab)}</g>')
    pcs = []
    for sq, p in board.piece_map().items():
        x, y = _xy(sq, orient)
        pcs.append(f'<use href="#pc-{p.symbol()}" x="{x}" y="{y}" width="{S}" height="{S}"/>')
    out.append("".join(pcs))
    out.extend(_arrow(a, z, c, orient) for a, z, c in arrows)
    out.append("</svg>")
    return "".join(out)



def _bg_symbols():
    sym = []
    for p in "KQRBNP":
        g = re.sub(r"\s+", " ", chess.svg.PIECES[p])
        g = re.sub(r' (id|class)="[^"]+"', "", g)
        g = re.sub(r'(fill|stroke)="#(?:fff|000)"', lambda m: f'{m.group(1)}="currentColor"', g)
        g = re.sub(r'(fill|stroke):#(?:ffffff|000000)', lambda m: f'{m.group(1)}:currentColor', g)
        sym.append(f'<symbol id="b{p}" viewBox="0 0 45 45">{g}</symbol>')
    return "".join(sym)


BG_DEFS = ('<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#08101c"/><stop offset=".38" stop-color="#16315e"/>'
           '<stop offset=".55" stop-color="#0c1a31"/><stop offset="1" stop-color="#060a12"/></linearGradient>'
           '<radialGradient id="glow" cx=".5" cy=".38" r=".55"><stop offset="0" stop-color="#6d9dff" stop-opacity=".5"/>'
           '<stop offset="1" stop-color="#6d9dff" stop-opacity="0"/></radialGradient>'
           '<radialGradient id="vig" cx=".5" cy=".45" r=".75"><stop offset=".55" stop-color="#05080e" stop-opacity="0"/>'
           '<stop offset="1" stop-color="#05080e" stop-opacity=".85"/></radialGradient>'
           + "".join(f'<filter id="bl{i}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="{b}"/></filter>'
                     for i, b in enumerate((0.5, 1.5, 3, 5, 9, 18)))
           + '<filter id="rim" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="6" result="b"/>'
             '<feFlood flood-color="#8fb4ff" flood-opacity=".7"/><feComposite in2="b" operator="in" result="g"/>'
             '<feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')


def _piece(p, x, y, size, color, blur=0, op=1.0, rim=False):
    f = ' filter="url(#rim)"' if rim else (f' filter="url(#bl{blur})"' if blur else "")
    return (f'<use href="#b{p}" x="{x - size / 2:.1f}" y="{y - size * 0.9:.1f}" width="{size:.1f}" height="{size:.1f}" '
            f'color="{color}"{f} opacity="{op}"/>')


def background_uri(variant="night"):
    """The pre-rendered background scene (assets/bg-<variant>.webp) as a data: URI."""
    return asset_uri(f"bg-{variant}.webp")


def background_svg(variant="fog", seed=7):
    """An original faded chess scene for the page background (no photos), in the report's blue palette.
    variant: "fog"  - a board in perspective that disappears into blue fog, two armies facing each other;
             "king" - a large king and queen in the light on the right, out-of-focus pieces and bokeh;
             "night" - a dark, quiet board edge at the bottom with a few pieces and a soft glow (most subtle)."""
    import random
    rnd = random.Random(seed)
    W, Hh = 1600, 1000
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {Hh}" preserveAspectRatio="xMidYMid slice">'
           f'<defs>{_bg_symbols()}{BG_DEFS}</defs><rect width="{W}" height="{Hh}" fill="url(#sky)"/>']

    def board(hz, cx, rows, sq, k, fade):
        def proj(x, z):
            s = 1 / (1 + z * k)
            return cx + x * sq * s, hz + (Hh - hz) * s, s
        for zi in range(rows):
            for xi in range(-8, 8):
                (x1, y1, _), (x2, _, _) = proj(xi, zi), proj(xi + 1, zi)
                (x3, y3, _), (x4, _, _) = proj(xi + 1, zi + 1), proj(xi, zi + 1)
                op = max(0.0, 0.9 - zi * fade)
                out.append(f'<polygon points="{x1:.1f},{y1:.1f} {x2:.1f},{y1:.1f} {x3:.1f},{y3:.1f} {x4:.1f},{y3:.1f}" '
                           f'fill="{"#2c5090" if (xi + zi) % 2 == 0 else "#0b1730"}" opacity="{op:.2f}"/>')
        return proj

    def bokeh(n, y0, y1, rmin, rmax):
        for _ in range(n):
            out.append(f'<circle cx="{rnd.uniform(0, W):.0f}" cy="{rnd.uniform(y0, y1):.0f}" r="{rnd.uniform(rmin, rmax):.0f}" '
                       f'fill="#a9c6ff" opacity="{rnd.uniform(.05, .2):.2f}" filter="url(#bl4)"/>')

    if variant == "fog":
        hz = 380
        out.append(f'<rect width="{W}" height="{Hh}" fill="url(#glow)"/>')
        proj = board(hz, 800, 18, 150, 0.2, 0.045)
        out.append(f'<rect y="{hz - 60}" width="{W}" height="200" fill="#7fa6f5" opacity=".18" filter="url(#bl5)"/>')
        placed = []
        for z, row, col in [(9, "RNBQKBNR", "#1d3459"), (8, "PPPPPPPP", "#1d3459"), (3, "PPPPPPPP", "#d7e5ff"), (2, "RNBQKBNR", "#d7e5ff")]:
            for i, p in enumerate(row):
                if p == "P" and rnd.random() < 0.3:
                    continue
                placed.append((z + 0.5, i - 3.5, p, col))
        for z, x, p, col in sorted(placed, key=lambda t: -t[0]):
            px, py, s = proj(x, z)
            size = 175 * s * (1.18 if p in "KQ" else 1)
            blur = 0 if 2 <= z <= 3.6 else 1 if z < 7 else 2
            out.append(_piece(p, px, py, size, col, blur, .95 if z < 5 else .8, rim=(z < 5)))
        bokeh(22, 120, 520, 8, 38)
    elif variant == "king":
        out.append('<ellipse cx="1180" cy="430" rx="620" ry="420" fill="url(#glow)"/>')
        proj = board(560, 1000, 12, 170, 0.3, 0.07)
        bokeh(30, 60, 700, 10, 60)
        for p, x, y, s, c, b in [("R", 300, 640, 150, "#1d3459", 4), ("P", 520, 650, 120, "#d7e5ff", 3), ("B", 760, 640, 170, "#1d3459", 2),
                                 ("N", 960, 700, 230, "#c9dbff", 1)]:
            out.append(_piece(p, x, y, s, c, b, .75))
        out.append(_piece("Q", 1340, 760, 380, "#1d3459", 0, .95, rim=True))
        out.append(_piece("K", 1130, 820, 470, "#e3edff", 0, 1, rim=True))
        out.append(_piece("P", 160, 1010, 320, "#e3edff", 5, .5))
    else:  # night
        out.append('<ellipse cx="800" cy="980" rx="900" ry="300" fill="#2c5090" opacity=".35" filter="url(#bl5)"/>')
        board(760, 800, 7, 260, 0.35, 0.11)
        bokeh(14, 80, 600, 6, 26)
        for p, x, y, s, c, b, o in [("K", 260, 960, 260, "#c9dbff", 2, .55), ("N", 1360, 970, 300, "#1d3459", 1, .8),
                                    ("P", 1120, 905, 140, "#c9dbff", 2, .5), ("Q", 560, 870, 150, "#1d3459", 3, .55)]:
            out.append(_piece(p, x, y, s, c, b, o, rim=(b <= 1)))
    out.append(f'<rect width="{W}" height="{Hh}" fill="url(#vig)"/></svg>')
    return "".join(out)
