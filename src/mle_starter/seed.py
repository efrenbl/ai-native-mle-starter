"""Seed state for the live demo: synthetic data plus three MLflow runs.

    make seed

  - v1.baseline           logistic regression                  (passes the contract)
  - v1.lgbm_monotonic     LightGBM with monotone constraints   (passes, better metrics)
  - v1.lgbm_missing_tags  LightGBM that "forgets" two tags     (FAILED: breaks the contract)

Idempotent: data is regenerated only when missing, and an experiment is skipped
when a run with its run name already exists.
"""

from __future__ import annotations

import json
import sys

from mlflow.tracking import MlflowClient

from mle_starter import datagen
from mle_starter.standard import experiment_name_for, load_standard, repo_root, run_name_for
from mle_starter.train import ContractViolation, lakehouse_dir, train

SEED_EXPERIMENTS = [
    ("model_versions/v1/baseline", True),
    ("model_versions/v1/lgbm_monotonic", True),
    ("model_versions/v1/lgbm_missing_tags", False),  # expected to fail the contract
]


def main() -> int:
    lh = lakehouse_dir()
    if (lh / "_manifest.json").is_file():
        print(f"lakehouse: already present ({json.loads((lh / '_manifest.json').read_text())['snapshot_id']})")
    else:
        m = datagen.generate(lh)
        print(f"lakehouse: generated {m['rows']} rows, snapshot {m['snapshot_id']}")

    std = load_standard()
    client = MlflowClient()
    summary = []
    for rel, should_pass in SEED_EXPERIMENTS:
        mv, eid = rel.split("/")[-2:]
        run_name = run_name_for(std, mv, eid)
        exp = client.get_experiment_by_name(experiment_name_for(std, "credit_default"))
        if exp is not None:
            existing = client.search_runs([exp.experiment_id], filter_string=f"attributes.run_name = '{run_name}'")
            if existing:
                summary.append((run_name, existing[0].info.run_id, existing[0].info.status, "skipped (exists)"))
                continue
        try:
            res = train(repo_root() / rel)
            summary.append((run_name, res.run_id, "FINISHED", f"roc_auc={res.metrics['roc_auc']:.4f}"))
            if not should_pass:
                print(f"ERROR: {run_name} was expected to fail the contract but passed", file=sys.stderr)
                return 1
        except ContractViolation as err:
            if should_pass:
                print(f"ERROR: {run_name} unexpectedly failed: {err.report}", file=sys.stderr)
                return 1
            summary.append((run_name, err.run_id, "FAILED", f"contract: missing={err.report['missing']}"))

    print("\nseeded runs:")
    for row in summary:
        print("  {:<24} {}  {:<9} {}".format(*row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
