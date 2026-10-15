"""Run every use case against live Jev on real hermes-agent data. Writes results/<case>.json."""
from __future__ import annotations

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jev import ask

HERE = Path(__file__).parent
DATA, OUT = HERE / "data", HERE / "results"
OUT.mkdir(exist_ok=True)
POOL = ThreadPoolExecutor(8)
random.seed(7)


def load(name):
    return json.loads((DATA / name).read_text())


def save(name, obj):
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1))
    print(f"{name}: {len(obj['rows'])} rows")


def usage(rows):
    return {
        "calls": len(rows),
        "ms_median": sorted(r["ms"] for r in rows)[len(rows) // 2],
        "cost_usd": round(sum(r["cost"] for r in rows), 5),
    }


def call(state, questions):
    r = ask(state, questions)
    return r["answers"], r["_ms"], r.get("usage", {}).get("cost", 0.0)


# 1 ── issue → component (choice) ────────────────────────────────────────────
COMPONENTS = {
    "comp/agent": "Core agent runtime: loop, agent_init, prompt builder, context-compression, responses endpoint",
    "comp/cli": "CLI entry point, hermes_cli/, setup wizard, install and update",
    "comp/gateway": "Gateway runner, session dispatch, delivery, messaging platforms",
    "comp/tools": "Tool registry, model_tools, toolsets, individual tools",
    "comp/tui": "Terminal UI (ui-tui/ + tui_gateway/)",
    "comp/acp": "Agent Communication Protocol adapter",
    "comp/cron": "Cron scheduler and job management",
    "comp/plugins": "Plugin system and bundled plugins",
    "comp/desktop": "Electron desktop app (apps/desktop/*)",
    "comp/dashboard": "Web dashboard / control panel UI",
    "comp/portal": "Nous portal / Hermes Pro / hosted-Hermes path",
}


def issue_router(n=150, criteria=None, out="issue_router", start=0):
    issues = load("issues-labeled.json")[start:start + n]

    def one(i):
        a, ms, cost = call(
            {"title": i["title"], "body": i["body"][:2500]},
            {"component": {"type": "choice", "instructions": "Which part of Hermes is this issue mainly about?",
                           "criteria": criteria or COMPONENTS}},
        )
        c = a["component"]
        truth = [l for l in i["labels"] if l.startswith("comp/")]
        return {"number": i["number"], "title": i["title"], "truth": truth, "pick": c["choice"],
                "confidence": c["confidence"], "probabilities": c["probabilities"],
                "hit": c["choice"] in truth, "ms": ms, "cost": cost}

    rows = list(POOL.map(one, issues))
    save(out, {"rows": rows, "usage": usage(rows)})


# v2: same question, sharper option descriptions after reading v1's confident misses
COMPONENTS_V2 = {
    **COMPONENTS,
    "comp/gateway": "Gateway core: the runner, session dispatch and delivery that every surface talks to",
    "comp/plugins": "Plugin system and bundled plugins, including messaging platform adapters "
                    "(Telegram, Discord, Slack, WhatsApp, IRC under plugins/platforms/) and A2A",
    "comp/acp": "Agent Communication Protocol adapter for editors (Zed, JetBrains); not A2A",
}


def issue_router_v2():
    # Tuned by reading v1's misses on issues 0–149, so score both versions on 150–299, which neither saw.
    issue_router(criteria=COMPONENTS, out="issue_router_heldout_v1", start=150)
    issue_router(criteria=COMPONENTS_V2, out="issue_router_heldout_v2", start=150)


# 2 ── issue → priority (score) ──────────────────────────────────────────────
PRIORITY = [
    "P3 Low: cosmetic, nice to have",
    "P2 Medium: degraded but a workaround exists",
    "P1 High: a major feature is broken with no workaround",
    "P0 Critical: data loss, security hole, or crash loop",
]


def priority(n=120):
    bugs = [i for i in load("issues-labeled.json")
            if "type/bug" in i["labels"] and any(l in ("P0", "P1", "P2", "P3") for l in i["labels"])][:n]

    def one(i):
        a, ms, cost = call(
            {"title": i["title"], "body": i["body"][:2500]},
            {"severity": {"type": "score", "instructions": "How severe is this bug for the people it affects?",
                          "criteria": PRIORITY}},
        )
        s = a["severity"]
        truth = 3 - int(next(l for l in i["labels"] if l in ("P0", "P1", "P2", "P3"))[1])  # P3→0 … P0→3
        return {"number": i["number"], "title": i["title"], "truth": truth, "score": s["score"],
                "confidence": s["confidence"], "probabilities": s.get("probabilities"), "ms": ms, "cost": cost}

    rows = list(POOL.map(one, bugs))
    save("priority", {"rows": rows, "usage": usage(rows)})


# 3 ── competing / duplicate PRs (noul fan-out) ──────────────────────────────
DUP_PAIRS = [(139170, 139171), (125130, 139177), (139090, 139101), (139097, 139100)]
NEAR_MISS = [(139117, 139182)]  # both "retry on update", different code paths


def pr_card(p):
    return {"title": p["title"], "description": (p.get("body") or "")[:1200], "files": p["files"][:25]}


def duplicates():
    named = {json.loads(f.read_text())["number"]: json.loads(f.read_text()) for f in DATA.glob("pr-*.json")}
    others = [p for p in load("prs-all.json") if p["number"] not in named]
    pool = list(named.values()) + random.sample(others, 30)
    truth = {frozenset(p) for p in DUP_PAIRS}
    rows = []

    def one(a):
        cands = [b for b in pool if b["number"] != a["number"]]
        qs = {str(b["number"]): {"type": "noul", "instructions": {
            "other_pull_request": pr_card(b),
            "question": "This other pull request fixes the same underlying problem as the one in the state, "
                        "so only one of the two should merge."}} for b in cands}
        ans, ms, cost = call({"pull_request": pr_card(a)}, qs)
        return [{"a": a["number"], "b": int(k), "a_title": a["title"], "b_title": next(c["title"] for c in cands if str(c["number"]) == k),
                 "noul": v["noul"], "dup": frozenset((a["number"], int(k))) in truth,
                 "near_miss": frozenset((a["number"], int(k))) in {frozenset(p) for p in NEAR_MISS},
                 "ms": ms, "cost": cost, "questions": len(qs)} for k, v in ans.items()]

    calls = list(POOL.map(one, named.values()))
    for c in calls:
        rows += c
    per_call = [{"ms": c[0]["ms"], "cost": c[0]["cost"]} for c in calls]
    save("duplicates", {"rows": rows, "usage": usage(per_call), "pool": len(pool),
                        "questions_per_call": len(pool) - 1})


# 4 ── the workflow gate itself, on real PRs ─────────────────────────────────
ARMS = {
    "catalog": "The pull request only adds or updates a plugin-catalog entry and changes no Hermes code.",
    "security": "The change alters an authentication, authorization, secret-handling, or sandbox boundary.",
    "docs": "The change only touches documentation and changes no runtime behavior.",
}


def gate(n=160):
    prs = load("prs-all.json")[:n]

    def truth(p):
        f = p["files"]
        return {
            "catalog": bool(f) and all(x.startswith("plugin-catalog/") for x in f),
            "security": any(l in p["labels"] for l in ("type/security", "sweeper:risk-security-boundary", "area/auth")),
            "docs": bool(f) and all(x.endswith((".md", ".mdx")) or x.startswith("website/") for x in f),
        }

    def one(p):
        qs = {k: {"type": "noul", "instructions": v} for k, v in ARMS.items()}
        a, ms, cost = call(pr_card(p), qs)
        return {"number": p["number"], "title": p["title"], "labels": p["labels"], "files": len(p["files"]),
                "nouls": {k: a[k]["noul"] for k in ARMS}, "truth": truth(p), "ms": ms, "cost": cost}

    rows = list(POOL.map(one, prs))
    save("gate", {"rows": rows, "usage": usage(rows), "arms": ARMS})


# 5 ── approval replies from chat (choice) — synthetic inputs ────────────────
REPLIES = [
    "yes go ahead", "lgtm 🚀", "ship it", "approved, thanks!",
    "no", "don't merge this", "reject — wrong branch", "hold off, this breaks prod",
    "what does this change for windows users?", "can you show me the diff first?",
    "yes but fix the typo in the title first", "sure, after the release on friday",
    "hmm", "ok", "👀", "idk ask teknium",
]


def approvals():
    crit = {
        "approve": "Approves the action now, unconditionally",
        "reject": "Declines or blocks the action",
        "question": "Asks for more information before deciding",
        "conditional": "Approves only once something else happens first",
        "unclear": "Does not express a decision",
    }

    def one(text):
        a, ms, cost = call({"pending_action": "Merge PR #139186 into main", "reply": text},
                           {"intent": {"type": "choice", "instructions": "What is this reply to the approval request?",
                                       "criteria": crit}})
        c = a["intent"]
        return {"reply": text, "pick": c["choice"], "confidence": c["confidence"],
                "probabilities": c["probabilities"], "ms": ms, "cost": cost}

    rows = list(POOL.map(one, REPLIES))
    save("approvals", {"rows": rows, "usage": usage(rows), "criteria": crit})


# 6 ── agent step verdicts: Jev vs today's substring rule — synthetic inputs ─
SUMMARIES = [
    ("Implemented the retry and all 14 tests pass.", True),
    ("Done. PASS.", True),
    ("The fix works on macOS; I could not test Windows but nothing there changed.", True),
    ("This should NOT PASS: the migration drops the sessions table.", False),
    ("Tests PASS locally but CI is red on the lint job, so this is not ready.", False),
    ("I couldn't reproduce the bug, so I made no changes.", False),
    ("PASSED the type check; the runtime still crashes on startup.", False),
    ("Yes, I looked at it. The approach is wrong and needs a redesign.", False),
    ("Partially done: 3 of 5 endpoints migrated.", False),
    ("All checks green. Merged the branch into the PR as asked.", True),
]


def verdicts():
    def one(item):
        text, truth = item
        a, ms, cost = call({"step_goal": "Fix the bug and leave the branch ready to merge", "step_summary": text},
                           {"done": {"type": "noul", "instructions": "The step achieved its goal and the work is ready to move on."}})
        up = text.upper()
        substring = "PASS" in up or up.startswith("YES")
        return {"summary": text, "truth": truth, "noul": a["done"]["noul"], "substring": substring, "ms": ms, "cost": cost}

    rows = list(POOL.map(one, SUMMARIES))
    save("verdicts", {"rows": rows, "usage": usage(rows)})


# 7 ── comment triage on real thread comments (noul fan-out) ─────────────────
def comments():
    cs = load("comments.json")

    def one(c):
        a, ms, cost = call({"author": c["user"], "author_type": c["type"], "comment": c["body"][:1500]}, {
            "new_evidence": {"type": "noul", "instructions": "The comment adds new evidence: a reproduction, measurements, logs, or a confirmed environment."},
            "automated": {"type": "noul", "instructions": "The comment is an automated status message or bot output."},
            "closing": {"type": "noul", "instructions": "The comment explains why a pull request or issue is being closed or superseded."},
        })
        return {"issue": c["issue"], "user": c["user"], "excerpt": c["body"][:160], "ms": ms, "cost": cost,
                **{k: a[k]["noul"] for k in ("new_evidence", "automated", "closing")}}

    rows = list(POOL.map(one, cs))
    save("comments", {"rows": rows, "usage": usage(rows)})


# 2b ── priority, decomposed into atomic nouls and combined in code ──────────
FACTORS = {
    "data_loss": "The bug loses, corrupts, or overwrites user data.",
    "security": "The bug exposes secrets or lets someone bypass an access control.",
    "cannot_start": "Hermes or a whole surface cannot start, crash-loops, or becomes unusable until restarted.",
    "no_workaround": "The reporter has no way to work around the problem.",
    "cosmetic": "The bug is cosmetic: wrong text, styling, or a misleading message, with no functional impact.",
    "narrow": "The bug only affects an unusual configuration or a rare edge case.",
}


def priority_atomic(n=120):
    bugs = [i for i in load("issues-labeled.json")
            if "type/bug" in i["labels"] and any(l in ("P0", "P1", "P2", "P3") for l in i["labels"])][:n]

    def one(i):
        a, ms, cost = call({"title": i["title"], "body": i["body"][:2500]},
                           {k: {"type": "noul", "instructions": v} for k, v in FACTORS.items()})
        truth = 3 - int(next(l for l in i["labels"] if l in ("P0", "P1", "P2", "P3"))[1])
        return {"number": i["number"], "title": i["title"], "truth": truth,
                "f": {k: a[k]["noul"] for k in FACTORS}, "ms": ms, "cost": cost}

    rows = list(POOL.map(one, bugs))
    save("priority_atomic", {"rows": rows, "usage": usage(rows), "factors": FACTORS})


CASES = {f.__name__: f for f in (issue_router, issue_router_v2, priority, priority_atomic, duplicates, gate, approvals, verdicts, comments)}

if __name__ == "__main__":
    for name in sys.argv[1:] or CASES:
        CASES[name]()
