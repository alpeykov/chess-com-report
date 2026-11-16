"""Check the skill's own git repository for a newer version and pull it.

  python update_skill.py            fetch, and fast-forward to the remote branch if it is ahead
  python update_skill.py --check    only report

Run it before "analyze the last game" and "regenerate the report", together with update_stockfish.py.
It only fast-forwards (git pull --ff-only): local commits or edits that would conflict are left alone and
reported. Without a network connection, or when the skill folder is not a git clone, it says so and the
analysis goes on with the installed version.
"""
import argparse
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent


def git(*args):
    # git prints UTF-8 (commit subjects may be Cyrillic); the Windows default code page cannot decode it
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only report, do not pull")
    a = ap.parse_args()
    try:
        code, _ = git("rev-parse", "--is-inside-work-tree")
    except FileNotFoundError:
        print("git is not installed; going on with the installed skill.")
        return
    if code:
        print(f"{ROOT} is not a git clone; going on with the installed skill.")
        return
    code, out = git("fetch", "--quiet")
    if code:
        print(f"Could not reach the remote ({out.splitlines()[-1] if out else 'no answer'}); going on with the installed skill.")
        return
    code, out = git("rev-list", "--left-right", "--count", "HEAD...@{u}")
    if code:
        print("The branch has no remote to compare with; going on with the installed skill.")
        return
    ahead, behind = (int(x) for x in out.split())
    _, head = git("log", "-1", "--format=%h %s")
    if not behind:
        print(f"Skill up to date ({head})." + (f" {ahead} local commit(s) not pushed yet." if ahead else ""))
        return
    _, news = git("log", "--format=  %h %s", "HEAD..@{u}")
    print(f"Newer skill version: {behind} new commit(s):\n{news}")
    if a.check:
        print("Run without --check to pull them.")
        return
    code, out = git("pull", "--ff-only", "--quiet")
    if code:
        print(f"Could not fast-forward (local changes or commits?), the installed version is kept:\n{out}")
        return
    _, head = git("log", "-1", "--format=%h %s")
    print(f"Skill updated to {head}.")


if __name__ == "__main__":
    main()
