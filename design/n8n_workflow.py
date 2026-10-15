"""Write an importable n8n workflow that routes a chat message with one Jev call.

Two versions from one definition:
  jev-router.json       Webhook trigger, OpenRouter key from an n8n Header Auth credential (what you import)
  jev-router.test.json  Manual trigger + sample message, key from $env (what the docker smoke test runs)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import n8n_categories  # noqa: E402

HERE = Path(__file__).parent
CATS = n8n_categories()

BODY = (
    "={{ JSON.stringify({ model: '~typesafe/jev-latest', state: { channel: $json.channel, message: $json.message }, "
    "questions: { category: { type: 'choice', instructions: 'Which kind of request is this message?', criteria: "
    + json.dumps(CATS) + " } } }) }}"
)


def node(name, type_, pos, params, version=1, **extra):
    return {"parameters": params, "name": name, "type": type_, "typeVersion": version, "position": pos, "id": name.lower().replace(" ", "-"), **extra}


def jev_node(auth_header):
    params = {
        "method": "POST",
        "url": "https://openrouter.ai/api/v1/systemone",
        "sendBody": True,
        "contentType": "raw",
        "rawContentType": "application/json",
        "body": BODY,
        "options": {},
    }
    if auth_header:
        params |= {"sendHeaders": True, "headerParameters": {"parameters": [
            {"name": "Authorization", "value": "=Bearer {{ $env.OPENROUTER_API_KEY }}"}]}}
        return node("Ask Jev", "n8n-nodes-base.httpRequest", [440, 300], params, 4.2)
    params |= {"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"}
    return node("Ask Jev", "n8n-nodes-base.httpRequest", [440, 300], params, 4.2,
                credentials={"httpHeaderAuth": {"id": "", "name": "OpenRouter (Authorization: Bearer …)"}})


def flatten():
    return node("Verdict", "n8n-nodes-base.set", [660, 300], {
        "assignments": {"assignments": [
            {"id": "c", "name": "category", "value": "={{ $json.answers.category.choice }}", "type": "string"},
            {"id": "f", "name": "confidence", "value": "={{ $json.answers.category.confidence }}", "type": "number"},
            {"id": "m", "name": "message", "value": "={{ $('Message').item.json.message }}", "type": "string"},
        ]}, "options": {}}, 3.4)


def sure():
    return node("Sure?", "n8n-nodes-base.if", [880, 300], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                       "conditions": [{"id": "s", "leftValue": "={{ $json.confidence }}", "rightValue": 0.6,
                                       "operator": {"type": "number", "operation": "gte"}}], "combinator": "and"},
        "options": {}}, 2.2)


def route():
    rules = [{"outputKey": k, "renameOutput": True, "conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
        "conditions": [{"id": k, "leftValue": "={{ $json.category }}", "rightValue": k,
                        "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}} for k in CATS]
    return node("Route", "n8n-nodes-base.switch", [1100, 200], {"rules": {"values": rules}, "options": {}}, 3.2)


def ask_human():
    return node("Ask a human", "n8n-nodes-base.noOp", [1100, 420], {})


def build(test: bool):
    if test:
        trigger = node("Start", "n8n-nodes-base.manualTrigger", [0, 300], {})
        msg = node("Message", "n8n-nodes-base.set", [220, 300], {"assignments": {"assignments": [
            {"id": "ch", "name": "channel", "value": "#devops", "type": "string"},
            {"id": "ms", "name": "message", "value": "deploy to staging has been stuck on 'waiting for runner' for 40 min", "type": "string"},
        ]}, "options": {}}, 3.4)
    else:
        trigger = node("Mattermost webhook", "n8n-nodes-base.webhook", [0, 300], {"httpMethod": "POST", "path": "jev-router", "options": {}}, 2,
                       webhookId="jev-router")
        msg = node("Message", "n8n-nodes-base.set", [220, 300], {"assignments": {"assignments": [
            {"id": "ch", "name": "channel", "value": "={{ $json.body.channel_name }}", "type": "string"},
            {"id": "ms", "name": "message", "value": "={{ $json.body.text }}", "type": "string"},
        ]}, "options": {}}, 3.4)
    nodes = [trigger, msg, jev_node(auth_header=test), flatten(), sure(), route(), ask_human()]
    conn = {
        trigger["name"]: {"main": [[{"node": "Message", "type": "main", "index": 0}]]},
        "Message": {"main": [[{"node": "Ask Jev", "type": "main", "index": 0}]]},
        "Ask Jev": {"main": [[{"node": "Verdict", "type": "main", "index": 0}]]},
        "Verdict": {"main": [[{"node": "Sure?", "type": "main", "index": 0}]]},
        "Sure?": {"main": [[{"node": "Route", "type": "main", "index": 0}], [{"node": "Ask a human", "type": "main", "index": 0}]]},
    }
    wf = {"name": "Route DevOps requests with Jev" + (" (smoke test)" if test else ""), "nodes": nodes, "connections": conn,
          "settings": {"executionOrder": "v1"}, "active": False}
    if test:
        wf["id"] = "jevSmokeTest01"
    return wf


if __name__ == "__main__":
    out = HERE / "n8n"
    out.mkdir(exist_ok=True)
    (out / "jev-router.json").write_text(json.dumps(build(False), indent=1))
    (out / "jev-router.test.json").write_text(json.dumps(build(True), indent=1))
    print("wrote", *(p.name for p in out.glob("*.json")))
