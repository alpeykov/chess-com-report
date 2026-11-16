# chess-com-report

A Claude skill that builds a personal chess improvement report from a player's public chess.com games: one self-contained HTML file with statistics, a rating chart, opening and tilt analysis, recurring tactical mistakes and step-through boards. Reports can be in English, French or Bulgarian.

## Install

- **Claude Code:** copy this folder to `~/.claude/skills/chess-com-report`.
- **claude.ai:** zip the folder and upload it under Settings → Capabilities → Skills.

Requirements: Python 3.9+ and `pip install chess`. No chess.com login is needed, because the games come from the public API.

### Stockfish (optional, recommended)

The deeper analysis (accuracy, move classes, evaluation graph, clock, motifs, puzzles) needs the free [Stockfish](https://github.com/official-stockfish/Stockfish) engine (GPLv3). It is not stored in this repository, but **no manual setup is needed**: `python scripts/update_stockfish.py` downloads the latest official release into the skill's own folder, `stockfish/` (ignored by git), and on later runs replaces it when a newer release comes out (`--check` only reports). The skill runs it before every "analyze the last game" and "regenerate the report", and `sf_scan.py` runs it by itself when no Stockfish is found at all.

Builds: `windows-x86-64-universal` on Windows, `ubuntu-x86-64-avx2` on Linux, the Apple Silicon or x86-64 build on macOS. To use another install instead, pass `--stockfish PATH` or set `STOCKFISH_PATH`; installs from apt, brew or `C:\projects\stockfish` are used only when the skill's copy is missing (for example offline) and are never changed.

Check: `python -c "import sys; sys.path.insert(0, 'scripts'); import sf_engine; print(sf_engine.find_stockfish())"` prints the path. Without Stockfish the report still works with the built-in material engine.

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
| `update_stockfish.py` | Install Stockfish in the skill folder and keep it on the latest release |
| `explorer.py`, `explorer_section.py` | Compare the openings with the lichess opening explorer (players of a similar rating) and build its report section |
| `move_ideas.py` | Why one opening move is better than another: board facts plus a Stockfish check, in BG/EN/FR |
| `last_game.py`, `last_game_section.py` | The last game in depth: puzzles from its mistakes, threats, clock, the opponent's mistakes, recurring motifs, the opening against lichess, comparison with recent games |
| `archive_game.py` | Keep each last-game analysis in `game_analysis/` (ignored by git): PGN, Stockfish data, spec and a standalone page |
| `game_index.py` | The games list (`games.html`, newest first) and one page per analysed game, linked to and from the main report |
| `update_skill.py` | Pull a newer version of this skill from its git repository |
| `board_svg.py` | Board, pieces and background scenes |

## License

MIT, see [LICENSE](LICENSE). Stockfish is not part of this repository: `update_stockfish.py` downloads the official release, which is under its own licence (GPLv3).
