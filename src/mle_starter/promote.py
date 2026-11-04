"""Set a registry alias on a model version, but only for a run that passes the contract.

    make promote RUN=<run_id> ALIAS=challenger              # dry run: shows what would happen
    make promote RUN=<run_id> ALIAS=challenger CONFIRM=yes  # actually sets the alias

This is a WRITE to the registry. No MCP tool can do it. The promote-model skill is
explicit-only, and .claude/settings.json puts `make promote` behind a permission prompt.
"""

from __future__ import annotations

import argparse
import json
import sys

from mlflow.tracking import MlflowClient

from mle_starter.standard import check_tags, load_standard


def promote(run_id: str, alias: str, confirm: bool) -> dict:
    std = load_standard()
    allowed = std["registry"]["allowed_aliases"]
    if alias not in allowed:
        return {"status": "refused", "reason": f"alias {alias!r} not in allowed_aliases {allowed}"}

    client = MlflowClient()
    run = client.get_run(run_id)
    exp = client.get_experiment(run.info.experiment_id)
    report = check_tags(run.data.tags, std, run_name=run.info.run_name, experiment_name=exp.name)
    if run.info.status != "FINISHED":
        report.ok = False
        report.invalid.append({"key": "status", "value": run.info.status, "reason": "run must be FINISHED"})
    if not report.ok:
        return {"status": "refused", "reason": "run fails the tag contract", "contract": report.to_dict()}

    model_type = run.data.tags["demo.model_type"]
    model_name = std["model_types"][model_type]["registered_model"]
    versions = client.search_model_versions(f"name='{model_name}' and run_id='{run_id}'")
    if not versions:
        return {"status": "refused", "reason": f"run {run_id} has no registered version of {model_name}"}
    version = max(versions, key=lambda v: int(v.version)).version

    previous = None
    try:
        previous = client.get_model_version_by_alias(model_name, alias).version
    except Exception:  # noqa: BLE001 - alias not set yet
        previous = None

    plan = {"model": model_name, "version": version, "alias": alias, "previous_version": previous, "run_id": run_id}
    if not confirm:
        return {"status": "dry_run", "would_set": plan, "hint": "re-run with CONFIRM=yes to apply"}
    client.set_registered_model_alias(model_name, alias, version)
    return {"status": "promoted", **plan}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--alias", required=True)
    ap.add_argument("--confirm", action="store_true", help="actually set the alias (default is a dry run)")
    args = ap.parse_args(argv)
    result = promote(args.run_id, args.alias, args.confirm)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in ("promoted", "dry_run") else 1


if __name__ == "__main__":
    sys.exit(main())
