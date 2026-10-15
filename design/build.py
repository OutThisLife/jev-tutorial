"""Render ../design.html from results/*.json. Every number on the page comes from here."""
from __future__ import annotations

import html
import json
from pathlib import Path
from string import Template

HERE = Path(__file__).parent
R = HERE / "results"


def load(n):
    return json.loads((R / f"{n}.json").read_text())


def e(s):
    return html.escape(str(s))


def pct(x):
    return f"{x * 100:.0f}%"


def src(path):
    return f'<code>{e(path.split("/")[-1])}</code>'


def subject(s):
    return s.split(": ", 1)[-1]


files = list(R.glob("*.json"))
CALLS = sum(load(f.stem)["usage"]["calls"] for f in files)
COST = sum(load(f.stem)["usage"]["cost_usd"] for f in files)

# ── n8n ─────────────────────────────────────────────────────────────────────
n = load("n8n")
nr = n["rows"]
jev_ok = sum(r["pick"] == r["truth"] for r in nr)
llm_ok = sum(r["llm_pick"] == r["truth"] for r in nr)
llm_ms = sorted(r["llm_ms"] for r in nr)[len(nr) // 2]
llm_cost = sum(r["llm_cost"] for r in nr)
jev_cost = n["usage"]["cost_usd"]
low = sorted(nr, key=lambda r: r["confidence"])[:3]
n8n_low = "".join(f'<li>“{e(r["message"])}”: <code>{r["pick"]}</code> at {r["confidence"]:.2f}</li>' for r in low)
smoke = (HERE / "n8n/smoke-run.txt").read_text()
smoke = json.loads(smoke[smoke.find("{"):])
rd = smoke["data"]["resultData"]["runData"]
SMOKE_JEV_MS = rd["Ask Jev"][0]["executionTime"]
v = rd["Verdict"][0]["data"]["main"][0][0]["json"]

# ── variants ────────────────────────────────────────────────────────────────
vr = load("variants")["rows"]
v_hi = [r for r in vr if r["confidence"] >= 0.9]
v_lo = [r for r in vr if r["confidence"] < 0.6]
v_acc = sum(r["pick"] == r["truth"] for r in vr) / len(vr)
VAR_ROWS = "".join(
    f'<tr><td>{lab}</td><td>{len(b)}</td><td><span class="bar" style="--w:{a * 100:.0f}%"></span>{pct(a)}</td></tr>'
    for lab, b in (("0.9 or higher", v_hi), ("0.6 to 0.9", [r for r in vr if 0.6 <= r["confidence"] < 0.9]), ("below 0.6", v_lo))
    for a in [sum(r["pick"] == r["truth"] for r in b) / len(b)]
)

# ── icons ───────────────────────────────────────────────────────────────────
ir = sorted((r for r in load("icons")["rows"] if "hermes" not in r["file"]), key=lambda r: r["fits"])
fit_ok = [r for r in ir if r["fits"] >= 0.8]
ICON_LOW = "".join(
    f'<tr><td><code>{r["icon"]}</code></td><td>{e(r["text"])}</td><td>{r["fits"]:.2f}</td>'
    f'<td><code>{r["best"]}</code></td><td>{src(r["file"])}</td></tr>' for r in ir[:6]
)
ICON_HIGH = ", ".join(f'<code>{r["icon"]}</code> → {e(r["text"])}' for r in ir[-5:])

# ── tips ────────────────────────────────────────────────────────────────────
tr = load("tips")["rows"]
viol = [r for r in tr if r["dismiss"] >= 0.8 or r["menu"] >= 0.8]
TIP_ROWS = "".join(
    f'<tr><td>{e(r["tooltip"])}</td><td>{"close / dismiss" if r["dismiss"] >= 0.8 else "opens a menu"}</td>'
    f'<td>{max(r["dismiss"], r["menu"]):.2f}</td><td>{src(r["file"])}</td></tr>' for r in viol
)

# ── primitives ──────────────────────────────────────────────────────────────
pr = load("primitives")
prr = pr["rows"]
top1 = sum(r["pick"] == r["truth"] for r in prr)
top3 = sum(r["truth"] in r["top3"] for r in prr)
p_hi = [r for r in prr if r["confidence"] >= 0.9]
p_hi_ok = sum(r["pick"] == r["truth"] for r in p_hi)
wins = [r for r in prr if r["pick"] == r["truth"] and r["confidence"] >= 0.9]
seen, P_WINS = set(), ""
for r in wins:
    if subject(r["subject"]) in seen:
        continue
    seen.add(subject(r["subject"]))
    P_WINS += f'<li>{e(subject(r["subject"]))}: <code>{r["truth"]}</code> at {r["confidence"]:.2f}</li>'

page = Template((HERE / "design.template.html").read_text()).substitute(
    CALLS=CALLS, COST=f"${COST:.3f}",
    N_N=len(nr), N_JEV=jev_ok, N_LLM=llm_ok, N_LLM_MS=f"{llm_ms / 1000:.1f} s", N_JEV_MS=n["usage"]["ms_median"],
    N_LLM_COST=f"${llm_cost:.3f}", N_JEV_COST=f"${jev_cost:.4f}", N_RATIO=f"{llm_cost / jev_cost:.0f}",
    N_SPEED=f'{llm_ms / n["usage"]["ms_median"]:.0f}',
    N_PROMPT=f'{n["llm_prompt_chars"]:,}', N_LOW=n8n_low, N_CATS=len(n["categories"]),
    S_MS=SMOKE_JEV_MS, S_CAT=v["category"], S_CONF=v["confidence"],
    V_N=len(vr), V_ACC=pct(v_acc), V_ROWS=VAR_ROWS, V_HI=len(v_hi), V_HI_ACC=pct(sum(r["pick"] == r["truth"] for r in v_hi) / len(v_hi)),
    I_N=len(ir), I_LOW=ICON_LOW, I_HIGH=ICON_HIGH, I_OK=len(fit_ok),
    T_N=len(tr), T_V=len(viol), T_ROWS=TIP_ROWS,
    P_N=len(prr), P_OPTS=pr["n_options"], P_TOP1=top1, P_TOP3=top3, P_HI=len(p_hi), P_HI_OK=p_hi_ok, P_WINS=P_WINS,
)
(HERE.parent / "design.html").write_text(page)
print("wrote design.html", CALLS, f"${COST:.4f}")
