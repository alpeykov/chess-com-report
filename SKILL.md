---
name: chess-com-report
description: Build a personal chess improvement report (single HTML file with interactive boards) from a player's public chess.com games, in English, French or Bulgarian. Use when the user gives a chess.com username and asks for a chess report, an analysis of their games or habits, or says "analyze the last game" / "regenerate the report" for an existing report.
---

# chess.com report

Input: a chess.com **username** and a **report language** (`en`, `fr`, `bg`). If the username is missing, ask once.

Reports are **multi-language by default**: `"langs": [main, the other two]` (main language first, e.g. `["bg", "en", "fr"]`), and every text field in the spec is `{"bg": ..., "en": ..., "fr": ...}`. The page shows flag buttons at the top and remembers the reader's choice (`?lang=en` in the URL also works). Write all three versions yourself; keep chess notation identical across them.

Look: dark blue theme (Archivo font) over a faded chess scene drawn in SVG (`board_svg.background_svg`, spec `background`), a wooden board with metal pieces and coordinates on all four sides (`scripts/board_svg.py`; boards are drawn in the browser from compact position data, textures are small pictures in `assets/`), a collapsible contents card with coloured numbered badges that highlights the section in view, numbered section cards and a back-to-top button.

Output: one self-contained `report.html` (dark theme, step-through boards, rating chart, no external files), saved where the user asks (default: `~/Downloads/chess-report-<username>/report.html`).

Requirements: Python 3.9+ and `python-chess` (`pip install chess`). Games come from the public API `https://api.chess.com/pub/...`; no login. Use a generic User-Agent (the scripts already do) and never send the user's personal details anywhere.

Scripts are in `scripts/` (run them from that folder or pass full paths). `OUT` below is a working folder, e.g. `~/Downloads/chess-report-<username>/data`.

**Report folder layout** (keep the root clean, only the report at the top):
```
chess-report-<username>/
  report.html        the report, nothing else in the root
  data/              games, statistics, scan results, report_spec.json, history.json
    sf/              Stockfish cache per game
    logs/            scan output
    old/             earlier copies of results
  scripts/           the report's own spec writer (make_spec.py), helpers and a README
  content/           hand-written material, e.g. recommended resources per language
```

## Three commands

| User says | Do |
|---|---|
| first request / "make my report" | Full workflow below (steps 1-6). |
| "analyze the last game" | Steps 1 (`--last-only`), 3b for the last game, 4 and 4b, then replace **only** `game_analysis` in the existing spec and rebuild (step 6). Then run `python archive_game.py --dir OUT`: it keeps the analysis in the skill's `game_analysis/<date>_<white>-<black>_<id>/` folder (ignored by git): the PGN, Stockfish data, the spec part and a standalone `analysis.html`. Then `python game_index.py USERNAME --out OUT_PAGES --home <main report file>` writes `games.html` (every analysed game, newest first: date, colour, opponent and ratings, result and how it ended, opening, moves, accuracy, mistakes; a click on a row opens the game) and one `game-<id>.html` per game, each with links back to the main report and to the list. The main report does not show the game itself: with `"games_page": "games.html"` in the spec the builder puts a „Анализ на партиите“ link at the top instead. Publish the main page with these pages as `files` (home = `index.html` there; `report.html` in the local folder), then **open the new game's page in the browser** without being asked. Do not recompute statistics or rewrite other sections. |
| "regenerate the report" | Steps 1-3 and 5-6: download and statistics cover all games, the scan adds only the new games (a few seconds); keep the current `game_analysis` as it is. Before rebuilding, search the spec (or the script that writes it) for numbers typed into the text instead of read from the data files, and update them or make them computed. Then `history.py --add`. |

**Before "analyze the last game" and "regenerate the report"**, first run `python update_skill.py`: it fetches the skill's own git repository and, if there is a newer version, pulls it (fast-forward only; local changes are kept and reported). If it pulled, re-read this file before going on. Tell the user in one line if the skill was updated. Then run `python update_stockfish.py`: the skill keeps its own Stockfish in `<skill>/stockfish/` (ignored by git); the script installs it there from the official GitHub releases if it is missing, and replaces it when there is a newer release. Other installs (STOCKFISH_PATH, apt/brew, C:/projects/stockfish) are never touched. Then do the analysis. Tell the user in one line if Stockfish was installed or updated. If GitHub cannot be reached, go on with the installed version.

