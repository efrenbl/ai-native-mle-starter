"""Shared fixtures: a throwaway lakehouse + sqlite MLflow store, seeded once per session."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def std():
    from mle_starter.standard import load_standard

    return load_standard(REPO / "standard" / "standard.yaml")


@pytest.fixture(scope="session")
def lakehouse_dir(tmp_path_factory) -> Path:
    from mle_starter import datagen

    out = tmp_path_factory.mktemp("lakehouse")
    datagen.generate(out, rows=50_000, seed=42)
    os.environ["LAKEHOUSE_DIR"] = str(out)
    return out


@pytest.fixture(scope="session")
def seeded(lakehouse_dir, tmp_path_factory):
    """Run the real seed (3 experiments) against a sqlite tracking store."""
    import mlflow

    from mle_starter import seed

    store = tmp_path_factory.mktemp("mlflow")
    uri = f"sqlite:///{store / 'mlflow.db'}"
    os.environ["MLFLOW_TRACKING_URI"] = uri
    mlflow.set_tracking_uri(uri)
    # Keep artifacts out of the repo: pre-create the experiment with a tmp artifact location.
    mlflow.MlflowClient().create_experiment("credit_default", artifact_location=(store / "artifacts").as_uri())
    assert seed.main() == 0
    client = mlflow.MlflowClient()
    exp = client.get_experiment_by_name("credit_default")
    runs = {r.info.run_name: r for r in client.search_runs([exp.experiment_id])}
    return {"uri": uri, "runs": runs, "client": client}
