---
name: review-experiment
description: Reviews MLflow runs of an experiment against the repo's ML standard and its baseline, and returns an evidence-backed report that cites run IDs, the tag-contract result and metric deltas. Use when the user asks to review, audit, check or validate an experiment or run, asks whether a run is ready to promote, or asks how a run compares with the baseline. Read-only - it never trains, tags, registers or promotes. Do not use to create experiments (scaffold-experiment) or to set registry aliases (promote-model).
---

# Review an experiment

Goal: a short report a reviewer can trust because every claim points at evidence from the MCP tools.
This skill is read-only. It writes nothing anywhere, and the report must not claim otherwise.

## MCP tools
- `mcp__standards-mcp__get_standard` — the tag contract and required metrics.
- `mcp__standards-mcp__list_experiments` — runs per experiment, status and contract summary.
- `mcp__standards-mcp__check_run_contract` — missing/invalid `demo.*` tags for one run.
- `mcp__standards-mcp__get_run` — params, metrics, tags and registered versions of one run.
- `mcp__standards-mcp__compare_runs` — metric deltas against a named baseline.

## Procedure
1. `get_standard` → note `version`, the `tag_contract` keys and `tracking.required_metrics`.
2. `list_experiments` → find the runs in scope (the run the user named, or every run of the experiment).
3. For EACH run in scope, call `check_run_contract`. Never infer contract status from a run's name or status.
4. Find the baseline: the experiment's `baseline_experiment_id` (usually `<model_version>.baseline`).
   Call `compare_runs` with the runs in scope and that baseline.
5. Write the report:

```
## Review: <experiment or run name>   (standard vX.Y.Z)
| run_id | run_name | status | contract | roc_auc Δ vs baseline | verdict |
Findings
- <run_id>: MISSING demo.xxx; INVALID demo.yyy=<value> (<reason>)      ← one line per problem
- <run_id>: roc_auc 0.xxx vs baseline 0.yyy (Δ +0.0zz); log_loss Δ ...
Verdict: ready / not ready for promotion, and the single next action.
```

## Rules
- Cite the full 32-character run_id for every finding.
- A run that fails the contract is "not ready", whatever its metrics. Say which tags to fix and that the
  fix is in the training code / config, followed by a new `make train` run. Do not suggest editing tags by hand.
- Report deltas with sign and direction (log_loss and brier: lower is better).
- If a tool returns `ok: false`, report the error and the hint; do not guess the missing data.
- Never say you set, wrote, fixed, tagged, registered or promoted anything.
