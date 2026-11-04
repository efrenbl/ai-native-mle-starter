"""Deterministic synthetic credit-risk data, written as partitioned parquet.

Everything here is invented. Applicant ids start with SYN-, every row carries
is_synthetic = true, and amounts are in "synthetic currency units" (SCU).

    python -m mle_starter.datagen [--rows 50000] [--seed 42] [--out lakehouse]

Same seed + same pinned library versions = byte-identical files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from mle_starter.standard import repo_root

GENERATOR_VERSION = 1
REGIONS = ["north", "south", "east", "west", "central"]
HOME = ["rent", "mortgage", "own"]
PURPOSES = ["debt_consolidation", "home_improvement", "education", "vehicle", "medical", "other"]
TEST_FROM_MONTH = "2024-10"  # out-of-time split: Oct-Dec are the test set


def snapshot_id(seed: int, rows: int) -> str:
    return f"synth-g{GENERATOR_VERSION}-s{seed}-n{rows}"


def make_raw(rows: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = rows
    day = rng.integers(0, 366, n)  # 2024 is a leap year
    date = pd.Timestamp("2024-01-01") + pd.to_timedelta(day, unit="D")
    age = np.clip(rng.normal(41, 12, n), 18, 80).round().astype(int)
    employment = np.minimum(rng.exponential(6.0, n), age - 18).clip(0, 45).round(1)
    income = (rng.lognormal(10.8, 0.5, n) * (1 + 0.01 * employment)).round(2)
    loan = np.clip(rng.lognormal(9.3, 0.6, n), 500, 60_000).round(2)
    term = rng.choice([12, 24, 36, 48, 60], n)
    history = np.clip(rng.normal((age - 18) * 9, 30), 0, None).round().astype(int)
    open_acc = rng.poisson(4, n)
    delinq = rng.poisson(0.3, n)
    dti = (rng.beta(2, 5, n) * 0.8).clip(0, 0.95).round(4)
    util = rng.beta(2, 3, n).round(4)
    home = rng.choice(HOME, n, p=[0.45, 0.40, 0.15])
    purpose = rng.choice(PURPOSES, n, p=[0.35, 0.15, 0.10, 0.15, 0.10, 0.15])
    region = rng.choice(REGIONS, n)

    lti = loan / income
    z = (
        -4.2
        + 3.0 * dti
        + 1.0 * util
        + 0.7 * delinq
        + 1.4 * lti
        - 0.04 * employment
        - 0.03 * history / 12
        + 0.35 * (purpose == "medical")
        + 0.25 * (home == "rent")
        + 0.006 * (term - 36)
        # Non-linear structure a linear model cannot see (so boosting has room to win):
        + 2.2 * ((util > 0.65) & (dti > 0.30))  # interaction: stretched on both fronts
        + 1.2 * (util > 0.85)  # threshold effect near the credit limit
        + 0.9 * ((age < 25) | (age > 68))  # U-shaped age effect
    )
    p = 1.0 / (1.0 + np.exp(-z))
    label = (rng.random(n) < p).astype(int)

    employment = employment.astype(float)
    employment[rng.random(n) < 0.02] = np.nan  # a little realistic missingness

    return pd.DataFrame(
        {
            "applicant_id": [f"SYN-{i:06d}" for i in range(n)],
            "application_date": date.date,
            "application_month": date.strftime("%Y-%m"),
            "region": region,
            "age": age,
            "employment_years": employment,
            "annual_income_scu": income,
            "home_ownership": home,
            "loan_purpose": purpose,
            "loan_amount_scu": loan,
            "loan_term_months": term,
            "credit_history_months": history,
            "num_open_accounts": open_acc,
            "num_delinquencies_2y": delinq,
            "debt_to_income": dti,
            "credit_utilization": util,
            "default_12m": label,
            "is_synthetic": True,
        }
    )


FEATURES_SQL = f"""
SELECT
    applicant_id,
    application_month,
    CASE WHEN application_month >= '{TEST_FROM_MONTH}' THEN 'test' ELSE 'train' END AS split,
    region,
    age,
    employment_years,
    round(ln(annual_income_scu), 6)                        AS income_log,
    loan_amount_scu,
    round(loan_amount_scu / annual_income_scu, 6)          AS loan_to_income,
    loan_term_months,
    round(credit_history_months / 12.0, 4)                 AS credit_history_years,
    num_open_accounts,
    num_delinquencies_2y,
    debt_to_income,
    credit_utilization,
    home_ownership,
    loan_purpose,
    default_12m,
    is_synthetic
FROM raw
ORDER BY applicant_id
"""


def _write(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="snappy")


def generate(out: Path, rows: int = 50_000, seed: int = 42) -> dict:
    out = Path(out)
    for sub in ("raw", "features"):
        if (out / sub).exists():
            shutil.rmtree(out / sub)
    raw = make_raw(rows, seed)

    files: list[Path] = []
    for month, part in raw.groupby("application_month", sort=True):
        path = out / "raw" / f"application_month={month}" / "part-0.parquet"
        tbl = pa.Table.from_pandas(
            part.drop(columns=["application_month"]).reset_index(drop=True), preserve_index=False
        )
        _write(tbl, path)
        files.append(path)

    con = duckdb.connect()
    con.register("raw", raw)
    features = con.execute(FEATURES_SQL).df()
    con.close()
    for split, part in features.groupby("split", sort=True):
        path = out / "features" / f"split={split}" / "part-0.parquet"
        tbl = pa.Table.from_pandas(part.drop(columns=["split"]).reset_index(drop=True), preserve_index=False)
        _write(tbl, path)
        files.append(path)

    manifest = {
        "snapshot_id": snapshot_id(seed, rows),
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "rows": rows,
        "synthetic": True,
        "test_from_month": TEST_FROM_MONTH,
        "tables": {"raw": "raw/application_month=*/part-0.parquet", "features": "features/split=*/part-0.parquet"},
        "files": {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},
    }
    (out / "_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=50_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=repo_root() / "lakehouse")
    args = ap.parse_args()
    m = generate(args.out, args.rows, args.seed)
    print(f"wrote {len(m['files'])} parquet files, snapshot {m['snapshot_id']} -> {args.out}")


if __name__ == "__main__":
    main()
