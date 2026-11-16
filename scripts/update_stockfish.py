"""Install Stockfish in the skill's own folder and keep it on the latest official release.

  python update_stockfish.py            install it if missing, update it if there is a newer release
  python update_stockfish.py --check    only report the installed and latest versions

Run it before "analyze the last game" and "regenerate the report" (sf_scan.py also runs it by itself when
no Stockfish is found). The skill keeps its own copy in <skill>/stockfish/ (ignored by git), so a fresh
clone needs no manual setup: the first run downloads it. Other installs (STOCKFISH_PATH, apt, brew,
C:/projects/stockfish) are never touched; they are only used when the skill's copy cannot be installed,
for example without a network connection.

The download comes only from the official GitHub releases (github.com/official-stockfish/Stockfish).
The new build is unpacked next to the old one, started once to check that it answers "uci", and only
then replaces the old folder. Cached analyses (OUT/sf/) are kept; run sf_scan.py --full to redo them.
"""
import argparse
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sf_engine  # noqa: E402

API = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"
UA = {"User-Agent": "chess-report-skill", "Accept": "application/vnd.github+json"}
ROOT = pathlib.Path(sf_engine.SKILL_ROOT)  # the program goes to ROOT/stockfish/


def version_of(exe):
    """'19' from 'Stockfish 19 by ...', or None for a dev build / no answer."""
    try:
        out = subprocess.run([exe], input="uci\nquit\n", capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return None
    m = re.search(r"id name Stockfish (\S+)", out) or re.search(r"Stockfish (\S+) by", out)
    return m.group(1) if m else None


def as_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def latest():
    with urllib.request.urlopen(urllib.request.Request(API, headers=UA), timeout=20) as r:
        rel = json.load(r)
    return rel["tag_name"].replace("sf_", ""), rel["assets"]


def pick_asset(assets, like=None):
    """The same build as `like` (e.g. ...-x86-64-universal) if given, else a safe default for this system."""
    names = {a["name"]: a["browser_download_url"] for a in assets}
    if like:
        stem = pathlib.Path(like).stem.lower()  # stockfish-windows-x86-64-universal
        for n in names:
            if n.split(".")[0].lower() == stem:
                return n, names[n]
    sysname, mach = platform.system(), platform.machine().lower()
    want = {"Windows": "stockfish-windows-x86-64-universal.zip",
            "Linux": "stockfish-ubuntu-x86-64-avx2.tar",
            "Darwin": "stockfish-macos-m1-apple-silicon.tar" if mach in ("arm64", "aarch64") else "stockfish-macos-x86-64-avx2.tar"}.get(sysname)
    if want in names:
        return want, names[want]
    return None, None


def install(url, name, root=ROOT):
    """Download the release archive and put its program folder at root/stockfish/. Returns (path, version)."""
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sf-download-", dir=root) as tmp:
        arc = pathlib.Path(tmp) / name
        print(f"Downloading {url}")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=300) as r, open(arc, "wb") as f:
            shutil.copyfileobj(r, f)
        out = pathlib.Path(tmp) / "x"
        out.mkdir()
        if name.endswith(".zip"):
            with zipfile.ZipFile(arc) as z:
                for m in z.namelist():  # refuse paths that leave the folder
                    if m.startswith("/") or ".." in pathlib.PurePosixPath(m).parts:
                        raise SystemExit(f"Unsafe path in archive: {m}")
                z.extractall(out)
        else:
            with tarfile.open(arc) as t:
                for m in t.getmembers():
                    if m.name.startswith("/") or ".." in pathlib.PurePosixPath(m.name).parts or m.issym() or m.islnk():
                        raise SystemExit(f"Unsafe entry in archive: {m.name}")
                t.extractall(out)
        new_dir = out / "stockfish"
        exes = sorted(p for p in new_dir.glob("stockfish*") if p.is_file() and p.suffix in ("", ".exe"))
        if not exes:
            raise SystemExit("No Stockfish program found in the archive; the installed version is kept.")
        if os.name != "nt":
            exes[0].chmod(0o755)
        v = version_of(str(exes[0]))
        if not v:
            raise SystemExit("The new build did not answer 'uci' (CPU not supported?); the installed version is kept.")
        dest = root / "stockfish"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(new_dir), str(dest))
        return str(dest / exes[0].name), v


def ensure(check=False, quiet=False):
    """Install or update the skill's copy. Returns the Stockfish path to use (the skill's copy, else any other found)."""
    say = (lambda *a: None) if quiet else print
    own = sf_engine.skill_stockfish()
    have = version_of(own) if own else None
    other = None if own else sf_engine.find_stockfish()
    say(f"Skill's Stockfish: {('Stockfish ' + have + ' (' + own + ')') if own else 'not installed yet (' + sf_engine.SKILL_SF + ')'}")
    try:
        new, assets = latest()
    except Exception as e:
        say(f"Could not reach GitHub ({e.__class__.__name__}); going on with "
            f"{own or other or 'the material engine (no Stockfish found)'}.")
        return own or other
    say(f"Latest release: Stockfish {new}")
    if own and not have:
        say("The skill's copy reports no release number (a development build?); left as it is.")
        return own
    if have and as_tuple(have) >= as_tuple(new):
        say("Up to date.")
        return own
    if check:
        say("Run without --check to " + ("update it." if own else "install it."))
        return own or other
    name, url = pick_asset(assets, own or other)
    if not url:
        say("No matching build for this system in the release; download it by hand from "
            "https://github.com/official-stockfish/Stockfish/releases/latest and set STOCKFISH_PATH.")
        return own or other
    try:
        path, v = install(url, name)
    except (OSError, SystemExit) as e:
        say(f"Install failed ({e}); going on with {own or other or 'the material engine'}.")
        return own or other
    say(f"{'Updated to' if own else 'Installed'} Stockfish {v}: {path}")
    if own:
        say("Earlier games keep their cached analysis; 'sf_scan.py ... --full' redoes them with the new version.")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only report, do not install")
    ensure(check=ap.parse_args().check)


if __name__ == "__main__":
    main()
