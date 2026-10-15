"""Tiny Jev client: one POST, every question at once."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

URL = "https://openrouter.ai/api/v1/systemone"
MODEL = "~typesafe/jev-latest"


def ask(state, questions: dict, timeout: float = 20.0) -> dict:
    body = json.dumps({"model": MODEL, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(
        URL, body, {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json"}
    )
    for attempt in range(4):
        t = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out = json.load(resp)
            out["_ms"] = round((time.perf_counter() - t) * 1000)
            return out
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(0.5 * 2**attempt)
                continue
            raise RuntimeError(f"{e.code}: {e.read()[:300]!r}") from e
    raise RuntimeError("unreachable")
