"""Time log for "analyze the last game", kept on every run so speed questions need no extra run.

Every analysis step writes one line to <skill>/logs/timings.jsonl:
    {"run": "<game id>", "step": "sf_scan", "seconds": 21.4, "end": <epoch>, ...}
The scripts log their own steps (analyze_last.py, key_moves.py, publish_last.py). The parts done
by hand (reading the data, writing the analysis text, checking the page) are logged with marks:

    python timing.py mark "text written"        # the time since the previous entry of this run
    python timing.py show [--runs 3]            # table per run: scripted steps and the gaps between them

The run id is the game id of the last analysed game (saved by analyze_last.py in logs/current_run).
"""
import argparse, json, os, sys, time

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(SKILL, "logs")
LOG = os.path.join(LOGS, "timings.jsonl")
CURRENT = os.path.join(LOGS, "current_run")


def current_run():
    try:
        return open(CURRENT, encoding="utf-8").read().strip() or "?"
    except OSError:
        return "?"


def start_run(run_id):
    os.makedirs(LOGS, exist_ok=True)
    with open(CURRENT, "w", encoding="utf-8") as f:
        f.write(str(run_id))
    record("start", 0.0, run=str(run_id))


def record(step, seconds, run=None, **extra):
    """Append one timing line; never fails the caller."""
    try:
        os.makedirs(LOGS, exist_ok=True)
        row = {"run": run or current_run(), "step": step, "seconds": round(float(seconds), 1),
               "end": round(time.time(), 1), **extra}
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:  # timing must never break an analysis
        print(f"timing: could not log {step}: {e}", file=sys.stderr)


class timed:
    """with timed("sf_scan"): ...  -> logs the step's wall time."""
    def __init__(self, step, run=None, **extra):
        self.step, self.run, self.extra = step, run, extra

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *exc):
        record(self.step, time.time() - self.t0, run=self.run, failed=bool(exc[0]) or None, **self.extra)
        return False


def load():
    try:
        return [json.loads(l) for l in open(LOG, encoding="utf-8") if l.strip()]
    except OSError:
        return []


def show(runs=3):
    rows = load()
    order = []
    for r in rows:
        if r["run"] not in order:
            order.append(r["run"])
        else:  # keep the latest position
            order.remove(r["run"]); order.append(r["run"])
    for run in order[-runs:]:
        rr = [r for r in rows if r["run"] == run]
        starts = [i for i, r in enumerate(rr) if r["step"] == "start"]
        rr = rr[starts[-1]:] if starts else rr
        t0 = rr[0]["end"] - rr[0]["seconds"]
        print(f"=== run {run}  ({time.strftime('%Y-%m-%d %H:%M', time.localtime(t0))})")
        print(f"{'step':28} {'took':>7} {'gap before':>10} {'at':>7}")
        prev = t0
        script = manual = 0.0
        for r in rr[1:]:
            begin = r["end"] - r["seconds"]
            gap = max(0.0, begin - prev) if r.get("kind") != "mark" else 0.0
            took = r["seconds"]
            if r.get("kind") == "mark":
                manual += took
            elif not r.get("inner"):
                script += took
                manual += gap
            note = " (by hand)" if r.get("kind") == "mark" else ("   inside" if r.get("inner") else "")
            gap_txt = "" if r.get("inner") or r.get("kind") == "mark" else f"{gap:.0f}s"
            print(f"{r['step'][:28]:28} {took:6.0f}s {gap_txt:>10} {r['end'] - t0:6.0f}s{note}")
            if not r.get("inner"):
                prev = max(prev, r["end"])
        print(f"total {prev - t0:.0f}s: scripts {script:.0f}s, by hand / waiting {manual:.0f}s\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mark", help="log the time since this run's previous entry under LABEL")
    m.add_argument("label")
    s = sub.add_parser("show")
    s.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    if a.cmd == "mark":
        run = current_run()
        last = [r for r in load() if r["run"] == run]
        since = time.time() - last[-1]["end"] if last else 0.0
        record(a.label, since, run=run, kind="mark")
        print(f"timing: {a.label} {since:.0f}s")
    else:
        show(a.runs)


if __name__ == "__main__":
    main()
