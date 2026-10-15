import os
import sys

sys.path.insert(0, os.environ.get("HERMES_CHECKOUT", "../hermes-agent"))  # a checkout of the Workflows PR branch
from workflow.topology import holds  # the real one from the PR branch

from judge import choose_arm, gate_state

ARMS = [
    {"id": "ship", "when": {"mode": "all-pass"}},
    {"id": "security", "when": {"mode": "prose", "source": "The change weakens an authentication or CSRF control."}},
    {"id": "docs", "when": {"mode": "prose", "source": "The change only touches documentation."}},
    {"id": "else", "when": {"mode": "always"}},
]
calls = []


def fake(nouls):
    def ask(state, questions):
        calls.append(sorted(questions))
        return {k: {"type": "noul", "noul": nouls[k]} for k in questions}
    return ask


st = gate_state([{"nodeId": "review", "verdict": "PASS"}], {"review": "ok"}, {"pr": 1})

# rule arm wins first -> Jev never called
calls.clear()
arm, why = choose_arm(ARMS, [{"nodeId": "review", "verdict": "PASS"}], st, holds, fake({}))
assert arm["id"] == "ship" and why == "rule" and calls == [], (arm, why, calls)

fail = [{"nodeId": "review", "verdict": "FAIL"}]
# confident yes on first judgement arm -> one call, both arms asked together
calls.clear()
arm, why = choose_arm(ARMS, fail, st, holds, fake({"security": 0.93, "docs": 0.9}))
assert arm["id"] == "security" and calls == [["docs", "security"]], (arm, why, calls)

# confident no, then yes -> second arm, still one call
calls.clear()
arm, why = choose_arm(ARMS, fail, st, holds, fake({"security": 0.04, "docs": 0.88}))
assert arm["id"] == "docs" and len(calls) == 1

# both no -> falls through to `always`
arm, why = choose_arm(ARMS, fail, st, holds, fake({"security": 0.1, "docs": 0.2}))
assert arm["id"] == "else", (arm, why)

# unsure -> stops, no default arm sneaks in
arm, why = choose_arm(ARMS, fail, st, holds, fake({"security": 0.55, "docs": 0.99}))
assert arm is None and why.startswith("unsure 0.55"), (arm, why)

# unsure with an "unsure" arm wired -> hands off to it (holds() never matches it as a rule)
ask_human = {"id": "ask", "when": {"mode": "unsure"}}
arm, why = choose_arm([*ARMS[:3], ask_human, ARMS[3]], fail, st, holds, fake({"security": 0.6, "docs": 0.1}))
assert arm["id"] == "ask", (arm, why)

print("ok: 6 cases")