Keep `OUT/report_spec.json` between runs: it is the source of the report, so later commands edit it instead of starting over.

## Workflow

1. **Download**
   `python fetch_games.py USERNAME --dir OUT` → `OUT/games.pgn` (all standard games, oldest first) and `OUT/last.pgn`.
   `--months N` limits history; `--last-only` fetches only the newest game.

2. **Statistics**
   `python stats.py USERNAME --dir OUT` (counts every game; `--time-class main` or e.g. `--time-class rapid` to keep one time class; the rating chart always uses the most played time class) → `OUT/games.json` (one row per game, `n` = game number) and `OUT/summary.json`: record by colour, rating first/now/peak/low, last 50 games, how games were lost and won, queen-lost games, losses within 15 moves, resignations at -3 or better, tilt (results after a win / after 1-3 losses in a row on the same day, and by game-of-the-day), openings (first moves, replies as Black, named openings, early bishop checks), quarters of the history.
   **Every number in the report must come from these files.** Recompute with a short Python snippet over `games.json` when you need a number they do not have; never estimate.

3. **Mistake scan (history)**
   `python scan.py USERNAME --dir OUT` (first run: all games, in parallel on all cores; later runs scan only the games not in `OUT/scanned.json` and keep the earlier results; `--full` rescans everything; `--games N` = only the last N) → `OUT/flagged.json`: the player's moves that lost material, allowed mate, missed a mate or missed free material. The 60 biggest items of each kind (missed mate, allowed mate, lost material, missed gain) are re-checked at depth 5 and carry `line` (best line) and `after` (what the played move allowed); the rest keep only the depth-3 result. About 1 minute per 16 games on 16 cores; run it in the background.
   Group the flagged moves into **recurring patterns** (e.g. "queen left undefended", "missed back-rank mate", "missed fork"). Pick 2-4 clear examples per pattern for boards.

3b. **Stockfish (recommended)**
   `python sf_scan.py USERNAME --dir OUT` → `OUT/sf_games.json`, `OUT/sf_moves.json`, `OUT/sf_summary.json`: accuracy (lichess formula), blunders / mistakes / inaccuracies by win-% drop (30/20/10), errors by phase, clock use from `%clk`, tactical motifs missed and allowed (undefended piece, fork, pin, skewer, discovered attack, mates), win % after move 10 by opening, and 12 puzzles with lichess links. Cached per game in `OUT/sf/`, so only new games are analysed (about 2 minutes for 400 games on 16 cores at 0.05 s per position). Stockfish is found via `--stockfish`, `STOCKFISH_PATH`, the skill's own copy in `stockfish/` (installed by `update_stockfish.py`), `stockfish` on PATH or `C:/projects/stockfish`; without it skip this step and say in the report that only the material engine was used.
   For the last game: `python sf_scan.py USERNAME --dir OUT --pgn OUT/last.pgn` → `OUT/sf_last.json` (0.3 s per position, ~20 s); put its `evals` into the game viewer (`"evals": [...]`) to draw the evaluation graph under the board, and use its classes and accuracy in the text. The graph and every "chances" number in the text are from the **player's side** (the board orientation): `evals` are White's %, the builder flips them for a Black viewer; in the text write 100 − value when the player is Black.
   Report sections from these files: Accuracy and mistakes (with phases), Coming out of the opening, Tactical motifs, The clock, Puzzles from your games. Keep a **Recommended material** section at the end: free resources as tabs, one per language (`<div class="tabs"><div class="tab" data-tab="bg" data-label="Български">...</div>...</div>`); the tab in the page's language opens first.

