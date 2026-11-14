"""Check for a newer official Stockfish release and install it in place of the current one.

  python update_stockfish.py            check, and install the new version if there is one
  python update_stockfish.py --check    only report the installed and latest versions

Run it before "analyze the last game" and "regenerate the report". It only touches a copy it can manage:
the folder layout of the official archive (<root>/stockfish/stockfish-<build>.exe), by default
C:/projects/stockfish on Windows and ~/stockfish on Linux. A Stockfish installed by apt or brew is
reported but left alone (update it with the package manager). Without a network connection it says so
and the analysis goes on with the installed version.

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


def pick_asset(assets, exe):
    """Same build as the installed one (e.g. ...-x86-64-universal), else a safe default for this system."""
    names = {a["name"]: a["browser_download_url"] for a in assets}
    if exe:
        stem = pathlib.Path(exe).stem  # stockfish-windows-x86-64-universal
        for n in names:
            if n.split(".")[0] == stem:
                return n, names[n]
    sysname = platform.system()
    want = {"Windows": "stockfish-windows-x86-64-universal.zip", "Linux": "stockfish-ubuntu-x86-64-avx2.tar"}.get(sysname)
    if want in names:
        return want, names[want]
    return None, None


def managed_root(exe):
    """<root> if exe sits in <root>/stockfish/, the layout of the official archive; else None."""
    p = pathlib.Path(exe).resolve()
    if p.parent.name.lower() == "stockfish" and not str(p).startswith(("/usr/", "/opt/homebrew")):
        return p.parent.parent
    return None


def install(url, name, root):
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        arc = pathlib.Path(tmp) / name
        print(f"Downloading {url}")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=120) as r, open(arc, "wb") as f:
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
        old = root / "stockfish"
        if old.exists():
            shutil.rmtree(old)
        shutil.move(str(new_dir), str(old))
        keep = root / name
        shutil.copy2(arc, keep)  # keep the archive next to the folder, as a manual install would
        for p in root.glob("stockfish-*.zip"):
            if p.name != name:
                p.unlink()
        return str(old / exes[0].name), v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only report, do not install")
    ap.add_argument("--stockfish", help="path to the installed Stockfish (default: the one the skill finds)")
    ap.add_argument("--root", help="where to install when none is found (default C:/projects/stockfish or ~/stockfish)")
    a = ap.parse_args()

    exe = sf_engine.find_stockfish(a.stockfish)
    have = version_of(exe) if exe else None
    print(f"Installed: {('Stockfish ' + have) if have else 'none'}{(' (' + exe + ')') if exe else ''}")
    try:
        new, assets = latest()
    except Exception as e:
        print(f"Could not reach GitHub ({e.__class__.__name__}); going on with the installed version.")
        return
    print(f"Latest release: Stockfish {new}")
    if have and as_tuple(have) >= as_tuple(new):
        print("Up to date.")
        return
    if exe and not have:
        print("The installed build reports no release number (a development build?); left as it is.")
        return
    if a.check:
        print("A newer version is available; run without --check to install it.")
        return
    root = managed_root(exe) if exe else pathlib.Path(a.root or ("C:/projects/stockfish" if os.name == "nt" else os.path.expanduser("~/stockfish")))
    if root is None:
        print(f"{exe} was not installed from the release archive (package manager?). Update it there, "
              "e.g. 'sudo apt upgrade stockfish' or 'brew upgrade stockfish'.")
        return
    name, url = pick_asset(assets, exe)
    if not url:
        print("No matching build for this system in the release; download it by hand from "
              "https://github.com/official-stockfish/Stockfish/releases/latest")
        return
    path, v = install(url, name, pathlib.Path(root))
    print(f"Installed Stockfish {v}: {path}")
    print("Earlier games keep their cached analysis; 'sf_scan.py ... --full' redoes them with the new version.")


if __name__ == "__main__":
    main()
