"""Steps 1-4c of "analyze the last game" in one go, with the slow parts side by side.

    python analyze_last.py USERNAME --dir OUT/data

Runs fetch_games.py --last-only, then at the same time:
  - sf_scan.py (Stockfish evaluations), then side by side:
      last_game.py (moments, threats, clock, opening, comparison) and
      key_moves.py (deeper check of every key move, 2 lines, several engines)
  - mate_check.py (forced mates for both sides; several single-thread engines in parallel)
and prints their output in that order. Writes the same files as running them one by one
(sf_last.json, last_extra.json, key_moves.json, mate_check.json in --dir).

Every step's time goes to <skill>/logs/timings.jsonl (timing.py); `python timing.py show`
prints them, so speed questions never need an extra run.
"""
import argparse, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import timing  # noqa: E402


def py(name, *args):
    return [sys.executable, os.path.join(HERE, name), *args]


def game_id(pgn):
    try:
        m = re.search(r'\[Link "[^"]*?(\d+)"\]', open(pgn, encoding="utf-8").read())
        return m.group(1) if m else "?"
    except OSError:
        return "?"


def start(cmd, env):
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                            text=True, encoding="utf-8", errors="replace"), time.time()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--dir", required=True, help="the report's data folder")
    a = ap.parse_args()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", ANALYZE_LAST="1")
    t0 = time.time()
    pgn = os.path.join(a.dir, "last.pgn")
    r = subprocess.run(py("fetch_games.py", a.username, "--last-only", "--dir", a.dir), env=env)
    if r.returncode:
        sys.exit("fetch_games.py failed")
    timing.start_run(game_id(pgn))             # the run is named after the game
    timing.record("fetch", time.time() - t0, inner=True)

    jobs = max(1, (os.cpu_count() or 4) // 2 - 2)   # leave room for sf_scan / last_game / key_moves
    mates = start(py("mate_check.py", a.username, "--pgn", pgn, "--out", os.path.join(a.dir, "mate_check.json"),
                     "--jobs", str(jobs)), env)
    t = time.time()
    r = subprocess.run(py("sf_scan.py", a.username, "--pgn", pgn, "--dir", a.dir), env=env)
    timing.record("sf_scan", time.time() - t, inner=True)
    if r.returncode:
        mates[0].kill()
        sys.exit("sf_scan.py failed")
    keys = start(py("key_moves.py", "--dir", a.dir, "--jobs", str(jobs)), env)   # logs its own time
    t = time.time()
    r = subprocess.run(py("last_game.py", a.username, "--dir", a.dir), env=env)
    timing.record("last_game", time.time() - t, inner=True)
    if r.returncode:
        mates[0].kill(); keys[0].kill()
        sys.exit("last_game.py failed")
    for name, (proc, t) in (("key_moves", keys), ("mate_check", mates)):
        out, _ = proc.communicate()
        if name == "mate_check":
            timing.record(name, time.time() - t, inner=True)
        print(out, end="")
        if proc.returncode:
            sys.exit(f"{name}.py failed")
    took = time.time() - t0
    timing.record("analyze_last", took)
    print(f"analyze_last: done in {took:.0f}s (times: python timing.py show)")


if __name__ == "__main__":
    main()
