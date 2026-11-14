"""Keep a list of the reports made so far, so the next report can compare the periods between them.

  python history.py --dir OUT                 show OUT/history.json
  python history.py --dir OUT --add           add the current state (last game number and date from OUT/summary.json)
  python history.py --dir OUT --add-at N DATE add a past report by hand (game number N in games.json, date YYYY.MM.DD)

Run --add after each full report or "regenerate the report" (not after "analyze the last game").
A second --add on the same day replaces that day's checkpoint.
The report's progress section compares: before the 1st report, between reports, since the last one, last 50 games.
"""
import argparse
import json
import pathlib


def load(out):
    p = pathlib.Path(out) / "history.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"reports": []}


def save(out, h):
    h["reports"] = sorted({r["games"]: r for r in h["reports"]}.values(), key=lambda r: r["games"])
    (pathlib.Path(out) / "history.json").write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")


def periods(h, n_games):
    """[(first, last, label_index)] game-number ranges: before the 1st report, between reports, since the last one."""
    cuts = [r["games"] for r in h["reports"] if r["games"] < n_games]
    out, start = [], 1
    for c in cuts:
        out.append((start, c))
        start = c + 1
    if start <= n_games:
        out.append((start, n_games))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--add", action="store_true")
    ap.add_argument("--add-at", nargs=2, metavar=("N", "DATE"))
    a = ap.parse_args()
    h = load(a.dir)
    if a.add:
        s = json.loads((pathlib.Path(a.dir) / "summary.json").read_text(encoding="utf-8"))
        # a second regeneration on the same day moves that day's checkpoint instead of adding a tiny period
        h["reports"] = [r for r in h["reports"] if r["date"] != s["last_date"]]
        h["reports"].append({"games": s["games"], "date": s["last_date"]})
    if a.add_at:
        h["reports"].append({"games": int(a.add_at[0]), "date": a.add_at[1]})
    if a.add or a.add_at:
        save(a.dir, h)
    print(json.dumps(h, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
