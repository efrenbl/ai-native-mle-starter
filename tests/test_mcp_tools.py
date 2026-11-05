"""Every standards-mcp tool, called through a real MCP client session (in-memory transport)."""

from __future__ import annotations

import json

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

TOOLS = {"get_standard", "list_experiments", "get_run", "compare_runs", "check_run_contract", "query_lakehouse"}


def call(tool: str, args: dict | None = None) -> dict:
    from standards_mcp.server import mcp

    async def _run():
        async with create_connected_server_and_client_session(mcp._mcp_server) as session:
            res = await session.call_tool(tool, args or {})
            assert not res.isError, res.content
            if res.structuredContent is not None:
                data = res.structuredContent
                return data.get("result", data) if set(data) == {"result"} else data
            return json.loads(res.content[0].text)

    return anyio.run(_run)


def list_tools():
    from standards_mcp.server import mcp

    async def _run():
        async with create_connected_server_and_client_session(mcp._mcp_server) as session:
            return (await session.list_tools()).tools

    return anyio.run(_run)


def test_exactly_the_read_only_tools_are_exposed():
    tools = list_tools()
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.annotations.readOnlyHint is True and t.annotations.destructiveHint is False
        assert len(t.description) > 80, f"{t.name} needs a precise description"
        assert t.inputSchema["type"] == "object"


def test_get_standard():
    out = call("get_standard")
    assert out["ok"] and out["standard"]["version"] == "1.0.0"
    assert len(out["standard"]["tag_contract"]) == 6


def test_list_experiments(seeded):
    out = call("list_experiments", {"model_type": "credit_default"})
    assert out["ok"]
    (exp,) = out["mlflow_experiments"]
    by_name = {r["run_name"]: r for r in exp["runs"]}
    assert by_name["v1.baseline"]["contract_ok"] is True
    assert by_name["v1.lgbm_missing_tags"]["contract_ok"] is False
    assert {e["experiment_id"] for e in out["local_experiments"]} >= {"baseline", "lgbm_monotonic"}


def test_get_run_by_name_and_id(seeded):
    by_name = call("get_run", {"run": "v1.baseline"})
    assert by_name["ok"] and by_name["run"]["metrics"]["roc_auc"] > 0.5
    run_id = by_name["run"]["run_id"]
    by_id = call("get_run", {"run": run_id})
    assert by_id["run"]["run_name"] == "v1.baseline"
    assert by_id["run"]["registered_versions"][0]["name"] == "credit_default"


def test_get_run_not_found_is_a_clear_error(seeded):
    out = call("get_run", {"run": "v9.nope"})
    assert out["ok"] is False and out["error"]["code"] == "run_not_found"


def test_compare_runs(seeded):
    out = call("compare_runs", {"runs": ["v1.lgbm_monotonic", "v1.lgbm_missing_tags"], "baseline": "v1.baseline"})
    assert out["ok"] and out["baseline"]["run_name"] == "v1.baseline"
    rows = {r["run_name"]: r for r in out["runs"]}
    auc = rows["v1.lgbm_monotonic"]["metrics"]["roc_auc"]
    assert auc["delta"] == pytest.approx(auc["value"] - auc["baseline"]) and auc["improved"] is True
    assert "log_loss" in out["lower_is_better"]
    assert rows["v1.lgbm_missing_tags"]["contract_ok"] is False


def test_check_run_contract(seeded):
    good = call("check_run_contract", {"run": "v1.lgbm_monotonic"})
    assert good["contract"]["ok"] is True
    bad = call("check_run_contract", {"run": "v1.lgbm_missing_tags"})
    assert bad["status"] == "FAILED"
    assert bad["contract"]["missing"] == ["demo.data_snapshot"]
    assert [i["key"] for i in bad["contract"]["invalid"]] == ["demo.standard_version"]


def test_query_lakehouse(seeded):
    out = call("query_lakehouse", {"sql": "SELECT count(*) AS n FROM raw"})
    assert out["ok"] and out["rows"] == [[50_000]]


@pytest.mark.parametrize(
    "sql",
    ["DROP VIEW raw", "INSERT INTO raw SELECT * FROM raw", "COPY raw TO '/tmp/x.csv'", "ATTACH '/tmp/x.db'"],
)
def test_query_lakehouse_rejects_writes(seeded, sql):
    out = call("query_lakehouse", {"sql": sql})
    assert out["ok"] is False and out["error"]["code"] == "query_rejected"


def test_query_lakehouse_validates_max_rows(seeded):
    from standards_mcp.server import mcp

    async def _run():
        async with create_connected_server_and_client_session(mcp._mcp_server) as session:
            return await session.call_tool("query_lakehouse", {"sql": "SELECT 1", "max_rows": 100_000})

    res = anyio.run(_run)
    assert res.isError  # typed parameter: le=500


def test_every_tool_call_writes_one_audit_line(seeded, caplog):
    import logging

    from standards_mcp.server import audit_log

    audit_log.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger=audit_log.name):
            call("check_run_contract", {"run": "v1.lgbm_missing_tags"})
            call("query_lakehouse", {"sql": "DROP VIEW features"})
    finally:
        audit_log.removeHandler(caplog.handler)
    lines = [r.getMessage() for r in caplog.records if r.name == audit_log.name]
    assert len(lines) == 2, lines
    assert lines[0].startswith('tool=check_run_contract args={"run":"v1.lgbm_missing_tags"} ok=true')
    assert lines[1].startswith("tool=query_lakehouse args=") and "ok=false error=query_rejected" in lines[1]
