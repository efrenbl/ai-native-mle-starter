"""standards-mcp: exposes the repo's ML standard, MLflow runs and the lakehouse to an agent.

Every tool is READ-ONLY. There is no tool that logs, tags, registers, promotes or
deletes anything, and none that writes to the lakehouse. Writes go through
`make train` / `make promote`, which a human (or the agent, behind a permission
prompt) runs explicitly.

Run it:
    python -m standards_mcp.server                 # streamable HTTP on 0.0.0.0:8765/mcp
    python -m standards_mcp.server --transport stdio
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from mle_starter import lakehouse
from mle_starter.standard import check_tags, list_local_experiments, load_standard, repo_root

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

mcp = FastMCP(
    "standards-mcp",
    instructions=(
        "Read-only access to this repo's ML standard (standard/standard.yaml), its MLflow runs, "
        "and the synthetic parquet lakehouse. Call get_standard first to learn the tag contract. "
        "Nothing here can write; training is `make train EXP=...`, promotion is `make promote ...`."
    ),
    host=os.environ.get("MCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("MCP_PORT", "8765")),
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["localhost:*", "127.0.0.1:*", "[::1]:*", "standards-mcp:*"],
        allowed_origins=["http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*"],
    ),
)


def _lakehouse_dir() -> Path:
    return Path(os.environ.get("LAKEHOUSE_DIR", repo_root() / "lakehouse"))


def _client() -> MlflowClient:
    return MlflowClient()


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, **extra}}


def _resolve_run(client: MlflowClient, run: str):
    """Accept a 32-char run id or a run name like `v1.baseline` (latest run with that name wins)."""
    std = load_standard()
    run = run.strip()
    if len(run) == 32 and all(c in "0123456789abcdef" for c in run):
        try:
            return client.get_run(run)
        except MlflowException:
            pass
    exp_ids = [e.experiment_id for e in client.search_experiments()]
    model_types = list(std["model_types"])
    if not exp_ids:
        raise LookupError(f"no MLflow experiments found; run `make seed` (model types: {model_types})")
    found = client.search_runs(
        exp_ids,
        filter_string=f"attributes.run_name = '{run.replace(chr(39), '')}'",
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )
    if not found:
        raise LookupError(f"no run with id or run name {run!r}; use list_experiments to see what exists")
    return found[0]


def _run_summary(client: MlflowClient, r, std: dict[str, Any], exp_names: dict[str, str]) -> dict[str, Any]:
    contract = check_tags(
        r.data.tags, std, run_name=r.info.run_name, experiment_name=exp_names.get(r.info.experiment_id)
    )
    return {
        "run_id": r.info.run_id,
        "run_name": r.info.run_name,
        "experiment": exp_names.get(r.info.experiment_id),
        "status": r.info.status,
        "start_time_ms": r.info.start_time,
        "primary_metric": {k: v for k, v in r.data.metrics.items() if k in ("roc_auc", "pr_auc")},
        "contract_ok": contract.ok,
        "contract_missing": contract.missing,
    }


@mcp.tool(annotations=READ_ONLY)
def get_standard() -> dict[str, Any]:
    """Return the repo's ML standard (standard/standard.yaml) as JSON: version, folder layout,
    supported libraries and estimators, MLflow experiment/run naming, the required `demo.*`
    tag contract, allowed registry aliases and lakehouse tables. Call this before scaffolding,
    reviewing or comparing experiments. Read-only."""
    try:
        std = load_standard()
    except Exception as err:  # noqa: BLE001
        return _error("standard_unreadable", str(err))
    return {"ok": True, "standard": std}


@mcp.tool(annotations=READ_ONLY)
def list_experiments(
    model_type: Annotated[
        str | None, Field(description="Filter to one model type, e.g. 'credit_default'. Omit for all.")
    ] = None,
    max_runs: Annotated[
        int, Field(ge=1, le=200, description="Max runs listed per MLflow experiment (newest first).")
    ] = 50,
) -> dict[str, Any]:
    """List experiments two ways and line them up: (1) local experiment folders under
    model_versions/<model_version>/<experiment_id>/ with any layout/config problems, and
    (2) MLflow experiments (one per model type) with their runs: run_id, run_name, status,
    roc_auc/pr_auc and whether each run passes the tag contract. Read-only."""
    try:
        std = load_standard()
        local = list_local_experiments(std)
        client = _client()
        experiments = client.search_experiments()
        out = []
        for e in experiments:
            if e.name == "Default" or (model_type and e.name != model_type):
                continue
            runs = client.search_runs([e.experiment_id], order_by=["attributes.start_time DESC"], max_results=max_runs)
            names = {e.experiment_id: e.name}
            out.append(
                {
                    "experiment_id": e.experiment_id,
                    "name": e.name,
                    "is_model_type": e.name in std["model_types"],
                    "runs": [_run_summary(client, r, std, names) for r in runs],
                }
            )
    except MlflowException as err:
        return _error("mlflow_error", str(err), hint="is the mlflow service up? try `make doctor`")
    except Exception as err:  # noqa: BLE001
        return _error("unexpected", f"{type(err).__name__}: {err}")
    return {"ok": True, "standard_version": std["version"], "local_experiments": local, "mlflow_experiments": out}


@mcp.tool(annotations=READ_ONLY)
def get_run(
    run: Annotated[str, Field(description="MLflow run id (32 hex chars) or run name like 'v1.baseline'.")],
) -> dict[str, Any]:
    """Return one MLflow run in full: ids, status, start/end time, params, metrics, tags,
    artifact URI and any registered model versions created from it. Read-only."""
    try:
        client = _client()
        r = _resolve_run(client, run)
        exp = client.get_experiment(r.info.experiment_id)
        versions = [
            {"name": v.name, "version": v.version, "aliases": list(getattr(v, "aliases", []) or [])}
            for v in client.search_model_versions(f"run_id='{r.info.run_id}'")
        ]
    except LookupError as err:
        return _error("run_not_found", str(err))
    except MlflowException as err:
        return _error("mlflow_error", str(err), hint="is the mlflow service up? try `make doctor`")
    return {
        "ok": True,
        "run": {
            "run_id": r.info.run_id,
            "run_name": r.info.run_name,
            "experiment": exp.name,
            "status": r.info.status,
            "start_time_ms": r.info.start_time,
            "end_time_ms": r.info.end_time,
            "params": dict(r.data.params),
            "metrics": dict(r.data.metrics),
            "tags": {k: v for k, v in r.data.tags.items() if not k.startswith("mlflow.log-model")},
            "artifact_uri": r.info.artifact_uri,
            "registered_versions": versions,
        },
    }


@mcp.tool(annotations=READ_ONLY)
def compare_runs(
    runs: Annotated[list[str], Field(min_length=1, max_length=10, description="Run ids or run names to compare.")],
    baseline: Annotated[str, Field(description="Run id or run name of the baseline, e.g. 'v1.baseline'.")],
    metrics: Annotated[
        list[str] | None, Field(description="Metric names to compare. Default: the standard's required_metrics.")
    ] = None,
) -> dict[str, Any]:
    """Put runs side by side with a baseline: each metric's value per run plus the delta
    (run - baseline) and relative delta. Lower-is-better metrics (log_loss, brier) are flagged
    so `improved` is correct for them. Also reports each run's contract status, because a
    comparison against a run that breaks the standard is not trustworthy. Read-only."""
    lower_is_better = {"log_loss", "brier"}
    try:
        std = load_standard()
        client = _client()
        base = _resolve_run(client, baseline)
        resolved = [_resolve_run(client, r) for r in runs]
        names = {e.experiment_id: e.name for e in client.search_experiments()}
    except LookupError as err:
        return _error("run_not_found", str(err))
    except MlflowException as err:
        return _error("mlflow_error", str(err), hint="is the mlflow service up? try `make doctor`")
    wanted = metrics or std["tracking"]["required_metrics"]
    rows = []
    for r in resolved:
        deltas = {}
        for m in wanted:
            v, b = r.data.metrics.get(m), base.data.metrics.get(m)
            if v is None or b is None:
                deltas[m] = {"value": v, "baseline": b, "delta": None, "note": "metric missing"}
                continue
            d = v - b
            deltas[m] = {
                "value": v,
                "baseline": b,
                "delta": d,
                "relative_delta": (d / b) if b else None,
                "improved": (d < 0) if m in lower_is_better else (d > 0),
            }
        summary = _run_summary(client, r, std, names)
        rows.append({"run_id": r.info.run_id, "run_name": r.info.run_name, "status": r.info.status,
                     "contract_ok": summary["contract_ok"], "contract_missing": summary["contract_missing"],
                     "metrics": deltas})  # fmt: skip
    base_summary = _run_summary(client, base, std, names)
    return {
        "ok": True,
        "baseline": {
            "run_id": base.info.run_id,
            "run_name": base.info.run_name,
            "contract_ok": base_summary["contract_ok"],
        },
        "metrics_compared": wanted,
        "lower_is_better": sorted(lower_is_better & set(wanted)),
        "runs": rows,
    }


@mcp.tool(annotations=READ_ONLY)
def check_run_contract(
    run: Annotated[str, Field(description="MLflow run id (32 hex chars) or run name like 'v1.baseline'.")],
) -> dict[str, Any]:
    """Check one MLflow run against the standard's tag contract. Returns `contract.ok`, the
    required tags that are `missing`, the ones that are `invalid` (with value and reason),
    and checks that the run name and experiment name follow the naming rules. Read-only."""
    try:
        std = load_standard()
        client = _client()
        r = _resolve_run(client, run)
        exp = client.get_experiment(r.info.experiment_id)
    except LookupError as err:
        return _error("run_not_found", str(err))
    except MlflowException as err:
        return _error("mlflow_error", str(err), hint="is the mlflow service up? try `make doctor`")
    report = check_tags(r.data.tags, std, run_name=r.info.run_name, experiment_name=exp.name)
    return {
        "ok": True,
        "run_id": r.info.run_id,
        "run_name": r.info.run_name,
        "status": r.info.status,
        "contract": report.to_dict(),
        "present_tags": {k: r.data.tags[k] for k in report.checked if k in r.data.tags},
    }


@mcp.tool(annotations=READ_ONLY)
def query_lakehouse(
    sql: Annotated[
        str,
        Field(
            description=(
                "One read-only DuckDB query (SELECT/WITH/FROM/DESCRIBE/SUMMARIZE) over views `raw` and `features`."
            )
        ),
    ],
    max_rows: Annotated[
        int, Field(ge=1, le=500, description="Rows to return; capped by the standard's query_row_cap.")
    ] = 50,
) -> dict[str, Any]:
    """Run one read-only SQL query with DuckDB over the synthetic parquet lakehouse.
    Views: `raw` (one row per synthetic application, partitioned by application_month) and
    `features` (model features + default_12m label, partitioned by split=train|test).
    Write statements (INSERT, COPY, ATTACH, DROP, CREATE, ...) and multiple statements are
    rejected in code, file access is limited to the lakehouse, and results are row-capped.
    Returns columns, rows, row_count and truncated."""
    try:
        cap = int(load_standard()["lakehouse"]["query_row_cap"])
        result = lakehouse.run_query(_lakehouse_dir(), sql, max_rows, cap)
    except lakehouse.SqlGuardError as err:
        return _error("query_rejected", str(err))
    except FileNotFoundError as err:
        return _error("lakehouse_missing", str(err))
    return {"ok": True, **result}


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "standards-mcp"})


def main() -> None:
    ap = argparse.ArgumentParser(description="standards-mcp server")
    ap.add_argument("--transport", choices=["streamable-http", "stdio"], default="streamable-http")
    args = ap.parse_args()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
