"""Render ../cases.html from results/*.json. Every number on the page comes from here."""
from __future__ import annotations

import html
import json
import random
from pathlib import Path
from string import Template

HERE = Path(__file__).parent
R = HERE / "results"
GH = "https://github.com/NousResearch/hermes-agent"
YES, NO = 0.8, 0.35


def load(n):
    return json.loads((R / f"{n}.json").read_text())


def e(s):
    return html.escape(str(s))


def pr(n):
    return f'<a href="{GH}/pull/{n}">#{n}</a>'


def iss(n):
    return f'<a href="{GH}/issues/{n}">#{n}</a>'


def pct(x):
    return f"{x * 100:.0f}%"


def band(p):
    return ("take", "take") if p >= YES else ("unsure", "unsure") if p >= NO else ("skip", "skip")


def chip(p):
    cls, label = band(p)
    return f'<span class="chip {cls}">{p:.2f} · {label}</span>'


# ── totals ──────────────────────────────────────────────────────────────────
files = [f for f in R.glob("*.json") if f.stem != "summary"]
CALLS = sum(load(f.stem)["usage"]["calls"] for f in files)
COST = sum(load(f.stem)["usage"]["cost_usd"] for f in files)
MS = sorted(load(f.stem)["usage"]["ms_median"] for f in files)[len(files) // 2]

# ── 1 verdicts ──────────────────────────────────────────────────────────────
v = load("verdicts")["rows"]
v_sub_wrong = sum(r["substring"] != r["truth"] for r in v)
v_jev_wrong = sum((r["noul"] >= 0.5) != r["truth"] for r in v)
v_rows = "".join(
    f'<tr><td>{e(r["summary"])}</td><td>{"✓" if r["truth"] else "✗"}</td>'
    f'<td class="{"bad" if r["substring"] != r["truth"] else ""}">{"PASS" if r["substring"] else "FAIL"}</td>'
    f'<td>{chip(r["noul"])}</td></tr>'
    for r in v
)

# ── 2 duplicates ────────────────────────────────────────────────────────────
dd = load("duplicates")
pairs = {}
for r in dd["rows"]:
    k = frozenset((r["a"], r["b"]))
    pairs.setdefault(k, {"titles": (r["a_title"], r["b_title"]), "dup": r["dup"], "near": r["near_miss"], "p": []})
    pairs[k]["p"].append(r["noul"])
agg = sorted(({"pair": sorted(k), **x, "noul": max(x["p"])} for k, x in pairs.items()), key=lambda x: -x["noul"])
true = [a for a in agg if a["dup"]]
neg = [a for a in agg if not a["dup"]]
near = next(a for a in agg if a["near"])
random.seed(3)
W, H = 640, 92
dots = "".join(
    f'<circle cx="{16 + a["noul"] * (W - 32):.1f}" cy="{30 + random.uniform(-14, 14):.1f}" r="2.6" class="neg"/>'
    for a in neg if not a["near"]
)
dots += f'<circle cx="{16 + near["noul"] * (W - 32):.1f}" cy="30" r="4.5" class="near"/>'
dots += "".join(f'<circle cx="{16 + a["noul"] * (W - 32):.1f}" cy="30" r="5" class="pos"/>' for a in true)
axis = "".join(
    f'<line x1="{16 + t * (W - 32)}" x2="{16 + t * (W - 32)}" y1="56" y2="61" class="tick"/>'
    f'<text x="{16 + t * (W - 32)}" y="76" class="lbl">{t:.1f}</text>' for t in (0, .2, .4, .6, .8, 1)
)
dup_svg = (f'<svg viewBox="0 0 {W} {H}" class="strip" role="img" aria-label="{len(agg)} PR pairs by duplicate probability">'
           f'<line x1="16" x2="{W - 16}" y1="56" y2="56" class="tick"/>{axis}{dots}</svg>')
dup_rows = "".join(
    f'<tr><td>{pr(a["pair"][0])} · {pr(a["pair"][1])}</td><td>{e(a["titles"][0])}<br><span class="dim">{e(a["titles"][1])}</span></td>'
    f'<td>{chip(a["noul"])}</td></tr>' for a in true
) + (f'<tr class="sep"><td>{pr(near["pair"][0])} · {pr(near["pair"][1])}</td><td>{e(near["titles"][0])}<br>'
     f'<span class="dim">{e(near["titles"][1])}</span><br><span class="dim">Same area, different bug. Both should merge.</span></td>'
     f'<td>{chip(near["noul"])}</td></tr>')

# ── 3 gate ──────────────────────────────────────────────────────────────────
g = load("gate")
grow = []
for arm, label in (("catalog", "Catalog only"), ("docs", "Docs only"), ("security", "Security boundary")):
    rs = g["rows"]
    pos = sum(r["truth"][arm] for r in rs)
    take_ok = sum(r["nouls"][arm] >= YES and r["truth"][arm] for r in rs)
    take_bad = sum(r["nouls"][arm] >= YES and not r["truth"][arm] for r in rs)
    miss = sum(r["nouls"][arm] < NO and r["truth"][arm] for r in rs)
    uns = sum(NO <= r["nouls"][arm] < YES for r in rs)
    grow.append(f"<tr><td>{label}</td><td>{pos}</td><td>{take_ok}</td><td>{take_bad}</td><td>{miss}</td><td>{uns}</td></tr>")
gate_rows = "".join(grow)
sec_fp = [r for r in g["rows"] if r["nouls"]["security"] >= YES and not r["truth"]["security"]]
sec_fp_list = "".join(f'<li>{pr(r["number"])} {e(r["title"])} <span class="dim">({r["nouls"]["security"]:.2f})</span></li>' for r in sec_fp)
sec_unsure = [r for r in g["rows"] if NO <= r["nouls"]["security"] < YES]

# ── 4 router ────────────────────────────────────────────────────────────────
ir = load("issue_router")
rows = ir["rows"]
acc = sum(r["hit"] for r in rows) / len(rows)


def bandrow(lo, hi, label):
    b = [r for r in rows if lo <= r["confidence"] < hi]
    a = sum(r["hit"] for r in b) / len(b)
    return (f'<tr><td>{label}</td><td>{len(b)}</td><td><span class="bar" style="--w:{a * 100:.0f}%"></span>'
            f'{pct(a)}</td></tr>')


router_bands = bandrow(0.9, 1.01, "0.9 or higher") + bandrow(0.6, 0.9, "0.6 to 0.9") + bandrow(0, 0.6, "below 0.6")
hi = [r for r in rows if r["confidence"] >= 0.9]
misses = sorted([r for r in rows if not r["hit"]], key=lambda r: -r["confidence"])[:4]
miss_list = "".join(
    f'<li>{iss(r["number"])} {e(r["title"])}: picked <code>{r["pick"]}</code> at {r["confidence"]:.2f}; '
    f'maintainers said <code>{", ".join(r["truth"])}</code></li>' for r in misses
)
h1, h2 = load("issue_router_heldout_v1")["rows"], load("issue_router_heldout_v2")["rows"]


def acc_hi(rs):
    hh = [r for r in rs if r["confidence"] >= 0.9]
    return sum(r["hit"] for r in rs) / len(rs), len(hh), sum(r["hit"] for r in hh) / len(hh)


H1, H2 = acc_hi(h1), acc_hi(h2)

# ── 5 approvals ─────────────────────────────────────────────────────────────
ap = load("approvals")["rows"]
ap_rows = "".join(f'<tr><td>“{e(r["reply"])}”</td><td><code>{r["pick"]}</code></td><td>{r["confidence"]:.2f}</td></tr>' for r in ap)

# ── 6 comments ──────────────────────────────────────────────────────────────
cm = load("comments")["rows"]
wake = [r for r in cm if r["new_evidence"] >= YES and r["automated"] < YES]
closing = [r for r in cm if r["closing"] >= YES]
bots = [r for r in cm if r["automated"] >= YES]
pick = {"Code0020161314", "smallmj", "LordMelkor", "greptile-apps[bot]", "austinpickett", "alt-glitch", "teknium1"}
seen, cm_rows = set(), ""
for r in cm:
    if r["user"] in pick and r["user"] not in seen:
        seen.add(r["user"])
        cm_rows += (f'<tr><td>{e(r["user"])}</td><td class="dim">{e(r["excerpt"][:90].replace(chr(10), " "))}…</td>'
                    f'<td>{r["new_evidence"]:.2f}</td><td>{r["automated"]:.2f}</td><td>{r["closing"]:.2f}</td></tr>')

# ── 7 priority ──────────────────────────────────────────────────────────────
pr_rows_ = load("priority")["rows"]
exact = sum(round(r["score"]) == r["truth"] for r in pr_rows_) / len(pr_rows_)


def mean(t):
    b = [r["score"] for r in pr_rows_ if r["truth"] == t]
    return len(b), sum(b) / len(b)


prio_rows = "".join(
    f'<tr><td>{lab}</td><td>{mean(t)[0]}</td><td>{mean(t)[1]:.2f}</td></tr>' for t, lab in ((0, "P3"), (1, "P2"), (2, "P1"))
)
top6 = sorted(pr_rows_, key=lambda r: -r["score"])[:6]
top_list = "".join(f'<li>{iss(r["number"])} {e(r["title"][:96])} <span class="dim">({["P3", "P2", "P1", "P0"][r["truth"]]}, {r["score"]:.2f})</span></li>' for r in top6)


def auc(xs, cut):
    pos = [s for s, t in xs if t >= cut]
    negs = [s for s, t in xs if t < cut]
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in negs) / (len(pos) * len(negs))


