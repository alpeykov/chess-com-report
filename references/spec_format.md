# report_spec.json

`build_report.py` turns this JSON into the HTML page. All `html` fields are raw HTML (escape `<`, `&` in plain text yourself).

```json
{
  "langs": ["bg", "en", "fr"],        // first = default; then every text field may be {"bg": .., "en": .., "fr": ..}
  "lang": "fr",                       // single-language reports only (used when "langs" is missing)
  "labels": {"move": "Zug"},          // optional overrides of the built-in labels
  "piece_words": "both",              // optional: true = moves written with piece names ("Bxe4" -> "Fou prend e4"),
                                      // "both" = names plus the standard notation in grey, {"Q": "..."} = own words
  "title": "Rapport d'échecs : USERNAME",
  "page_title": "Échecs USERNAME",    // optional, browser tab
  "subtitle": "383 parties · 1er mars – 13 nov. 2026",
  "tiles": [{"value": "575", "label": "Classement actuel"}],
  "summary_html": "<p><b>En bref :</b> ...</p>",
  "game_analysis": {
    "title": "Analyse de partie : victoire contre X",
    "sub_html": "13 nov. · Blancs (575) contre X (537) · 10 min · <a href=\"LINK\">la partie</a>",
    "html": "<p>...</p><div class=\"scroll\"><table>...{{GOTO:game:60:31}}...</table></div><h3>...</h3>",
    "viewer": {"game": "last", "orientation": "white", "title": "...",
               "notes": {"0": "...", "60": "..."}, "arrows": {"60": [["c1", "c4", "green"]]}}
  },
  "sections": [
    {"id": "openings", "title": "2. Ouvertures", "toc_title": "Ouvertures", "html": "<p>...</p>{{V:caro}}"}
  ],
  "viewers": {
    "caro":  {"moves": "e4 c6 d4 d5 e5 Bf5 Nf3 e6", "orientation": "black", "title": "Caro-Kann",
              "notes": {"6": "...Bf5 avant ...e6"}, "arrows": {"6": [["c8", "f5", "green"]]}},
    "g231":  {"game": 231, "from_ply": 50, "to_ply": 60, "orientation": "white", "title": "Partie 231",
              "notes": {"52": "..."}, "fills": {"52": {"e3": "red"}}}
  },
  "footer_html": "Données : API publique chess.com ..."
}
```

## Viewers

Source, one of:
- `"moves"`: SAN string from the start position (opening lines);
- `"game": N`: game number `n` from `games.json`;
- `"game": "last"`: `OUT/last.pgn`.

Options: `orientation` (`white`/`black`, use the player's colour), `from_ply`/`to_ply` (show only part of a game), `notes`, `arrows` (`[from, to, colour]`, colours `green` good move, `red` threat/mistake, `yellow` idea, `blue` neutral), `fills` (square → colour), `start_index` (frame shown first).

Keys of `notes`/`arrows`/`fills` are frame numbers = plies played (see SKILL.md conventions).

## Placeholders (in any html field)

- `{{CHART}}`: rating line of the main time class, wins green, losses red.
- `{{V:id}}`: a viewer from `viewers` (the game-analysis board is `game` and is placed automatically).
- `{{GOTO:id:ply:text}}`: button that shows that viewer at frame `ply`.

Useful layout classes: `vgrid` (grid of boards), `lg` (two columns: board + text), `scroll` (wrap tables), `panel`, `callout`, `bars`/`bar`/`track`/`fill`/`pct` (horizontal score bars, add `low` to `fill` for weak values), `tag w|l|n`, `hint`, `sub`.

## Piece names

With `piece_words`, every move in captions, tables and the board's move line is written with piece names in the
report language (bg: Цар, Царица, Топ, Офицер, Кон, пешка; "x" -> "взима"; O-O -> "рокада"). Pawn pushes such as
`e4` are named only after a move number or next to another move, so a square in a sentence stays a square.
To show the two side by side in a table, put the move twice: `<span class="words-only">Bxe4?</span>` (names only)
and `<code>Bxe4?</code>` (left in standard notation).

## Sections and contents

Section titles may start with their number ("3. Openings"): the number goes into the coloured badge and the contents card. The game analysis gets a knight badge and comes first. `toc_title` is the short name used in the contents card.
