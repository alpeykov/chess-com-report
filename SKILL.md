---
name: chess-com-report
description: Build a personal chess improvement report (single HTML file with interactive boards) from a player's public chess.com games, in English, French or Bulgarian. Use when the user gives a chess.com username and asks for a chess report, an analysis of their games or habits, or says "analyze the last game" / "regenerate the report" for an existing report.
---

# chess.com report

Input: a chess.com **username** and a **report language** (`en`, `fr`, `bg`; any other language works if you also pass `labels` in the spec). If either is missing, ask once.

Output: one self-contained `report.html` (dark theme, step-through boards, rating chart, no external files), saved where the user asks (default: `~/Downloads/chess-report-<username>/report.html`).

Requirements: Python 3.9+ and `python-chess` (`pip install chess`). Games come from the public API `https://api.chess.com/pub/...`; no login. Use a generic User-Agent (the scripts already do) and never send the user's personal details anywhere.

Scripts are in `scripts/` (run them from that folder or pass full paths). `OUT` below is a working folder, e.g. `~/Downloads/chess-report-<username>/data`.

## Three commands

| User says | Do |
|---|---|
| first request / "make my report" | Full workflow below (steps 1-6). |
| "analyze the last game" | Steps 1 (`--last-only`), 4, then replace **only** `game_analysis` in the existing spec and rebuild (step 6). Do not recompute statistics or rewrite other sections. |
| "regenerate the report" | Steps 1-3 and 5-6 with all games; keep the current `game_analysis` as it is. |

Keep `OUT/report_spec.json` between runs: it is the source of the report, so later commands edit it instead of starting over.

## Workflow

1. **Download**
   `python fetch_games.py USERNAME --dir OUT` → `OUT/games.pgn` (all standard games, oldest first) and `OUT/last.pgn`.
   `--months N` limits history; `--last-only` fetches only the newest game.

2. **Statistics**
   `python stats.py USERNAME --dir OUT` (counts only the most played time class, e.g. rapid; `--time-class all` or `--time-class blitz` to change) → `OUT/games.json` (one row per game, `n` = game number) and `OUT/summary.json`: record by colour, rating first/now/peak/low, last 50 games, how games were lost and won, queen-lost games, losses within 15 moves, resignations at -3 or better, tilt (results after a win / after 1-3 losses in a row on the same day, and by game-of-the-day), openings (first moves, replies as Black, named openings, early bishop checks), quarters of the history.
   **Every number in the report must come from these files.** Recompute with a short Python snippet over `games.json` when you need a number they do not have; never estimate.

3. **Mistake scan (history)**
   `python scan.py USERNAME --dir OUT --games 120` → `OUT/flagged.json`: the player's moves that lost material, allowed mate, missed a mate or missed free material. The top items are re-checked at depth 5 and carry `line` (best line) and `after` (what the played move allowed). Takes a few minutes; run it in the background for long histories.
   Group the flagged moves into **recurring patterns** (e.g. "queen left undefended", "missed back-rank mate", "missed fork"). Pick 2-4 clear examples per pattern for boards.

4. **Last game (both sides)**
   `python scan.py USERNAME --dir OUT --pgn OUT/last.pgn` → prints every move and writes `OUT/last_flagged.json` with verified lines for both players.
   Also look for forced mates the player missed when attacking (positions just before and during an attack). The engine is a material search: it finds hanging pieces, forks and mates in 1-3, not positional ideas. Only state tactics you verified with a printed line; if unsure, run `engine.pv` on the position.

5. **Write the spec** `OUT/report_spec.json` in the chosen language. Format: `references/spec_format.md`. Recommended sections (adapt to what the data shows; skip a section with nothing to say):
   1. Overview: tiles (games, record, rating now/peak, score in last 50), `{{CHART}}`, 3-5 key findings.
   2. Openings: table per situation (White first move, Black vs 1.e4 / 1.d4) with score % and games, conclusion per row; boards for the main lines and for the most costly opening habit.
   3. Tilt and session length: score after a win vs after 1, 2, 3 losses; games 1-5 / 6-20 / 21+ of a day; a concrete stop rule.
   4. How games are lost: mated, time, resignation, queen lost; how early.
   5. Recurring tactical mistakes: one subsection per pattern with boards from `flagged.json`, the verified line in the caption, and one habit to fix it.
   6. Missed wins: missed mates and free material.
   7. Plan: 3-5 concrete habits ranked by points saved, plus what is already working.
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
- Language: everything the reader sees (titles, captions, tables, buttons) is in the chosen language; chess notation stays in English SAN.