xs = [(r["score"], r["truth"]) for r in pr_rows_]
AUC_P1, AUC_P2 = auc(xs, 2), auc(xs, 1)

page = Template((HERE / "cases.template.html").read_text()).substitute(
    CALLS=CALLS, COST=f"${COST:.3f}", MS=MS, GH=GH,
    V_N=len(v), V_SUB=v_sub_wrong, V_JEV=v_jev_wrong, V_ROWS=v_rows,
    D_PAIRS=len(agg), D_CALLS=dd["usage"]["calls"], D_Q=dd["questions_per_call"], D_COST=f'${dd["usage"]["cost_usd"]:.4f}',
    D_MS=dd["usage"]["ms_median"], D_MIN=f'{min(a["noul"] for a in true):.2f}', D_MAX=f'{neg[0]["noul"]:.2f}',
    D_SVG=dup_svg, D_ROWS=dup_rows, D_POOL=dd["pool"],
    G_N=len(g["rows"]), G_ROWS=gate_rows, G_FP=sec_fp_list, G_UNS=len(sec_unsure),
    G_UNS_POS=sum(r["truth"]["security"] for r in sec_unsure),
    R_N=len(rows), R_ACC=pct(acc), R_BANDS=router_bands, R_HI_SHARE=pct(len(hi) / len(rows)),
    R_HI_ACC=pct(sum(r["hit"] for r in hi) / len(hi)), R_MISSES=miss_list,
    H1_ACC=pct(H1[0]), H1_HI=pct(H1[2]), H2_ACC=pct(H2[0]), H2_HI=pct(H2[2]),
    A_ROWS=ap_rows, A_N=len(ap),
    C_N=len(cm), C_WAKE=len(wake), C_CLOSE=len(closing), C_BOTS=len(bots), C_ROWS=cm_rows,
    P_N=len(pr_rows_), P_EXACT=pct(exact), P_ROWS=prio_rows, P_TOP=top_list,
    P_AUC1=f"{AUC_P1:.2f}", P_AUC2=f"{AUC_P2:.2f}",
)
(HERE.parent / "cases.html").write_text(page)
print("wrote cases.html", CALLS, f"${COST:.4f}", f"{MS}ms")
