"""Steps 1-3 of "analyze the last game" in one go, with the slow parts side by side.

    python analyze_last.py USERNAME --dir OUT/data

Runs fetch_games.py --last-only, then at the same time:
  - sf_scan.py (Stockfish evaluations) followed by last_game.py (moments, threats, clock, opening, comparison)
  - mate_check.py (forced mates for both sides; several single-thread engines in parallel)
and prints their output in that order. Writes the same files as running them one by one
(sf_last.json, last_extra.json, mate_check.json in --dir).
"""
import argparse, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def py(name, *args):
    return [sys.executable, os.path.join(HERE, name), *args]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--dir", required=True, help="the report's data folder")
    a = ap.parse_args()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    t0 = time.time()
    r = subprocess.run(py("fetch_games.py", a.username, "--last-only", "--dir", a.dir), env=env)
    if r.returncode:
        sys.exit("fetch_games.py failed")
    pgn = os.path.join(a.dir, "last.pgn")
    jobs = max(1, (os.cpu_count() or 4) // 2 - 2)   # leave room for sf_scan / last_game
    mates = subprocess.Popen(py("mate_check.py", a.username, "--pgn", pgn, "--out", os.path.join(a.dir, "mate_check.json"),
                                "--jobs", str(jobs)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                             text=True, encoding="utf-8", errors="replace")
    for step in (py("sf_scan.py", a.username, "--pgn", pgn, "--dir", a.dir), py("last_game.py", a.username, "--dir", a.dir)):
        r = subprocess.run(step, env=env)
        if r.returncode:
            mates.kill()
            sys.exit(f"{os.path.basename(step[1])} failed")
    out, _ = mates.communicate()
    print(out, end="")
    if mates.returncode:
        sys.exit("mate_check.py failed")
    print(f"analyze_last: done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
