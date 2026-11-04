"""The tag-contract checker and the experiment layout rules."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mle_starter.standard import StandardError, check_tags, list_local_experiments, load_experiment

GOOD = {
    "demo.model_type": "credit_default",
    "demo.model_version": "v1",
    "demo.experiment_id": "baseline",
    "demo.standard_version": "1.0.0",
    "demo.data_snapshot": "synth-g1-s42-n50000",
    "demo.lib": "sklearn",
}


def test_good_tags_pass(std):
    r = check_tags(GOOD, std, run_name="v1.baseline", experiment_name="credit_default")
    assert r.ok and r.missing == [] and r.invalid == []
    assert r.checked == [t["key"] for t in std["tag_contract"]]


def test_contract_has_five_or_six_demo_tags(std):
    keys = [t["key"] for t in std["tag_contract"]]
    assert 5 <= len(keys) <= 6
    # MLflow tag keys: alphanumerics, underscores, dashes, periods, spaces, slashes.
    assert all(k.startswith("demo.") and all(c.isalnum() or c in "._-/ " for c in k) for k in keys)


@pytest.mark.parametrize("key", list(GOOD))
def test_each_missing_tag_is_reported(std, key):
    tags = {k: v for k, v in GOOD.items() if k != key}
    r = check_tags(tags, std)
    assert not r.ok and r.missing == [key]


def test_empty_value_counts_as_missing(std):
    r = check_tags({**GOOD, "demo.lib": "  "}, std)
    assert r.missing == ["demo.lib"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("demo.model_type", "fraud"),  # not a model type in the standard
        ("demo.model_version", "version1"),
        ("demo.experiment_id", "Bad-Name"),
        ("demo.standard_version", "0.9.0"),  # MAJOR mismatch
        ("demo.standard_version", "one"),
        ("demo.data_snapshot", "prod-table"),
        ("demo.lib", "xgboost"),  # unsupported library
    ],
)
def test_invalid_values_are_reported(std, key, value):
    r = check_tags({**GOOD, key: value}, std)
    assert not r.ok
    assert [i["key"] for i in r.invalid] == [key]
    assert r.invalid[0]["value"] == value and r.invalid[0]["reason"]


def test_same_major_minor_bump_is_accepted(std):
    assert check_tags({**GOOD, "demo.standard_version": "1.4.2"}, std).ok


def test_run_and_experiment_names_must_match_tags(std):
    r = check_tags(GOOD, std, run_name="baseline", experiment_name="Default")
    assert {i["key"] for i in r.invalid} == {"run_name", "experiment_name"}


def test_seed_experiments_are_valid(std):
    for eid in ("baseline", "lgbm_monotonic", "lgbm_missing_tags"):
        exp = load_experiment(f"model_versions/v1/{eid}", std)
        assert exp.model_version == "v1" and exp.experiment_id == eid


def test_template_is_not_runnable(std):
    with pytest.raises(StandardError, match="template"):
        load_experiment("model_versions/_TEMPLATE", std)


def _copy_repo_subset(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(Path(__file__).resolve().parents[1] / "model_versions", root / "model_versions")
    return root


@pytest.mark.parametrize(
    "mutate,needle",
    [
        (lambda c: c.replace("lib: sklearn", "lib: xgboost"), "not supported"),
        (lambda c: c.replace("estimator: logistic_regression", "estimator: svm"), "not supported"),
        (lambda c: c.replace("experiment_id: baseline", "experiment_id: other"), "!= folder"),
        (lambda c: c + "\nsurprise: true\n", "unknown keys"),
    ],
)
def test_bad_configs_are_rejected(std, tmp_path, mutate, needle):
    root = _copy_repo_subset(tmp_path)
    cfg = root / "model_versions/v1/baseline/config.yaml"
    cfg.write_text(mutate(cfg.read_text()))
    with pytest.raises(StandardError) as err:
        load_experiment(root / "model_versions/v1/baseline", std, root)
    assert any(needle in p for p in err.value.problems)


def test_bad_folder_names_are_rejected(std, tmp_path):
    root = _copy_repo_subset(tmp_path)
    shutil.copytree(root / "model_versions/v1/baseline", root / "model_versions/version1/Bad")
    with pytest.raises(StandardError) as err:
        load_experiment(root / "model_versions/version1/Bad", std, root)
    assert len(err.value.problems) == 2


def test_list_local_experiments(std):
    items = {i["experiment_id"]: i for i in list_local_experiments(std)}
    assert {"baseline", "lgbm_monotonic", "lgbm_missing_tags"} <= set(items)
    assert items["baseline"]["valid"] and items["baseline"]["run_name"] == "v1.baseline"
