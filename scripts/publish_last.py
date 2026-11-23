"""After the analysis text is written: splice it in, rebuild, archive and write the game pages – one command.

    python publish_last.py USERNAME --report OUT --block GA_BLOCK.py --pages PAGES_DIR

  OUT        the report folder (has data/, scripts/make_spec.py, report.html)
  GA_BLOCK   a Python file that starts with `game_analysis = {` (the hand-written analysis)
  PAGES_DIR  the folder published as the Artifact (gets index.html, skill_report.html, games.html, game-<id>.html)

Steps (each timed into logs/timings.jsonl):
  1. replace `game_analysis = {...}` in OUT/scripts/make_spec.py (up to the "# deeper look at the last game"
     line) with the block, and check that the file now holds it (absolute paths, no shell guessing),
  2. make_spec.py, 3. build_report.py -> OUT/report.html, copied to PAGES_DIR/index.html and skill_report.html,
  4. archive_game.py, after checking that data/last.pgn is the game the run was started for,
  5. game_index.py for PAGES_DIR (home index.html) and for OUT (home report.html).
Prints the game page paths to publish and open.
"""
import argparse, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import timing  # noqa: E402

END = "\n# deeper look at the last game"


def splice(spec_py, block_file):
    src = open(spec_py, encoding="utf-8").read()
    block = open(block_file, encoding="utf-8").read().strip() + "\n"
    if not block.startswith("game_analysis = {"):
        sys.exit(f"{block_file} must start with 'game_analysis = {{'")
    i, j = src.find("\ngame_analysis = {"), src.find(END)
    if i < 0 or j < 0 or j < i:
        sys.exit(f"cannot find the game_analysis block in {spec_py}")
    new = src[:i + 1] + block + src[j:]
    with open(spec_py, "w", encoding="utf-8") as f:
        f.write(new)
    assert block in open(spec_py, encoding="utf-8").read(), "splice did not land"


def run(step, cmd, cwd, env):
    t = time.time()
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    timing.record(step, time.time() - t)
    if r.returncode:
        print(r.stdout, r.stderr)
        sys.exit(f"{step} failed")
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--report", required=True)
    ap.add_argument("--block", required=True)
    ap.add_argument("--pages", required=True)
    a = ap.parse_args()
    out, pages = os.path.abspath(a.report), os.path.abspath(a.pages)
    data = os.path.join(out, "data")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    py = sys.executable
    t0 = time.time()

    pgn = open(os.path.join(data, "last.pgn"), encoding="utf-8").read()
    gid = (re.search(r'\[Link "[^"]*?(\d+)"\]', pgn) or [None, "?"])[1]
    if timing.current_run() not in ("?", gid):
        sys.exit(f"data/last.pgn is game {gid}, but the analysis was started for {timing.current_run()}: "
                 "run analyze_last.py again before publishing")

    t = time.time()
    splice(os.path.join(out, "scripts", "make_spec.py"), a.block)
    timing.record("splice", time.time() - t)
    run("make_spec", [py, os.path.join(out, "scripts", "make_spec.py")], out, env)
    print(run("build_report", [py, os.path.join(HERE, "build_report.py"), "--dir", "data", "--out", "report.html"], out, env)
          .strip().splitlines()[-1][:80])
    os.makedirs(pages, exist_ok=True)
    for name in ("index.html", "skill_report.html"):
        shutil.copyfile(os.path.join(out, "report.html"), os.path.join(pages, name))
    run("archive_game", [py, os.path.join(HERE, "archive_game.py"), "--dir", "data"], out, env)
    run("game_index_pages", [py, os.path.join(HERE, "game_index.py"), a.username, "--out", pages, "--home", "index.html"], out, env)
    run("game_index_local", [py, os.path.join(HERE, "game_index.py"), a.username, "--out", ".", "--home", "report.html"], out, env)
    took = time.time() - t0
    timing.record("publish_last", took, inner=True)
    page = f"game-{gid}.html"
    for d in (pages, out):
        if not os.path.exists(os.path.join(d, page)):
            sys.exit(f"{page} was not written in {d}")
    print(f"publish_last: done in {took:.0f}s")
    print(f"publish: root={pages} file_path={os.path.join(pages, 'index.html')} files=[{page}, games.html]")
    print(f"open:    {os.path.join(out, page)}")


if __name__ == "__main__":
    main()
