"""Checks choose_path with Jev replaced by a fake. Run: python3 test_judge.py"""
from judge import choose_path, gate_state


def rule_holds(when, steps):
    kind = when.get("kind")
    if kind == "all-pass":
        return all(s.get("verdict") == "PASS" for s in steps)
    if kind == "any-fail":
        return any(s.get("verdict") == "FAIL" for s in steps)
    return kind == "always"


PATHS = [
    {"id": "ship", "when": {"kind": "all-pass"}},
    {"id": "security", "when": {"kind": "judgement", "question": "The change weakens an authentication or CSRF control."}},
    {"id": "docs", "when": {"kind": "judgement", "question": "The change only touches documentation."}},
    {"id": "else", "when": {"kind": "always"}},
]
calls = []


def fake(answers):
    def ask(state, questions):
        calls.append(sorted(questions))
        return {k: {"type": "noul", "noul": answers[k]} for k in questions}
    return ask


passed = [{"id": "review", "verdict": "PASS", "summary": "ok"}]
failed = [{"id": "review", "verdict": "FAIL", "summary": "Removed the CSRF check on /logout"}]
st = gate_state(failed, {"pr": 1})

# a rule wins first, so Jev is never called
calls.clear()
path, why = choose_path(PATHS, passed, st, rule_holds, fake({}))
assert path["id"] == "ship" and why == "rule" and calls == [], (path, why, calls)

# a confident yes on the first judgement path: one call, both questions asked together
calls.clear()
path, why = choose_path(PATHS, failed, st, rule_holds, fake({"security": 0.93, "docs": 0.9}))
assert path["id"] == "security" and calls == [["docs", "security"]], (path, why, calls)

# a confident no, then a yes: the second path, still one call
calls.clear()
path, why = choose_path(PATHS, failed, st, rule_holds, fake({"security": 0.04, "docs": 0.88}))
assert path["id"] == "docs" and len(calls) == 1

# both no: the fallback takes it
path, why = choose_path(PATHS, failed, st, rule_holds, fake({"security": 0.1, "docs": 0.2}))
assert path["id"] == "else", (path, why)

# unsure: the gate stops instead of letting the fallback win
path, why = choose_path(PATHS, failed, st, rule_holds, fake({"security": 0.55, "docs": 0.99}))
assert path is None and why.startswith("unsure 0.55"), (path, why)

# unsure with a "not sure" path: it hands off there
ask_person = {"id": "ask", "when": {"kind": "unsure"}}
path, why = choose_path([*PATHS[:3], ask_person, PATHS[3]], failed, st, rule_holds, fake({"security": 0.6, "docs": 0.1}))
assert path["id"] == "ask", (path, why)

print("ok: 6 cases")
