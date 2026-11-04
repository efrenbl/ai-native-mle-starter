---
name: promote-model
description: Sets an MLflow registry alias (challenger or champion) on the model version produced by one run, after a passing review and an explicit confirmation from the user. Use only when the user explicitly invokes /promote-model. Never use it on your own initiative, never to fix a failing run, and not for reviews (review-experiment).
disable-model-invocation: true
---

# Promote a model (explicit-only)

This skill WRITES to the model registry, so it is explicit-only: `disable-model-invocation: true` keeps it out
of automatic invocation, and `.claude/settings.json` puts `make promote` behind a permission prompt.
The MCP server has no write tools; the only write path is `make promote`.

## MCP tools
- `mcp__standards-mcp__check_run_contract` — the gate: the run must pass the tag contract.
- `mcp__standards-mcp__get_run` — status, metrics and the registered model version of the run.
- `mcp__standards-mcp__compare_runs` — the evidence against the baseline.
- `mcp__standards-mcp__get_standard` — `registry.allowed_aliases`.

## Procedure
1. Identify the run (id or run name) and the alias. The alias must be in `registry.allowed_aliases`;
   default to `challenger`. `champion` only if the user says so.
2. Gate, in order. Stop at the first failure and explain why:
   a. `check_run_contract` → `contract.ok` must be true.
   b. `get_run` → `status` must be `FINISHED` and `registered_versions` must not be empty.
   c. `compare_runs` against `<model_version>.baseline` → show the deltas.
3. Dry run: `make promote RUN=<run_id> ALIAS=<alias>` and show the output (what would change, previous version).
4. Ask the user to confirm, quoting run_id, model version and alias. Wait for an explicit "yes".
5. Only then: `make promote RUN=<run_id> ALIAS=<alias> CONFIRM=yes`. Claude Code will show a permission
   prompt; the user approves it there too.
6. Report the result exactly as the command printed it.

## Rules
- Never promote a run that fails the contract, even if asked; the script refuses it anyway.
- Never call `make promote ... CONFIRM=yes` without a confirmation in the current conversation turn.
