# report_spec.json

`build_report.py` turns this JSON into the HTML page. All `html` fields are raw HTML (escape `<`, `&` in plain text yourself).

```json
{
  "lang": "fr",                       // en | fr | bg (button/chart labels); other languages: add "labels"
  "labels": {"move": "Zug"},          // optional overrides of the built-in labels
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
