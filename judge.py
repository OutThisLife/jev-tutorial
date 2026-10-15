"""Jev-backed judgement for workflow gates — the sketch from the tutorial, runnable."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable

ENDPOINTS = {
    "typesafe": ("https://api.typesafe.ai/v1/systemone", "TYPESAFE_API_KEY", "jev-latest"),
    "openrouter": ("https://openrouter.ai/api/v1/systemone", "OPENROUTER_API_KEY", "~typesafe/jev-latest"),
}

YES, NO = 0.8, 0.35  # noul >= YES takes the arm; noul < NO skips it; between is "unsure"


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


def gate_state(inputs: list[dict], summaries: dict, payload: Any, cap: int = 2000) -> dict:
    """What the gate knows, as structured state — not a prompt."""
    return {
        "upstream": [
            {"step": i["nodeId"], "verdict": i.get("verdict"), "summary": str(summaries.get(i["nodeId"], ""))[:cap]}
            for i in inputs
        ],
        "trigger_payload": json.dumps(payload, default=str)[:cap] if payload is not None else None,
    }


def judge_arms(arms: list[dict], state: dict, ask: Callable[[Any, dict], dict] = ask_jev) -> dict[str, float]:
    """One Noul per Judgement arm, all in one call. {arm_id: noul}."""
    questions = {
        a["id"]: {"type": "noul", "instructions": a["when"]["source"]}
        for a in arms
        if (a.get("when") or {}).get("mode") == "prose"
    }
    if not questions:
        return {}
    return {arm_id: ans["noul"] for arm_id, ans in ask(state, questions).items()}


def choose_arm(arms: list[dict], inputs: list[dict], state: dict, holds, ask=ask_jev) -> tuple[dict | None, str]:
    """First match wins, same as today. Returns (arm, why)."""
    nouls: dict[str, float] | None = None  # asked lazily: no Jev call if a rule arm wins first
    for arm in arms:
        when = arm.get("when") or {}
        if when.get("mode") != "prose":
            if holds(when, inputs):
                return arm, "rule"
            continue
        if nouls is None:
            nouls = judge_arms(arms, state, ask)
        p = nouls.get(arm["id"], 0.0)
        if p >= YES:
            return arm, f"jev {p:.2f}"
        if p >= NO:
            # Stop here: a later arm must not win by default. Hand off to an
            # "unsure" arm (wire it to a Human approval step) if the gate has one.
            unsure = next((a for a in arms if (a.get("when") or {}).get("mode") == "unsure"), None)
            return unsure, f"unsure {p:.2f} on {arm['id']}"
    return None, "no arm"
