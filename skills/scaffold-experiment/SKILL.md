---
name: scaffold-experiment
description: Creates a new experiment folder model_versions/<model_version>/<experiment_id>/ from the _TEMPLATE, with a config.yaml that follows the repo's ML standard. Use when the user wants to start, set up or create a new experiment, try a new model or new hyperparameters. Do not use to train or run an experiment (that is `make train`), to review results (review-experiment), or to edit standard/standard.yaml.
---

# Scaffold an experiment

Goal: a new, valid experiment folder in one step, ready for `make train`. Nothing is trained here.

## MCP tools
- `mcp__standards-mcp__get_standard` — layout rules, supported libraries/estimators, naming patterns.
- `mcp__standards-mcp__list_experiments` — which experiment ids already exist (local folders and MLflow).

## Procedure
1. Call `get_standard`. Note `layout.experiment_id_pattern`, `layout.model_version_pattern`, and
   `libraries` (only scikit-learn and LightGBM estimators listed there are allowed).
2. Call `list_experiments`. Pick an `experiment_id` that matches the pattern and is not taken.
   Default `model_version` is the highest existing one (e.g. `v1`); only start `v2` if the user asks.
3. Create the folder with the scaffolder (it copies `_TEMPLATE`, fills the names and validates):
   `make scaffold MV=<model_version> EXP=<experiment_id>`
4. Edit only `model_versions/<mv>/<id>/config.yaml` to express the user's hypothesis:
   - `description`: one sentence, the hypothesis being tested.
   - `model.lib` / `model.estimator`: one supported pair from the standard.
   - `model.params`: estimator parameters. For monotone constraints, LightGBM uses
     `monotone_constraints: {column: 1|-1}`; sklearn `hist_gradient_boosting` uses `monotonic_constraints`.
   - Keep `model_type`, `model_version`, `experiment_id` equal to the folder. Do not add new top-level keys.
5. Tell the user the exact next command: `make train EXP=model_versions/<mv>/<id>`.
   Do not run it unless the user asks; training writes to MLflow.

## Rules
- Never edit `standard/`, `lakehouse/`, or another experiment's folder.
- If the user asks for a library outside the standard (e.g. XGBoost, PyTorch), say it is outside
  the structured lane of standard vX.Y.Z and stop; changing that is a standard change done by a human.
