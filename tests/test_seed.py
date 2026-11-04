"""The synthetic data generator and the seeded demo runs."""

from __future__ import annotations

import json

import pyarrow.parquet as pq

from mle_starter import datagen, promote, seed


def test_generator_is_deterministic(tmp_path):
    a = datagen.generate(tmp_path / "a", rows=2_000, seed=7)
    b = datagen.generate(tmp_path / "b", rows=2_000, seed=7)
    c = datagen.generate(tmp_path / "c", rows=2_000, seed=8)
    assert a["files"] == b["files"]  # byte-identical parquet (sha256 per file)
    assert a["files"] != c["files"]
    assert a["snapshot_id"] == "synth-g1-s7-n2000"


def test_lakehouse_layout_and_schema(lakehouse_dir):
    manifest = json.loads((lakehouse_dir / "_manifest.json").read_text())
    assert manifest["synthetic"] is True and manifest["rows"] == 50_000
    raw_parts = sorted((lakehouse_dir / "raw").glob("application_month=*/part-0.parquet"))
    assert len(raw_parts) == 12
    feat = {p.parent.name for p in (lakehouse_dir / "features").glob("split=*/part-0.parquet")}
    assert feat == {"split=train", "split=test"}
    t = pq.read_table(raw_parts[0]).to_pandas()
    assert t["applicant_id"].str.startswith("SYN-").all()
    assert t["is_synthetic"].all()
    assert {"debt_to_income", "credit_utilization", "default_12m", "annual_income_scu"} <= set(t.columns)


def test_default_rate_is_plausible(lakehouse_dir):
    import pandas as pd

    df = pd.concat(pq.read_table(p).to_pandas() for p in (lakehouse_dir / "features").glob("split=*/*.parquet"))
    assert 0.05 < df["default_12m"].mean() < 0.30


def test_seed_logs_three_runs(seeded):
    runs = seeded["runs"]
    assert set(runs) == {"v1.baseline", "v1.lgbm_monotonic", "v1.lgbm_missing_tags"}
    assert runs["v1.baseline"].info.status == "FINISHED"
    assert runs["v1.lgbm_monotonic"].info.status == "FINISHED"
    assert runs["v1.lgbm_missing_tags"].info.status == "FAILED"


def test_better_variant_beats_baseline(seeded):
    runs = seeded["runs"]
    assert runs["v1.lgbm_monotonic"].data.metrics["roc_auc"] > runs["v1.baseline"].data.metrics["roc_auc"]


def test_broken_run_is_failed_and_flagged(seeded):
    broken = seeded["runs"]["v1.lgbm_missing_tags"]
    assert "demo.data_snapshot" not in broken.data.tags
    assert broken.data.tags["demo.standard_version"] == "0.9.0"
    assert broken.data.tags["demo.contract_status"] == "failed"


def test_only_passing_runs_register_a_model(seeded):
    client = seeded["client"]
    registered = {v.run_id for v in client.search_model_versions("name='credit_default'")}
    assert seeded["runs"]["v1.baseline"].info.run_id in registered
    assert seeded["runs"]["v1.lgbm_monotonic"].info.run_id in registered
    assert seeded["runs"]["v1.lgbm_missing_tags"].info.run_id not in registered


def test_seed_is_idempotent(seeded, capsys):
    assert seed.main() == 0
    assert capsys.readouterr().out.count("skipped (exists)") == 3


def test_promote_is_gated(seeded):
    good = seeded["runs"]["v1.lgbm_monotonic"].info.run_id
    bad = seeded["runs"]["v1.lgbm_missing_tags"].info.run_id
    assert promote.promote(bad, "challenger", confirm=True)["status"] == "refused"
    assert promote.promote(good, "production", confirm=True)["status"] == "refused"
    dry = promote.promote(good, "challenger", confirm=False)
    assert dry["status"] == "dry_run"
    with __import__("pytest").raises(Exception):  # dry run must not have set the alias
        seeded["client"].get_model_version_by_alias("credit_default", "challenger")
    done = promote.promote(good, "challenger", confirm=True)
    assert done["status"] == "promoted"
    assert seeded["client"].get_model_version_by_alias("credit_default", "challenger").run_id == good
