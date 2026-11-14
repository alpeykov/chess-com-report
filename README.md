# chess-com-report

A Claude skill that builds a personal chess improvement report from a player's public chess.com games: one self-contained HTML file with statistics, a rating chart, opening and tilt analysis, recurring tactical mistakes and step-through boards. Reports can be in English, French or Bulgarian.

## Install

- **Claude Code:** copy this folder to `~/.claude/skills/chess-com-report`.
- **claude.ai:** zip the folder and upload it under Settings → Capabilities → Skills.

Requirements: Python 3.9+ and `pip install chess`. No chess.com login is needed, because the games come from the public API.

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
