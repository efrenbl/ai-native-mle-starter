"""Call every standards-mcp tool over streamable HTTP with the official MCP Python SDK client.

    uv run --with mcp==1.30.0 scripts/verify_mcp.py [http://localhost:8765/mcp]

Exits non-zero if a tool is missing, errors, or a write attempt is not rejected.
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/mcp"

CALLS = [
    ("get_standard", {}),
    ("list_experiments", {"model_type": "credit_default", "max_runs": 10}),
    ("get_run", {"run": "v1.baseline"}),
    ("compare_runs", {"runs": ["v1.lgbm_monotonic", "v1.lgbm_missing_tags"], "baseline": "v1.baseline"}),
    ("check_run_contract", {"run": "v1.lgbm_missing_tags"}),
    ("query_lakehouse", {"sql": "SELECT split, count(*) n, round(avg(default_12m), 4) rate FROM features GROUP BY 1"}),
    ("query_lakehouse", {"sql": "DROP VIEW features"}),  # must be rejected
]


def payload(res) -> dict:
    if res.structuredContent is not None:
        return res.structuredContent
    return json.loads(res.content[0].text)


def summarize(name: str, out: dict) -> str:
    if not out.get("ok"):
        return f"ok=false error={out['error']['code']}: {out['error']['message']}"
    if name == "get_standard":
        return f"version={out['standard']['version']} tags={[t['key'] for t in out['standard']['tag_contract']]}"
    if name == "list_experiments":
        runs = out["mlflow_experiments"][0]["runs"]
        return "runs=" + ", ".join(f"{r['run_name']}:{r['status']}:contract_ok={r['contract_ok']}" for r in runs)
    if name == "get_run":
        r = out["run"]
        return f"run_id={r['run_id']} status={r['status']} roc_auc={r['metrics']['roc_auc']:.4f}"
    if name == "compare_runs":
        return "; ".join(
            f"{r['run_name']} roc_auc Δ={r['metrics']['roc_auc']['delta']:+.4f} contract_ok={r['contract_ok']}"
            for r in out["runs"]
        )
    if name == "check_run_contract":
        c = out["contract"]
        return f"run_id={out['run_id']} ok={c['ok']} missing={c['missing']} invalid={[i['key'] for i in c['invalid']]}"
    if name == "query_lakehouse":
        return f"columns={out['columns']} rows={out['rows']}"
    return json.dumps(out)[:200]


async def main() -> int:
    failures = 0
    async with streamablehttp_client(URL) as (read, write, _), ClientSession(read, write) as session:
        init = await session.initialize()
        print(f"connected: {init.serverInfo.name} {init.serverInfo.version} (protocol {init.protocolVersion})")
        tools = (await session.list_tools()).tools
        print(f"tools: {sorted(t.name for t in tools)}")
        print(f"all readOnlyHint: {all(t.annotations and t.annotations.readOnlyHint for t in tools)}")
        for name, args in CALLS:
            res = await session.call_tool(name, args)
            out = payload(res)
            expect_reject = name == "query_lakehouse" and args["sql"].startswith("DROP")
            good = (not res.isError) and (out.get("ok") is (not expect_reject))
            failures += not good
            print(f"[{'PASS' if good else 'FAIL'}] {name}({json.dumps(args)[:70]}) -> {summarize(name, out)}")
    print(f"\n{len(CALLS) - failures}/{len(CALLS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
