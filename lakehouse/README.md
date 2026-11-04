# lakehouse/ — synthetic parquet, queried with DuckDB

A local stand-in for a lakehouse: partitioned parquet files plus a manifest. It is
**generated** by `make seed` (`python -m mle_starter.datagen`) and git-ignored.
Same seed + same pinned library versions = byte-identical files (a test checks it).

**Everything here is invented.** No real people, lenders or records. Applicant ids
start with `SYN-`, every row has `is_synthetic = true`, money is in synthetic currency
units (SCU), and the label comes from a known formula with noise.

```
lakehouse/
├── _manifest.json                         snapshot_id, seed, rows, sha256 per file
├── raw/application_month=2024-01/part-0.parquet  … 12 monthly partitions
└── features/split=train/part-0.parquet    Jan–Sep 2024 (37,468 rows)
    features/split=test/part-0.parquet     Oct–Dec 2024 (12,532 rows, out-of-time)
```

The snapshot id (`synth-g1-s42-n50000`) is what training logs as `demo.data_snapshot`.

## `raw` — one row per synthetic loan application (50,000 rows)

| column | type | notes |
|---|---|---|
| applicant_id | string | `SYN-000000` … `SYN-049999` |
| application_date | date | uniform over 2024 |
| application_month | string | partition key, `YYYY-MM` |
| region | string | north, south, east, west, central |
| age | int | 18–80 |
| employment_years | double | ~2 % missing |
| annual_income_scu | double | log-normal |
| home_ownership | string | rent, mortgage, own |
| loan_purpose | string | debt_consolidation, home_improvement, education, vehicle, medical, other |
| loan_amount_scu | double | 500–60,000 |
| loan_term_months | int | 12, 24, 36, 48, 60 |
| credit_history_months | int | |
| num_open_accounts | int | |
| num_delinquencies_2y | int | |
| debt_to_income | double | 0–0.95 |
| credit_utilization | double | 0–1 |
| default_12m | int | label: 1 = defaulted within 12 months (~8 %) |
| is_synthetic | bool | always true |

## `features` — model inputs + label (50,000 rows)

Derived from `raw` with DuckDB SQL (`FEATURES_SQL` in `src/mle_starter/datagen.py`).

| column | derivation |
|---|---|
| applicant_id, application_month | from raw |
| split | partition key: `test` from 2024-10, else `train` |
| region, age, employment_years, home_ownership, loan_purpose, loan_amount_scu, loan_term_months, num_open_accounts, num_delinquencies_2y, debt_to_income, credit_utilization | as in raw |
| income_log | `ln(annual_income_scu)` |
| loan_to_income | `loan_amount_scu / annual_income_scu` |
| credit_history_years | `credit_history_months / 12` |
| default_12m, is_synthetic | as in raw |

The label has non-linear structure on purpose (a utilisation × DTI interaction, a
threshold near the credit limit, a U-shaped age effect) so that boosting has room to
beat the logistic baseline.

## Query it

Through the agent: the `explore-data` skill → `query_lakehouse` MCP tool (read-only).
By hand: `docker compose --profile jobs run --rm trainer python -c "..."` or any DuckDB client:

```sql
SELECT loan_purpose, count(*) n, round(avg(default_12m), 4) default_rate
FROM read_parquet('lakehouse/features/split=*/part-*.parquet', hive_partitioning = true)
GROUP BY 1 ORDER BY 3 DESC;
```
