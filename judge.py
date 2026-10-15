"""A workflow gate that asks Jev about its judgement paths. The sketch from the tutorial, runnable."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable

ENDPOINTS = {
    "typesafe": ("https://api.typesafe.ai/v1/systemone", "TYPESAFE_API_KEY", "jev-latest"),
    "openrouter": ("https://openrouter.ai/api/v1/systemone", "OPENROUTER_API_KEY", "~typesafe/jev-latest"),
}

YES, NO = 0.8, 0.35  # at or above YES, take the path; below NO, skip it; in between, ask a person


def _backend() -> tuple[str, str, str] | None:
    for name in ("typesafe", "openrouter"):
        url, env, model = ENDPOINTS[name]
        if key := os.environ.get(env):
            return url, key, model
    return None


def ask_jev(state: Any, questions: dict, timeout: float = 5.0) -> dict:
    """One POST, every question at once. Returns {question_id: answer}."""
    backend = _backend()
    if backend is None:
        raise RuntimeError("no TYPESAFE_API_KEY or OPENROUTER_API_KEY")
    url, key, model = backend
    body = json.dumps({"model": model, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(url, body, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)["answers"]


def gate_state(steps: list[dict], payload: Any, cap: int = 2000) -> dict:
    """What the gate knows, sent as data rather than a prompt."""
    return {
        "steps": [{"step": s["id"], "verdict": s.get("verdict"), "summary": str(s.get("summary", ""))[:cap]} for s in steps],
        "trigger": json.dumps(payload, default=str)[:cap] if payload is not None else None,
    }


def is_judgement(path: dict) -> bool:
    return (path.get("when") or {}).get("kind") == "judgement"


def judge_paths(paths: list[dict], state: dict, ask: Callable[[Any, dict], dict] = ask_jev) -> dict[str, float]:
    """One yes/no question per judgement path, all in one call. {path_id: probability of yes}."""
    questions = {p["id"]: {"type": "noul", "instructions": p["when"]["question"]} for p in paths if is_judgement(p)}
    if not questions:
        return {}
    return {pid: ans["noul"] for pid, ans in ask(state, questions).items()}


def choose_path(paths: list[dict], steps: list[dict], state: dict, rule_holds, ask=ask_jev) -> tuple[dict | None, str]:
    """Walk the paths in order; the first one that holds wins. Returns (path, why)."""
    answers: dict[str, float] | None = None  # asked lazily, so a rule can win with no Jev call
    for path in paths:
        when = path.get("when") or {}
        if not is_judgement(path):
            if rule_holds(when, steps):
                return path, "rule"
            continue
        if answers is None:
            answers = judge_paths(paths, state, ask)
        p = answers.get(path["id"], 0.0)
        if p >= YES:
            return path, f"jev {p:.2f}"
        if p >= NO:
            # Stop here, so a later path can't win by default. Hand off to the
            # "not sure" path (wire it to a person) if the gate has one.
            unsure = next((x for x in paths if (x.get("when") or {}).get("kind") == "unsure"), None)
            return unsure, f"unsure {p:.2f} on {path['id']}"
    return None, "no path"
