"""The training entrypoint. The only code path that writes runs to MLflow.

    python -m mle_starter.train model_versions/v1/baseline      (or: make train EXP=...)

Steps:
  1. Validate the experiment folder and config against standard/standard.yaml.
  2. Load the features table from the lakehouse (read-only).
  3. Start an MLflow run in the experiment for the model type, named <model_version>.<experiment_id>.
  4. Log the contract tags, params and metrics.
  5. CHECK, DON'T TRUST: read the run back from the tracking server and verify
     the tag contract. If it fails, mark the run FAILED and exit non-zero.
  6. Only a passing run logs its model and registers a new model version.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from mle_starter.lakehouse import connect_readonly
from mle_starter.standard import (
    Experiment,
    StandardError,
    check_tags,
    experiment_name_for,
    load_experiment,
    load_standard,
    repo_root,
    run_name_for,
)

# Models are saved with skops (no arbitrary pickle on load). These are the only
# non-default types our supported estimators need; anything else fails loudly.
SKOPS_TRUSTED_TYPES = [
    "numpy.dtype",
    "collections.OrderedDict",
    "lightgbm.basic.Booster",
    "lightgbm.sklearn.LGBMClassifier",
]


class ContractViolation(RuntimeError):
    def __init__(self, run_id: str, report: dict[str, Any]):
        self.run_id = run_id
        self.report = report
        super().__init__(f"run {run_id} failed the tag contract: {json.dumps(report)}")


@dataclass
class TrainResult:
    run_id: str
    run_name: str
    metrics: dict[str, float]
    registered_version: str | None


def lakehouse_dir() -> Path:
    return Path(os.environ.get("LAKEHOUSE_DIR", repo_root() / "lakehouse"))


def load_features(cols: list[str], target: str) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    lh = lakehouse_dir()
    manifest = json.loads((lh / "_manifest.json").read_text())
    con = connect_readonly(lh)
    try:
        select = ", ".join(f'"{c}"' for c in [*cols, target, "split"])
        df = con.execute(f"SELECT {select} FROM features ORDER BY applicant_id").df()
    finally:
        con.close()
    return df[df["split"] == "train"], df[df["split"] == "test"], manifest["snapshot_id"]


def build_model(exp: Experiment, X: pd.DataFrame) -> Pipeline:
    m = exp.config["model"]
    params = dict(m.get("params") or {})
    cat = [c for c in X.columns if X[c].dtype == object or str(X[c].dtype) in ("category", "string", "str")]
    num = [c for c in X.columns if c not in cat]
    n_cat_out = sum(X[c].nunique() for c in cat)  # one-hot columns, after the numeric ones
    if m["estimator"] == "logistic_regression":
        from sklearn.linear_model import LogisticRegression

        clf = LogisticRegression(**params)
        num_pipe = Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    elif m["estimator"] == "random_forest":
        from sklearn.ensemble import RandomForestClassifier

        clf = RandomForestClassifier(**params)
        num_pipe = Pipeline([("impute", SimpleImputer(strategy="median"))])
    elif m["estimator"] == "hist_gradient_boosting":
        from sklearn.ensemble import HistGradientBoostingClassifier

        mono = params.pop("monotonic_constraints", None) or {}
        if mono:
            params["monotonic_cst"] = [int(mono.get(c, 0)) for c in num] + [0] * n_cat_out
        clf = HistGradientBoostingClassifier(**params)
        num_pipe = "passthrough"
    elif m["estimator"] == "lgbm_classifier":
        from lightgbm import LGBMClassifier

        mono = params.pop("monotone_constraints", None) or {}
        params.setdefault("verbose", -1)
        if mono:
            # Constraints are declared by column name in config.yaml; LightGBM wants
            # one entry per input column after preprocessing (numeric first).
            params["monotone_constraints"] = [int(mono.get(c, 0)) for c in num] + [0] * n_cat_out
        clf = LGBMClassifier(**params)
        num_pipe = "passthrough"
    else:  # unreachable: load_experiment already rejected unsupported estimators
        raise StandardError([f"unsupported estimator {m['estimator']}"])
    pre = ColumnTransformer(
        [("num", num_pipe, num), ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat)]
    )
    return Pipeline([("pre", pre), ("clf", clf)])


def contract_tags(exp: Experiment, std: dict[str, Any], snapshot: str) -> dict[str, str]:
    tags = {
        "demo.model_type": exp.model_type,
        "demo.model_version": exp.model_version,
        "demo.experiment_id": exp.experiment_id,
        "demo.standard_version": str(std["version"]),
        "demo.data_snapshot": snapshot,
        "demo.lib": exp.lib,
    }
    # demo_fault exists ONLY so `make seed` can produce one broken run for the
    # review skill to catch. Never use it in a real experiment.
    fault = exp.config.get("demo_fault") or {}
    for key in fault.get("drop_tags", []):
        tags.pop(key, None)
    tags.update({k: str(v) for k, v in (fault.get("override_tags") or {}).items()})
    return tags


def train(exp_path: str | Path) -> TrainResult:
    std = load_standard()
    exp = load_experiment(exp_path, std)
    data = exp.config["data"]
    target = std["model_types"][exp.model_type]["target"]
    train_df, test_df, snapshot = load_features(data["features"], target)
    X_train, y_train = train_df[data["features"]], train_df[target].to_numpy()
    X_test, y_test = test_df[data["features"]], test_df[target].to_numpy()

    mlflow.set_experiment(experiment_name_for(std, exp.model_type))
    run_name = run_name_for(std, exp.model_version, exp.experiment_id)
    client = MlflowClient()

    with mlflow.start_run(run_name=run_name) as run:
        run_id = run.info.run_id
        mlflow.set_tags(contract_tags(exp, std, snapshot))
        mlflow.set_tag("mlflow.note.content", exp.config.get("description", ""))
        mlflow.log_params(
            {
                "estimator": exp.config["model"]["estimator"],
                "n_features": len(data["features"]),
                "features": ",".join(data["features"]),
                **{f"model.{k}": v for k, v in (exp.config["model"].get("params") or {}).items()},
            }
        )
        model = build_model(exp, X_train)
        model.fit(X_train, y_train)
        proba = np.clip(model.predict_proba(X_test)[:, 1], 1e-6, 1 - 1e-6)
        metrics = {
            "roc_auc": float(roc_auc_score(y_test, proba)),
            "pr_auc": float(average_precision_score(y_test, proba)),
            "log_loss": float(log_loss(y_test, proba)),
            "brier": float(brier_score_loss(y_test, proba)),
            "train_rows": float(len(y_train)),
            "test_rows": float(len(y_test)),
            "test_positive_rate": float(y_test.mean()),
        }
        mlflow.log_metrics(metrics)

        # Check, don't trust: read the run back from the server.
        logged = client.get_run(run_id)
        experiment = client.get_experiment(logged.info.experiment_id)
        report = check_tags(logged.data.tags, std, run_name=logged.info.run_name, experiment_name=experiment.name)
        missing_metrics = [m for m in std["tracking"]["required_metrics"] if m not in logged.data.metrics]
        if missing_metrics:
            report.ok = False
            report.invalid.append(
                {"key": "metrics", "value": ",".join(missing_metrics), "reason": "required metrics not logged"}
            )
        if not report.ok:
            mlflow.set_tag("demo.contract_status", "failed")
            mlflow.end_run(status="FAILED")
            raise ContractViolation(run_id, report.to_dict())

        mlflow.set_tag("demo.contract_status", "passed")
        info = mlflow.sklearn.log_model(
            model,
            name="model",
            registered_model_name=std["model_types"][exp.model_type]["registered_model"],
            input_example=X_test.head(5),
            serialization_format="skops",
            skops_trusted_types=SKOPS_TRUSTED_TYPES,
            pip_requirements=["scikit-learn==1.9.1", "lightgbm==4.7.0", "pandas==3.0.6", "skops==0.16.0"],
        )
        version = getattr(info, "registered_model_version", None)
    return TrainResult(
        run_id=run_id, run_name=run_name, metrics=metrics, registered_version=str(version) if version else None
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train one experiment folder under the standard.")
    ap.add_argument("experiment", help="path like model_versions/v1/baseline")
    args = ap.parse_args(argv)
    try:
        res = train(args.experiment)
    except StandardError as err:
        print("REJECTED before training: the experiment does not follow the standard:", file=sys.stderr)
        for p in err.problems:
            print(f"  - {p}", file=sys.stderr)
        return 2
    except ContractViolation as err:
        print(f"RUN FAILED: {err.run_id} did not log the required tag contract.", file=sys.stderr)
        print(json.dumps(err.report, indent=2), file=sys.stderr)
        return 3
    print(json.dumps({"status": "passed", **res.__dict__}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
