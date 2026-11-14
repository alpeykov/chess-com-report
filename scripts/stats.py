"""Whole-history statistics for one player from OUT/games.pgn.

usage: python stats.py USERNAME --dir OUT

Writes OUT/games.json (one row per game, n = 1-based game number, oldest first) and OUT/summary.json,
and prints a readable summary. All numbers in the report should come from these two files.
"""
import argparse
import collections
import io
import json
import pathlib
import sys
import chess
import chess.pgn
from engine import search, material_for, MATE


def time_class(tc):
    if not tc or tc == "-":
        return "other"
    if "/" in tc:
        return "daily"
    base, _, inc = tc.partition("+")
    est = int(base) + 40 * int(inc or 0)
    return "bullet" if est < 180 else "blitz" if est < 600 else "rapid"


def pct(rs):
    if not rs:
        return None
    return round(100 * (sum(r["outcome"] == "win" for r in rs) + 0.5 * sum(r["outcome"] == "draw" for r in rs)) / len(rs))


def rec(rs):
    return {"n": len(rs), "w": sum(r["outcome"] == "win" for r in rs), "l": sum(r["outcome"] == "loss" for r in rs),
            "d": sum(r["outcome"] == "draw" for r in rs), "score_pct": pct(rs)}


def rows_from(pgn_text, me):
    rows, f = [], io.StringIO(pgn_text)
    while (g := chess.pgn.read_game(f)) is not None:
        h = g.headers
        if me not in (h.get("White", "").lower(), h.get("Black", "").lower()):
            continue
        white = h["White"].lower() == me
        color = chess.WHITE if white else chess.BLACK
        res = h["Result"]
        outcome = "draw" if res == "1/2-1/2" else ("win" if (res == "1-0") == white else "loss")
        moves = list(g.mainline_moves())
        b, sans, qlost, early_check = chess.Board(), [], None, None
        for i, m in enumerate(moves):
            san = b.san(m)
            if b.turn == color and early_check is None and b.fullmove_number <= 4 and \
                    b.piece_type_at(m.from_square) == chess.BISHOP and san.endswith("+"):
                early_check = san
            sans.append(san)
            b.push(m)
            if qlost is None and not b.pieces(chess.QUEEN, color) and b.pieces(chess.QUEEN, not color):
                nb, traded = b.copy(), False
                for m2 in moves[i + 1:i + 3]:
                    nb.push(m2)
                    traded |= not nb.pieces(chess.QUEEN, not color)
                if not traded:
                    qlost = {"move_no": i // 2 + 1, "ply": i + 1}
        term = h.get("Termination", "").lower()
        how = ("checkmate" if "checkmate" in term else "time" if "on time" in term else
               "abandoned" if "abandon" in term else "resignation" if "resignation" in term else
               "draw" if outcome == "draw" else "other")
        resign_eval = None
        if outcome == "loss" and how == "resignation" and not b.is_game_over():
            s = search(b, 2)
            resign_eval = s if b.turn == color else -s
        eco_url = h.get("ECOUrl", "")
        rows.append(dict(
            date=h.get("UTCDate", h.get("Date", "")), end_time=h.get("EndTime", ""), color="white" if white else "black",
            outcome=outcome, how=how, opp=h["Black"] if white else h["White"],
            my_elo=int(h.get("WhiteElo" if white else "BlackElo", 0) or 0),
            opp_elo=int(h.get("BlackElo" if white else "WhiteElo", 0) or 0),
            tc=h.get("TimeControl", ""), time_class=time_class(h.get("TimeControl", "")), plies=len(moves),
            first=sans[:10], eco=h.get("ECO", ""), opening=eco_url.rsplit("/", 1)[-1].replace("-", " ") if eco_url else "",
            early_bishop_check=early_check, qlost=qlost, mat_end=material_for(b, color), resign_eval=resign_eval,
            link=h.get("Link", "")))
    rows.sort(key=lambda r: (r["date"], r["end_time"]))
    for n, r in enumerate(rows, 1):
        r["n"] = n
    return rows


def tilt(rows):
    out = {}
    for label, k in [("after_win", "W"), ("after_1_loss", 1), ("after_2_losses", 2), ("after_3_losses", 3)]:
        sel = []
        for i, r in enumerate(rows):
            prev = [p for p in rows[max(0, i - 3):i] if p["date"] == r["date"]]
            prev = prev[::-1]
            if k == "W":
                ok = prev[:1] and prev[0]["outcome"] == "win"
            else:
                ok = len(prev) >= k and all(p["outcome"] == "loss" for p in prev[:k])
            if ok:
                sel.append(r)
        out[label] = rec(sel)
    by_day_index = collections.defaultdict(list)
    seen = collections.Counter()
    for r in rows:
        seen[r["date"]] += 1
        idx = seen[r["date"]]
        by_day_index["games_1_5" if idx <= 5 else "games_6_20" if idx <= 20 else "games_21_plus"].append(r)
    out["by_game_of_day"] = {k: rec(v) for k, v in by_day_index.items()}
    out["max_games_in_a_day"] = max(seen.values())
    return out


def openings(rows):
    W = [r for r in rows if r["color"] == "white"]
    B = [r for r in rows if r["color"] == "black"]
    res = {"white_first_move": {}, "black_vs": {}, "named_white": {}, "named_black": {}}
    for k, v in collections.Counter(r["first"][0] for r in W if r["first"]).most_common(5):
        res["white_first_move"][k] = rec([r for r in W if r["first"][:1] == [k]])
    for opp_first in ["e4", "d4"]:
        sel = [r for r in B if r["first"][:1] == [opp_first]]
        res["black_vs"][opp_first] = {k: rec([r for r in sel if r["first"][1:2] == [k]])
                                      for k, _ in collections.Counter(r["first"][1] for r in sel if len(r["first"]) > 1).most_common(5)}
    other = [r for r in B if r["first"][:1] not in (["e4"], ["d4"])]
    res["black_vs"]["other"] = rec(other)
    for side, sel in [("named_white", W), ("named_black", B)]:
        c = collections.Counter(r["opening"] for r in sel if r["opening"])
        res[side] = {k: rec([r for r in sel if r["opening"] == k]) for k, v in c.most_common(12) if v >= 3}
    eb = [r for r in rows if r["early_bishop_check"]]
    res["early_bishop_check"] = {"with": rec(eb), "without": rec([r for r in rows if not r["early_bishop_check"]]),
                                 "examples": collections.Counter(r["early_bishop_check"] for r in eb).most_common(3)}
    return res


def summary(rows):
    L = [r for r in rows if r["outcome"] == "loss"]
    Wn = [r for r in rows if r["outcome"] == "win"]
    tcs = collections.Counter(r["time_class"] for r in rows)
    main_tc = tcs.most_common(1)[0][0]
    rated = [r for r in rows if r["time_class"] == main_tc and r["my_elo"]]
    peak = max(rated, key=lambda r: r["my_elo"]) if rated else None
    low = min(rated, key=lambda r: r["my_elo"]) if rated else None
    return {
        "games": len(rows), "first_date": rows[0]["date"], "last_date": rows[-1]["date"],
        "overall": rec(rows), "white": rec([r for r in rows if r["color"] == "white"]),
        "black": rec([r for r in rows if r["color"] == "black"]),
        "time_classes": dict(tcs), "main_time_class": main_tc,
        "rating": {"first": rated[0]["my_elo"], "now": rated[-1]["my_elo"], "peak": peak["my_elo"], "peak_date": peak["date"],
                   "low": low["my_elo"], "low_date": low["date"]} if rated else None,
        "last_50": rec(rows[-50:]), "last_50_rating": [rows[-50:][0]["my_elo"], rows[-1]["my_elo"]],
        "losses_by": dict(collections.Counter(r["how"] for r in L)),
        "wins_by": dict(collections.Counter(r["how"] for r in Wn)),
        "queen_lost_in_losses": sum(bool(r["qlost"]) for r in L),
        "queen_lost_games": [r["n"] for r in L if r["qlost"]],
        "mated_games": [r["n"] for r in L if r["how"] == "checkmate"],
        "losses_within_15_moves": [r["n"] for r in L if r["plies"] <= 30],
        "resigned_at_minus3_or_better": [r["n"] for r in L if r["resign_eval"] is not None and r["resign_eval"] >= -3],
        "tilt": tilt(rows), "openings": openings(rows),
        "by_quarter": [dict(range=[c[0]["n"], c[-1]["n"]], dates=[c[0]["date"], c[-1]["date"]], **rec(c),
                            rating=[c[0]["my_elo"], c[-1]["my_elo"]])
                       for c in (rows[len(rows) * k // 4:len(rows) * (k + 1) // 4] for k in range(4)) if c],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--time-class", default="main",
                    help="main (default: only the most played time class), all, or bullet/blitz/rapid/daily")
    a = ap.parse_args()
    out = pathlib.Path(a.dir)
    rows = rows_from((out / "games.pgn").read_text(encoding="utf-8"), a.username.strip().lower())
    if not rows:
        raise SystemExit("No games of this user in games.pgn")
    if a.time_class != "all":
        tc = collections.Counter(r["time_class"] for r in rows).most_common(1)[0][0] if a.time_class == "main" else a.time_class
        dropped = collections.Counter(r["time_class"] for r in rows if r["time_class"] != tc)
        rows = [r for r in rows if r["time_class"] == tc]
        for n, r in enumerate(rows, 1):
            r["n"] = n
        if dropped:
            print(f"Only {tc} games are counted; left out: {dict(dropped)} (use --time-class all to keep them)",
                  file=sys.stderr)
        if not rows:
            raise SystemExit(f"No {tc} games found")
    s = summary(rows)
    (out / "games.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
