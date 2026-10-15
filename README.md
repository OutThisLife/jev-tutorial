# Jev for workflow gates

A tutorial and two sets of use cases for [TypeSafe Jev](https://docs.typesafe.ai/introduction), a model that returns calibrated probabilities instead of text.

- `index.html`: what Jev is, and a Jev-backed gate for a workflow runner (`judge.py`, `test_judge.py`)
- `cases.html`: workflow-gate decisions run against real NousResearch/hermes-agent issues, PRs and comments (`cases/`)
- `design.html`: n8n and design-system decisions (`design/`), including an importable n8n workflow at `design/n8n/jev-router.json`

Every number on the case pages is rebuilt from `*/results/*.json`:

```sh
export OPENROUTER_API_KEY=...
cd cases && python3 run.py && python3 build.py && cd ..
cd design && python3 run.py && python3 build.py
```
