"""Score every case against ground truth. Writes results/summary.json and prints it."""
from __future__ import annotations

import json
from pathlib import Path

R = Path(__file__).parent / "results"


def load(n):
    return json.loads((R / f"{n}.json").read_text())


def bands(rows, conf_key, hit_key, cuts=(0.9, 0.6)):
    """Accuracy inside confidence bands: the whole point of calibration."""
    out = []
    lo_prev = 1.01
    for lo in (*cuts, 0.0):
        b = [r for r in rows if lo <= r[conf_key] < lo_prev]
        out.append({"band": f"{lo:.1f}–{min(lo_prev, 1):.1f}" if lo else f"<{lo_prev:.1f}",
                    "n": len(b), "acc": round(sum(r[hit_key] for r in b) / len(b), 3) if b else None})
        lo_prev = lo
    return out


def router():
    d = load("issue_router")
    rows = d["rows"]
    misses = sorted([r for r in rows if not r["hit"]], key=lambda r: -r["confidence"])
    hi = [r for r in rows if r["confidence"] >= 0.9]
    return {
        "n": len(rows), "acc": round(sum(r["hit"] for r in rows) / len(rows), 3),
        "bands": bands(rows, "confidence", "hit"),
        "auto_at_0.9": {"share": round(len(hi) / len(rows), 3), "acc": round(sum(r["hit"] for r in hi) / len(hi), 3)},
        "confident_misses": [{k: r[k] for k in ("number", "title", "truth", "pick", "confidence")} for r in misses[:6]],
        "usage": d["usage"],
    }


def prio():
    d = load("priority")
    rows = d["rows"]
    for r in rows:
        r["level"] = round(r["score"])
        r["exact"] = r["level"] == r["truth"]
        r["within1"] = abs(r["score"] - r["truth"]) <= 0.75
    by_truth = {}
    for t in range(4):
        b = [r["score"] for r in rows if r["truth"] == t]
        by_truth[["P3", "P2", "P1", "P0"][t]] = {"n": len(b), "mean_score": round(sum(b) / len(b), 2) if b else None}
    # the useful question: does P1/P0 rise to the top?
    ranked = sorted(rows, key=lambda r: -r["score"])
    top = ranked[: max(1, len(rows) // 10)]
    high = [r for r in rows if r["truth"] >= 2]
    return {
        "n": len(rows), "exact": round(sum(r["exact"] for r in rows) / len(rows), 3),
        "mean_score_by_label": by_truth,
        "top10pct": {"n": len(top), "p1_or_p0": sum(r["truth"] >= 2 for r in top), "total_p1_p0": len(high)},
        "top": [{k: r[k] for k in ("number", "title", "truth", "score")} for r in ranked[:6]],
        "high_rows": [{k: r[k] for k in ("number", "title", "truth", "score")} for r in high],
        "usage": d["usage"],
    }


def dups():
    d = load("duplicates")
    rows = d["rows"]
    pairs = {}
    for r in rows:  # each pair is asked from both sides; keep both scores
        pairs.setdefault(frozenset((r["a"], r["b"])), []).append(r)
    agg = []
    for k, rs in pairs.items():
        agg.append({"pair": sorted(k), "titles": [rs[0]["a_title"], rs[0]["b_title"]],
                    "noul": round(max(x["noul"] for x in rs), 3), "both": [round(x["noul"], 3) for x in rs],
                    "dup": rs[0]["dup"], "near_miss": rs[0]["near_miss"]})
    agg.sort(key=lambda x: -x["noul"])
    true = [a for a in agg if a["dup"]]
    neg = [a for a in agg if not a["dup"]]
    return {
        "pairs_scored": len(agg), "calls": d["usage"]["calls"], "questions_per_call": d["questions_per_call"],
        "true_pairs": true,
        "near_miss": [a for a in agg if a["near_miss"]],
        "top_non_dups": neg[:5],
        "max_non_dup": neg[0]["noul"] if neg else None,
        "min_true": min(a["noul"] for a in true),
        "rank_of_true": [agg.index(a) + 1 for a in true],
        "usage": d["usage"],
    }


def gate():
    d = load("gate")
    rows = d["rows"]
    out = {}
    for arm in d["arms"]:
        tp = fp = fn = tn = unsure = 0
        fps, fns = [], []
        for r in rows:
            p, t = r["nouls"][arm], r["truth"][arm]
            if 0.35 <= p < 0.8:
                unsure += 1
                continue
            yes = p >= 0.8
            if yes and t:
                tp += 1
            elif yes:
                fp += 1
                fps.append({"number": r["number"], "title": r["title"], "p": p})
            elif t:
                fn += 1
                fns.append({"number": r["number"], "title": r["title"], "p": p})
            else:
                tn += 1
        out[arm] = {"positives": sum(r["truth"][arm] for r in rows), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                    "unsure": unsure, "fp_examples": fps[:4], "fn_examples": fns[:4]}
    return {"n": len(rows), "arms": out, "usage": d["usage"]}


def simple(name):
    return load(name)


if __name__ == "__main__":
    s = {"issue_router": router(), "priority": prio(), "duplicates": dups(), "gate": gate(),
         "approvals": simple("approvals"), "verdicts": simple("verdicts"), "comments": simple("comments")}
    (R / "summary.json").write_text(json.dumps(s, indent=1, default=list))
    for k in ("issue_router", "priority", "duplicates", "gate"):
        print(f"\n===== {k}")
        print(json.dumps(s[k], indent=1, default=list)[:3500])
