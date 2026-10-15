"""Design / n8n experiments, live against Jev. Writes results/<case>.json."""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "cases"))
from jev import ask  # noqa: E402

HERE = Path(__file__).parent
DATA, OUT = HERE / "data", HERE / "results"
OUT.mkdir(exist_ok=True)
POOL = ThreadPoolExecutor(8)


def load(n):
    return json.loads((DATA / n).read_text())


def call(state, questions):
    r = ask(state, questions)
    return r["answers"], r["_ms"], r.get("usage", {}).get("cost", 0.0)


def save(name, rows, **extra):
    med = sorted(r["ms"] for r in rows)[len(rows) // 2]
    (OUT / f"{name}.json").write_text(json.dumps(
        {"rows": rows, "usage": {"calls": len(rows), "ms_median": med, "cost_usd": round(sum(r["cost"] for r in rows), 5)}, **extra},
        indent=1))
    print(f"{name}: {len(rows)} rows")


# ── n8n: swap the template's LLM classifier for one Choice ───────────────────
# Template 15051 "Classify and route DevOps chat requests with Mattermost and Claude".
# Messages are mine (not the template's examples); labels are mine.
MESSAGES = [
    ("Bump the CPU request on checkout-api to 500m, it's throttling at peak", "modify_infrastructure"),
    ("Need a new Kafka topic `payments.refunds` with 12 partitions", "modify_infrastructure"),
    ("Can we drop the old staging Elasticsearch? nobody's touched it since march", "modify_infrastructure"),
    ("Please add a DNS record for status.example.com pointing at the new LB", "modify_infrastructure"),
    ("prod is returning 502s on /login for everyone right now", "incident"),
    ("Postgres primary just failed over and the app can't reconnect", "incident"),
    ("disk on the logging nodes is at 98% and climbing fast", "incident"),
    ("users are reporting that uploads hang forever since ~10 minutes ago", "incident"),
    ("what's the retention on our Loki logs?", "question"),
    ("Is there a reason staging and prod use different Redis versions?", "question"),
    ("how do I get read access to the prod replica?", "question"),
    ("where do the alert routing rules live these days?", "question"),
    ("main is red: the docker build step fails with `no space left on device`", "ci_cd_error"),
    ("deploy to staging has been stuck on 'waiting for runner' for 40 min", "ci_cd_error"),
    ("every PR's e2e job times out after the node 22 bump", "ci_cd_error"),
    ("the release workflow can't push the image, 403 from the registry", "ci_cd_error"),
    ("We want feature flags; can we stand up Unleash or similar?", "new_system"),
    ("Let's move our secrets from env files to Vault properly, we've never had it", "new_system"),
    ("Could we try Grafana Tempo for tracing? we don't have any tracing yet", "new_system"),
    ("Proposal: replace Jenkins with GitHub Actions for all services", "new_system"),
    ("FYI the cloud provider is upgrading our k8s control plane Saturday 02:00 UTC", "announcement"),
    ("Heads up: egress pricing goes up 20% next month per the vendor email", "announcement"),
    ("Scheduled maintenance on the shared VPN gateway tomorrow 18:00–19:00", "announcement"),
    ("Reminder: the old bastion host is being retired on the 30th", "announcement"),
    ("thanks for the help yesterday!!", "other"),
    ("does anyone know a good lunch spot near the office?", "other"),
    ("lol", "other"),
    ("can someone review my vacation request in the HR tool", "other"),
]


def n8n_categories() -> dict[str, str]:
    text = (DATA / "n8n-categories.md").read_text().split("\n---\n")[0]
    cats = {}
    for block in re.split(r"^### ", text, flags=re.M)[1:]:
        name, _, body = block.partition("\n")
        cats[name.strip()] = re.sub(r"\s+", " ", body).strip()[:1200]
    return cats


def chat(model: str, system: str, user: str) -> tuple[str, int, float]:
    body = json.dumps({"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                       "usage": {"include": True}}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body,
                                 {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json"})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    return d["choices"][0]["message"]["content"] or "", round((time.perf_counter() - t) * 1000), d.get("usage", {}).get("cost", 0.0)


def n8n():
    cats = n8n_categories()
    raw = json.loads((DATA / "n8n-15051.json").read_text())["workflow"]["workflow"]
    prompt = next(n for n in raw["nodes"] if n["name"] == "AI Agent")["parameters"]["options"]["systemMessage"]
    # Same prompt minus the Mattermost thread-lookup steps the LLM can't run here.
    llm_system = prompt[prompt.find("## Step 3"):]

    def one(item):
        text, truth = item
        a, ms, cost = call({"channel": "#devops", "message": text},
                           {"category": {"type": "choice", "instructions": "Which kind of request is this message?", "criteria": cats}})
        c = a["category"]
        out, lms, lcost = chat("anthropic/claude-sonnet-4.6", llm_system, f"USER MESSAGE:\n{text}")
        m = re.search(r'"category"\s*:\s*"([a-z_]+)"', out)
        return {"message": text, "truth": truth, "pick": c["choice"], "confidence": c["confidence"],
                "probabilities": c["probabilities"], "ms": ms, "cost": cost,
                "llm_pick": m.group(1) if m else None, "llm_ms": lms, "llm_cost": lcost, "llm_raw": out[:400]}

    rows = list(POOL.map(one, MESSAGES))
    save("n8n", rows, categories=list(cats), llm_prompt_chars=len(llm_system))


# ── design system: which Button variant is this? ─────────────────────────────
VARIANTS = {
    "ghost": "Icon or chrome button with no fill or ring: secondary text that lifts on hover. Toolbars, row actions, close/kebab buttons.",
    "text": "Boxless inline-text action, quiet: muted label text that underlines on hover (e.g. Cancel, Clear).",
    "textStrong": "Emphasized inline-text action: bold and always underlined. The actionable affordance in a row (Change, Set, Open logs).",
    "outline": "Quiet boxed action: transparent fill with a thin inset ring.",
    "secondary": "Soft-fill action: the default non-primary button look.",
    "default": "Primary call to action: solid primary fill.",
    "destructive": "Destructive action: solid red fill (delete, remove permanently).",
    "link": "Hyperlink-styled action in primary color that underlines on hover.",
}


def variants(n=160):
    random.seed(11)
    rows_all = [b for b in load("buttons.json") if b["variant"] in VARIANTS]
    by = {}
    for b in rows_all:
        by.setdefault(b["variant"], []).append(b)
    sample = []
    for v, bs in by.items():  # stratify so rare variants show up
        random.shuffle(bs)
        sample += bs[: max(3, round(n * len(bs) / len(rows_all)))]

    def one(b):
        a, ms, cost = call({"component": "Button", "file": b["file"], "jsx": b["jsx"]},
                           {"variant": {"type": "choice", "instructions": "Which variant should this Button use?", "criteria": VARIANTS}})
        c = a["variant"]
        return {"file": b["file"], "truth": b["variant"], "pick": c["choice"], "confidence": c["confidence"],
                "probabilities": c["probabilities"], "jsx": b["jsx"], "ms": ms, "cost": cost}

    rows = list(POOL.map(one, sample))
    save("variants", rows)


# ── design system: does this icon fit its label? ─────────────────────────────
def icons():
    pairs = load("icon-pairs.json")
    vocab = sorted({p["icon"] for p in pairs})

    def one(p):
        a, ms, cost = call({"control": "icon-only button", "accessible_label": p["text"], "icon": p["icon"]}, {
            "fits": {"type": "noul", "instructions": "The icon clearly communicates the action named by the label."},
            "best": {"type": "choice", "instructions": "Which icon best communicates this label's action?",
                     "criteria": {i: None for i in vocab}},
        })
        return {**p, "fits": a["fits"]["noul"], "best": a["best"]["choice"], "best_conf": a["best"]["confidence"], "ms": ms, "cost": cost}

    rows = list(POOL.map(one, pairs))
    save("icons", rows, vocab=vocab)


# ── design → code: which existing primitive should this markup be? ──────────
def primitives():
    docs = {re.sub(r"\.tsx$", "", p["file"]): f'{", ".join(p["exports"][:3])}: {p["doc"][:260] or "(no doc comment)"}'
            for p in load("primitives.json")}
    cases = [c for c in load("adoptions.json") if c["primitive"] in docs]

    def one(c):
        a, ms, cost = call({"hand_rolled_markup": c["removed"]},
                           {"primitive": {"type": "choice",
                                          "instructions": "This markup was hand-rolled. Which existing design-system component should it be built on?",
                                          "criteria": docs}})
        p = a["primitive"]
        top3 = sorted(p["probabilities"], key=lambda k: -p["probabilities"][k])[:3]
        return {"sha": c["sha"], "subject": c["subject"], "file": c["file"], "truth": c["primitive"], "pick": p["choice"],
                "confidence": p["confidence"], "top3": top3, "ms": ms, "cost": cost}

    rows = list(POOL.map(one, cases))
    save("primitives", rows, n_options=len(docs))


def tips():
    """DESIGN.md: '<Tip> only when hover teaches something new' — one call per real Tip in the app."""
    rows_in = load("tips.json")

    def one(t):
        a, ms, cost = call({
            "control": {"icon": t["icon"], "visible_text": t["visible_text"] or None, "aria_label": t["aria_label"],
                        "opens_menu": t["menu_trigger"]},
            "tooltip": t["tooltip"]}, {
            "teaches": {"type": "noul", "instructions": "Hovering reveals something the user cannot already see or infer from the control itself."},
            "dismiss": {"type": "noul", "instructions": "The control is a close or dismiss button."},
            "menu": {"type": "noul", "instructions": "The control's job is to open a menu of further actions."},
        })
        return {**{k: t[k] for k in ("file", "tooltip", "aria_label", "icon", "visible_text", "menu_trigger")},
                **{k: a[k]["noul"] for k in ("teaches", "dismiss", "menu")}, "ms": ms, "cost": cost}

    rows = list(POOL.map(one, rows_in))
    save("tips", rows)


CASES = {f.__name__: f for f in (n8n, variants, icons, primitives, tips)}
if __name__ == "__main__":
    for name in sys.argv[1:] or CASES:
        CASES[name]()