3c. **Lichess opening explorer (recommended)**
   `python explorer.py USERNAME --dir OUT` → `OUT/explorer.json`: the first 12 moves of every game compared with the lichess database of players at a similar level (rating bands from the current rating + 400, e.g. 1000–1399 for 600 on chess.com; `--ratings`, `--speeds` to change). It notes where each game left the known moves (played at least `--min-games` 50 times) and who left first, the player's repeated positions with the database share and score of each move, the usual moves that score at least 4 points below a popular alternative (`weak`), and the player's own repeated departures (`novelties`). For the first six `weak` entries it also stores `ideas` (`move_ideas.py`): what the usual and the better move do on the board (attacks, centre, development, bishops opened or shut in, a pawn offered and whether it comes back after the capture) and Stockfish's win % for the player's colour with its main line; without Stockfish only the board facts. Only board positions are sent to lichess, no user name. Positions are cached in `OUT/explorer/cache.json`: the first run asks about 1–2 thousand positions (10–20 minutes, run it in the background), later runs only the new games' positions. On "regenerate the report" run it after the Stockfish scan.
   Section: `explorer_section.build(json.load(...))` returns the section (`id` "explorer", bg/en/fr, every number from the file) and its viewers (`ex1`, `ex2`: red arrow = the usual move, green = the better-scoring one; the notes under the boards explain both moves from `ideas`); add both to the spec, after "Coming out of the opening". Without network or without the file, leave the section out.

4. **Last game (both sides)**
   `python scan.py USERNAME --dir OUT --pgn OUT/last.pgn` (depth 4, all moves in parallel, about 1 minute) → prints every move and writes `OUT/last_flagged.json` with verified lines for both players.
   Also look for forced mates the player missed when attacking (positions just before and during an attack). The engine is a material search: it finds hanging pieces, forks and mates in 1-3, not positional ideas. Only state tactics you verified with a printed line; if unsure, run `engine.pv` on the position.

