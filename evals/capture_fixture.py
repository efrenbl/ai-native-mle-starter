"""Capture real standards-mcp tool outputs for the three seed runs as the eval fixture.

    make up && make seed
    uv run --with mcp==1.30.0 evals/capture_fixture.py

Writes evals/fixtures/review_v1_evidence.json and prints the run IDs that
evals/promptfooconfig.yaml asserts on (update them there after re-capturing).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://localhost:8765/mcp"
OUT = Path(__file__).resolve().parent / "fixtures" / "review_v1_evidence.json"
SEED = ["v1.baseline", "v1.lgbm_monotonic", "v1.lgbm_missing_tags"]


async def main() -> int:
    async with streamablehttp_client(URL) as (read, write, _), ClientSession(read, write) as s:
        await s.initialize()

        async def call(name: str, args: dict) -> dict:
            out = (await s.call_tool(name, args)).structuredContent
            if not out or not out.get("ok"):
                raise SystemExit(f"{name} failed: {out}")
            return out

        std = await call("get_standard", {})
        listing = await call("list_experiments", {"model_type": "credit_default"})
        for exp in listing["mlflow_experiments"]:
            exp["runs"] = [r for r in exp["runs"] if r["run_name"] in SEED]
        listing["local_experiments"] = [e for e in listing["local_experiments"] if f"v1.{e['experiment_id']}" in SEED]
        contracts = {name: await call("check_run_contract", {"run": name}) for name in SEED[1:]}
        comparison = await call("compare_runs", {"runs": SEED[1:], "baseline": "v1.baseline"})

    evidence = {
        "get_standard": {
            "ok": True,
            "standard": {k: std["standard"][k] for k in ("version", "tag_contract", "tracking")},
        },
        "list_experiments": listing,
        "check_run_contract": contracts,
        "compare_runs": comparison,
    }
    OUT.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"wrote {OUT}")
    for name, c in contracts.items():
        print(f"  {name:<24} {c['run_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
