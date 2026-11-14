"""Wooden board with metal pieces, drawn as SVG.

DEFS goes into the page once (piece shapes, wood textures, gradients); render() returns one small SVG per position
that refers to them with <use>. Pieces are the python-chess (Colin M.L. Burnett) shapes with a silver / dark-steel
finish; the board has maple and walnut squares with grain and a dark wooden frame with coordinates on all sides.
"""
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


DEFS = (
    "<defs>"
    '<linearGradient id="mW" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/>'
    '<stop offset=".4" stop-color="#e4e6ea"/><stop offset=".72" stop-color="#a9adb4"/><stop offset="1" stop-color="#f1f2f4"/></linearGradient>'
    '<linearGradient id="mB" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8a9099"/>'
    '<stop offset=".33" stop-color="#3a3e45"/><stop offset=".7" stop-color="#16181c"/><stop offset="1" stop-color="#4c5159"/></linearGradient>'
    '<filter id="pcShadow" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx=".6" dy="1.4" stdDeviation=".9" '
    'flood-color="#000" flood-opacity=".55"/></filter>'
    '<filter id="grainH" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.006 0.21" '
    'numOctaves="3" seed="4"/><feColorMatrix values="0 0 0 0 .35  0 0 0 0 .2  0 0 0 0 .08  0 0 0 -1.6 1.15"/></filter>'
    '<filter id="grainV" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.21 0.006" '
    'numOctaves="3" seed="11"/><feColorMatrix values="0 0 0 0 .2  0 0 0 0 .1  0 0 0 0 .03  0 0 0 -1.6 1.15"/></filter>'
    f'<pattern id="woodL" patternUnits="userSpaceOnUse" x="{M}" y="{M}" width="{8 * S}" height="{8 * S}">'
    f'<rect width="{8 * S}" height="{8 * S}" fill="#e6c79a"/><rect width="{8 * S}" height="{8 * S}" filter="url(#grainH)" opacity=".38"/></pattern>'
    f'<pattern id="woodD" patternUnits="userSpaceOnUse" x="{M}" y="{M}" width="{8 * S}" height="{8 * S}">'
    f'<rect width="{8 * S}" height="{8 * S}" fill="#a86e3e"/><rect width="{8 * S}" height="{8 * S}" filter="url(#grainV)" opacity=".42"/></pattern>'
    f'<pattern id="woodF" patternUnits="userSpaceOnUse" width="{N}" height="{N}">'
    f'<rect width="{N}" height="{N}" fill="#4a2e1b"/><rect width="{N}" height="{N}" filter="url(#grainH)" opacity=".5"/></pattern>'
    '<radialGradient id="checkGlow"><stop offset="0" stop-color="#ff3b30" stop-opacity=".95"/>'
    '<stop offset=".55" stop-color="#ff3b30" stop-opacity=".45"/><stop offset="1" stop-color="#ff3b30" stop-opacity="0"/></radialGradient>'
    + "".join(_piece_symbol(s) for s in "KQRBNPkqrbnp")
    + "</defs>"
)


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
    out.append(f'<g filter="url(#pcShadow)">{"".join(pcs)}</g>')
    out.extend(_arrow(a, z, c, orient) for a, z, c in arrows)
    out.append("</svg>")
    return "".join(out)