4b. **Last game, deeper (needs Stockfish)**
   `python last_game.py USERNAME --dir OUT` (after `sf_scan.py --pgn OUT/last.pgn`; about 30 s) → `OUT/last_extra.json`: for each of the player's mistakes, blunders and missed mates the accepted moves and solution line (a puzzle), the time spent and left, the **threat** in the position (null move: what the opponent would play if it were their turn again), what the move allowed, and how often the same motif came up in the last 50 games; the opponent's mistakes and whether the reply punished them; the opening against the lichess explorer (where the known moves ended, who left first, weaker choices; uses `explorer.json` params and cache, skipped offline); this game against the average of the previous 20 games.
   A move that gives away 3 or more points of material against the best reply counts as a mistake (5+: a blunder) even when the win % barely moves because the position stays won (e.g. a queen left to a pawn when far ahead); call it a blunder in the text too.
   `last_game_section.build(json.load(...))` returns `(html, viewers)`: append `html` to `game_analysis["html"]` and add the viewers (`lgp1`… interactive puzzles: a viewer with `"puzzle": {"ok": [uci, ...]}` waits for the reader's move — click a piece, then a square — and opens the solution once solved or on "Show the answer"). Keep the hand-written key-moment table; these blocks come after it.

5. **Write the spec** `OUT/report_spec.json` in the chosen language. Format: `references/spec_format.md`. Recommended sections (adapt to what the data shows; skip a section with nothing to say):
   1. Overview: tiles (games, record, rating now/peak, score in last 50), `{{CHART}}`, 3-5 key findings.
   2. Openings: table per situation (White first move, Black vs 1.e4 / 1.d4) with score % and games, conclusion per row; boards for the main lines and for the most costly opening habit.
   3. Tilt, sessions and breaks: score after a win vs after 1, 2, 3 losses; score by the game's place in a session and by the break length before the next game after 1 or 2 losses (`summary.json` → `sessions`); a concrete rule for how long to stop.
   4. How games are lost: mated, time, resignation, queen lost; how early.
   5. Recurring tactical mistakes: one subsection per pattern with boards from `flagged.json`, the verified line in the caption, and one habit to fix it.
   6. Missed wins: missed mates and free material.
   7. Plan: 3-5 concrete habits ranked by points saved, plus what is already working.
   In the key-moment table the last column („Обяснение“ / Explanation) must be specific and complete: the winning chances before → after (from `sf_last.json`), what the played move did or failed to do (which piece, which square, which threat), the idea of the better move with its concrete line, and what the opponent could or did do next. Never just "better move" or "lost material". In a suggested line that was not played, say where each piece comes from ("your bishop from d3 takes the knight on e4, Black takes back with the f5 bishop") and stop the line as soon as the point is clear; a bare continuation like "16.Ne5" reads as if it happened in the game.
   **Never leave the material or the outcome implied.** In every row and suggested line say the material balance before the move and at the end of the line ("you are a bishop down", "you end with queen against queen and rook") and what the line leads to: a perpetual check is a **draw** (say so — 50% after a sacrifice is not an equal position), winning a piece, mate. When the best move is a sacrifice, also give the best move without it and its chances.
   Explain **why the played move lost the evaluation** (what it allowed: compare Stockfish on the position after it), not just the plan of the engine's best move. Before giving a "the better move wins X" claim, test the opponent's obvious defence with Stockfish (e.g. the attacked pawn simply moving on) and mention it with its result; the player will think of it. Do not stake the whole explanation on a slow plan the opponent can sidestep. When the player disputes a moment, check their idea with Stockfish before answering, say plainly which part they are right about, and correct the text.
   Key-moment table layout: one row with move number (GOTO button), played (words + `<code>` notation), better (words + `<code>`), then a second row `<tr class="mv-exp"><td colspan="5">…</td></tr>` with the explanation across the full width.
   Also include, when the data shows them: **King safety** (mates on f7/f2, back rank, g7/g2, early Qh5), recurring patterns such as **knight forks on c7**, **Resigning too early**, and in Progress a table **between the reports** (periods from `history.py`): score, rating, Stockfish accuracy, quick losses, early bishop checks, opening scores, early resignations, queen losses, mates, after 2 losses.
   Plus `game_analysis` for the last game: summary (2-3 sentences), key-moment table (move, played, better, what happened) where each move number is a `{{GOTO:game:PLY:N}}` button, "what you did well", one lesson linked to a general habit. Board orientation = the player's colour.

6. **Build and check**
   `python build_report.py --dir OUT --out PATH/report.html`
   Then open the file and check: no unresolved `{{...}}` (the builder refuses those), every GOTO button opens the decision position, captions match the board, the board is from the player's side, numbers match `summary.json`.

## Conventions (get these right)

- `ply` = half-moves already played. Frame/ply `k` shows the position **after** `k` half-moves. White's move N is played from ply `2N-2` and leads to `2N-1`; Black's move N goes from `2N-1` to `2N`.
- Notes and arrows are keyed by `k` (as strings in JSON). A note stays visible until the next note.
- A GOTO button for "move N" should normally point to the **decision position** (before the move), so the reader can look for the better move.
- In tables, mark moves with `?` (mistake), `??` (blunder), `!` (good), `?!` (dubious) and colour tags `<span class="tag w|l|n">`.
- Write for a club player: short sentences, no engine scores, name squares and pieces, explain *why* a move fails.
- Notation: if the user finds SAN hard to read, set `"piece_words": "both"` (names plus standard notation) or `true` (names only); in key-moment tables give separate columns with `<span class="words-only">` and `<code>` (see references/spec_format.md).
- Bulgarian wording: say **„фигура“**, never „материал“ (e.g. „губи фигура“, „пропуснати фигури“, „изоставате във фигури“); a piece that can be taken for nothing is a **„незащитена фигура“**, never „безплатен материал“; the queen is **„царица“**, not „дама“. The colour adjective follows the я/е rule: **„бялата“** царица/пешка, **„бялото“** поле, but „белият“ топ, „белите“ (never „белата“). A score percentage is **„успеваемост“** (wins + ½ per draw ÷ games); always say over which games it is and give the W–L–D numbers next to it. The latest-game section is called **„Последна партия (date): победа/загуба срещу X“** (en: “Latest game”, fr: « Dernière partie »).
- File letters: when a letter names a file ("линията e", "the e-file", "la colonne e", "пешката на h", "the h-pawn"), the builder shows it bold and italic (***e***), without quotes; write the plain letter in the spec, in those word patterns, so the builder can find it.
- Language: everything the reader sees (titles, captions, tables, buttons) is in the chosen language; chess notation stays in English SAN.
