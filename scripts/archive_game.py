"""Keep every "analyze the last game" result: copy it into the skill's game_analysis/ folder (ignored by git).

    python archive_game.py --dir OUT [--spec OUT/report_spec.json]

Creates game_analysis/<date>_<white>-<black>_<game id>/ with
  game.pgn            the game (OUT/last.pgn)
  sf_last.json        Stockfish evaluations (when present)
  last_extra.json     puzzles, threats, clock, opponent's mistakes, opening, comparison (when present)
  analysis_spec.json  the spec's game_analysis and the viewers it uses
  analysis.html       that analysis alone as a page (board, table, puzzles; BG/EN/FR like the report)
Run it after the report is rebuilt; running it again for the same game overwrites that folder.
"""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys

import chess.pgn

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "game_analysis"


def slug(s):
    return re.sub(r"[^\w.-]+", "_", s).strip("_")


def folder_for(pgn_path):
    h = chess.pgn.read_game(open(pgn_path, encoding="utf-8")).headers
    gid = h.get("Link", "").rstrip("/").rsplit("/", 1)[-1] or "game"
    date = h.get("UTCDate", h.get("Date", "")).replace(".", "-")
    return ARCHIVE / slug(f"{date}_{h.get('White', '?')}-{h.get('Black', '?')}_{gid}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="the report's data folder (with last.pgn and report_spec.json)")
    ap.add_argument("--spec")
    a = ap.parse_args()
    out = pathlib.Path(a.dir)
    spec = json.loads(pathlib.Path(a.spec or out / "report_spec.json").read_text(encoding="utf-8"))
    ga = spec.get("game_analysis")
    if not ga:
        sys.exit("the spec has no game_analysis")
    dest = folder_for(out / "last.pgn")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out / "last.pgn", dest / "game.pgn")
    shutil.copyfile(out / "last.pgn", dest / "last.pgn")  # the builder reads the last game from last.pgn
    for name in ("sf_last.json", "last_extra.json"):
        if (out / name).exists():
            shutil.copyfile(out / name, dest / name)
    text = json.dumps(ga, ensure_ascii=False)
    used = set(re.findall(r"\{\{V:([\w-]+)\}\}", text))
    mini = {k: spec[k] for k in ("langs", "lang", "piece_words", "labels") if k in spec}
    mini.update({"title": ga.get("title", "Game analysis"), "subtitle": "", "tiles": [], "sections": [], "game_analysis": ga,
                 "viewers": {k: v for k, v in spec.get("viewers", {}).items() if k in used}})
    (dest / "analysis_spec.json").write_text(json.dumps(mini, ensure_ascii=False, indent=1), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_report.py"), "--dir", str(dest), "--spec", str(dest / "analysis_spec.json"),
                        "--out", str(dest / "analysis.html")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    (dest / "last.pgn").unlink(missing_ok=True)
    if r.returncode:
        print(r.stdout + r.stderr)
        sys.exit("analysis.html was not built")
    print(f"archived: {dest}")


if __name__ == "__main__":
    main()
