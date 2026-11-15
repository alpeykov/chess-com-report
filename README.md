# chess-com-report

A Claude skill that builds a personal chess improvement report from a player's public chess.com games: one self-contained HTML file with statistics, a rating chart, opening and tilt analysis, recurring tactical mistakes and step-through boards. Reports can be in English, French or Bulgarian.

## Install

- **Claude Code:** copy this folder to `~/.claude/skills/chess-com-report`.
- **claude.ai:** zip the folder and upload it under Settings → Capabilities → Skills.

Requirements: Python 3.9+ and `pip install chess`. No chess.com login is needed, because the games come from the public API.

### Stockfish (optional, recommended)

The deeper analysis (accuracy, move classes, evaluation graph, clock, motifs, puzzles) needs the free [Stockfish](https://github.com/official-stockfish/Stockfish) engine (GPLv3). It is not included here; install it once:

- **Windows:** download `stockfish-windows-x86-64-universal.zip` from the [latest release](https://github.com/official-stockfish/Stockfish/releases/latest), unzip it (e.g. to `C:\projects\stockfish`) and set `STOCKFISH_PATH` to the `.exe`.
- **Linux (Debian/Ubuntu):** `sudo apt install stockfish` (installs `/usr/games/stockfish`), or download `stockfish-ubuntu-x86-64-avx2.tar` from the release page, unpack it and set `STOCKFISH_PATH`.
- **macOS:** `brew install stockfish`.

Check: `python -c "import sys; sys.path.insert(0, 'scripts'); import sf_engine; print(sf_engine.find_stockfish())"` prints the path.

Update: `python scripts/update_stockfish.py` installs the latest release in place of the old one (`--check` only reports). The skill runs it before every "analyze the last game" and "regenerate the report". Without Stockfish the report still works with the built-in material engine.

## Use

- "Make my chess report. chess.com username: USERNAME, language: French"
- "analyze the last game": analyzes only the newest game and replaces the game-analysis section.
- "regenerate the report": adds new games and recomputes the statistics.

See [SKILL.md](SKILL.md) for the workflow and [references/spec_format.md](references/spec_format.md) for the report spec.

## Scripts

| Script | Purpose |
|---|---|
| `fetch_games.py` | Download games from the chess.com public API |
| `stats.py` | Record, rating, openings, tilt and how games are lost |
| `scan.py` | Find mistakes and missed mates; verify the key moves at depth 5 |
| `build_report.py` | Assemble the HTML report from `report_spec.json` |
| `engine.py` | Small material search (alpha-beta and quiescence), no Stockfish needed |
| `sf_engine.py`, `sf_scan.py` | Stockfish analysis: accuracy, move classes, phases, clock, motifs, opening exit, puzzles |
| `update_stockfish.py` | Check for a newer Stockfish release and install it |
| `update_skill.py` | Pull a newer version of this skill from its git repository |
| `board_svg.py` | Board, pieces and background scenes |
