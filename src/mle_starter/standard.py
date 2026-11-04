"""Load the standard and check things against it.

This module is the single source of truth for "does X follow the standard?".
The training entrypoint, the MCP server, the promotion script and the tests
all import it, so a rule lives in exactly one place.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_KEYS_REQUIRED = {"model_type", "model_version", "experiment_id", "data", "model"}
CONFIG_KEYS_OPTIONAL = {"description", "baseline_experiment_id", "demo_fault"}


class StandardError(ValueError):
    """Raised when something does not follow the standard. Carries every problem found."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def repo_root() -> Path:
    env = os.environ.get("MLE_REPO_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


def load_standard(path: Path | None = None) -> dict[str, Any]:
    path = path or Path(os.environ.get("STANDARD_PATH", repo_root() / "standard" / "standard.yaml"))
    with open(path, encoding="utf-8") as fh:
        std = yaml.safe_load(fh)
    if not isinstance(std, dict) or "version" not in std or "tag_contract" not in std:
        raise StandardError([f"{path} is not a valid standard file (needs version and tag_contract)"])
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(std["version"])):
        raise StandardError([f"standard version {std['version']!r} is not semver"])
    return std


def required_tag_keys(std: dict[str, Any]) -> list[str]:
    return [t["key"] for t in std["tag_contract"]]


def run_name_for(std: dict[str, Any], model_version: str, experiment_id: str) -> str:
    return std["tracking"]["run_name"].format(model_version=model_version, experiment_id=experiment_id)


def experiment_name_for(std: dict[str, Any], model_type: str) -> str:
    return std["tracking"]["experiment_name"].format(model_type=model_type)


@dataclass
class ContractResult:
    ok: bool
    standard_version: str
    missing: list[str] = field(default_factory=list)
    invalid: list[dict[str, str]] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "standard_version": self.standard_version,
            "missing": self.missing,
            "invalid": self.invalid,
            "checked": self.checked,
        }


def check_tags(
    tags: dict[str, str],
    std: dict[str, Any],
    run_name: str | None = None,
    experiment_name: str | None = None,
) -> ContractResult:
    """Check a run's tags (and optionally its run/experiment name) against the tag contract."""
    missing: list[str] = []
    invalid: list[dict[str, str]] = []
    major = str(std["version"]).split(".")[0]

    for rule in std["tag_contract"]:
        key = rule["key"]
        value = tags.get(key)
        if value is None or str(value).strip() == "":
            missing.append(key)
            continue
        value = str(value)
        if "pattern" in rule and not re.fullmatch(rule["pattern"], value):
            invalid.append({"key": key, "value": value, "reason": f"does not match {rule['pattern']}"})
            continue
        if "allowed_from" in rule:
            allowed = sorted(std[rule["allowed_from"]].keys())
            if value not in allowed:
                invalid.append({"key": key, "value": value, "reason": f"must be one of {allowed}"})
                continue
        if rule.get("same_major_as_standard") and value.split(".")[0] != major:
            invalid.append(
                {
                    "key": key,
                    "value": value,
                    "reason": f"MAJOR differs from current standard {std['version']}",
                }
            )

    # Cross-field checks: names must agree with the tags.
    mv, eid, mt = tags.get("demo.model_version"), tags.get("demo.experiment_id"), tags.get("demo.model_type")
    if run_name is not None and mv and eid:
        expected = run_name_for(std, mv, eid)
        if run_name != expected:
            invalid.append({"key": "run_name", "value": run_name, "reason": f"expected {expected!r}"})
    if experiment_name is not None and mt:
        expected = experiment_name_for(std, mt)
        if experiment_name != expected:
            invalid.append({"key": "experiment_name", "value": experiment_name, "reason": f"expected {expected!r}"})

    return ContractResult(
        ok=not missing and not invalid,
        standard_version=str(std["version"]),
        missing=missing,
        invalid=invalid,
        checked=required_tag_keys(std),
    )


@dataclass
class Experiment:
    path: Path
    model_version: str
    experiment_id: str
    config: dict[str, Any]

    @property
    def model_type(self) -> str:
        return self.config["model_type"]

    @property
    def lib(self) -> str:
        return self.config["model"]["lib"]


def load_experiment(exp_dir: Path | str, std: dict[str, Any], root: Path | None = None) -> Experiment:
    """Validate an experiment folder against the layout and config rules. Raises StandardError."""
    root = root or repo_root()
    exp_dir = Path(exp_dir)
    if not exp_dir.is_absolute():
        exp_dir = (root / exp_dir).resolve()
    problems: list[str] = []
    layout = std["layout"]

    try:
        rel = exp_dir.relative_to((root / layout["root"]).resolve())
    except ValueError:
        raise StandardError([f"{exp_dir} is not under {layout['root']}/"]) from None
    if rel.parts and rel.parts[0] == Path(layout["template_dir"]).name:
        raise StandardError(["the template folder is not a runnable experiment; scaffold a copy first"])
    if len(rel.parts) != 2:
        raise StandardError([f"expected {layout['experiment_path']}, got {layout['root']}/{rel}"])
    model_version, experiment_id = rel.parts
    if model_version == Path(layout["template_dir"]).name or experiment_id.startswith("_"):
        raise StandardError(["the template folder is not a runnable experiment; scaffold a copy first"])
    if not re.fullmatch(layout["model_version_pattern"], model_version):
        problems.append(f"model_version {model_version!r} does not match {layout['model_version_pattern']}")
    if not re.fullmatch(layout["experiment_id_pattern"], experiment_id):
        problems.append(f"experiment_id {experiment_id!r} does not match {layout['experiment_id_pattern']}")
    for fname in layout["required_files"]:
        if not (exp_dir / fname).is_file():
            problems.append(f"missing required file {fname}")
    if problems:
        raise StandardError(problems)

    with open(exp_dir / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    missing = CONFIG_KEYS_REQUIRED - cfg.keys()
    unknown = cfg.keys() - CONFIG_KEYS_REQUIRED - CONFIG_KEYS_OPTIONAL
    if missing:
        problems.append(f"config.yaml is missing keys: {sorted(missing)}")
    if unknown:
        problems.append(f"config.yaml has unknown keys: {sorted(unknown)}")
    if cfg.get("model_version") not in (None, model_version):
        problems.append(f"config model_version {cfg.get('model_version')!r} != folder {model_version!r}")
    if cfg.get("experiment_id") not in (None, experiment_id):
        problems.append(f"config experiment_id {cfg.get('experiment_id')!r} != folder {experiment_id!r}")
    if "model_type" in cfg and cfg["model_type"] not in std["model_types"]:
        problems.append(f"model_type {cfg['model_type']!r} not in {sorted(std['model_types'])}")
    model = cfg.get("model") or {}
    lib, est = model.get("lib"), model.get("estimator")
    if lib not in std["libraries"]:
        problems.append(f"model.lib {lib!r} not supported; use one of {sorted(std['libraries'])}")
    elif est not in std["libraries"][lib]["estimators"]:
        problems.append(f"model.estimator {est!r} not supported for {lib}: {std['libraries'][lib]['estimators']}")
    data = cfg.get("data") or {}
    if not data.get("features"):
        problems.append("data.features must list at least one feature column")
    if problems:
        raise StandardError(problems)
    return Experiment(path=exp_dir, model_version=model_version, experiment_id=experiment_id, config=cfg)


def list_local_experiments(std: dict[str, Any], root: Path | None = None) -> list[dict[str, Any]]:
    """Every folder under model_versions/<mv>/<id>/, valid or not, with any problems found."""
    root = root or repo_root()
    base = root / std["layout"]["root"]
    out: list[dict[str, Any]] = []
    if not base.is_dir():
        return out
    for mv_dir in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        for exp_dir in sorted(p for p in mv_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            item: dict[str, Any] = {
                "model_version": mv_dir.name,
                "experiment_id": exp_dir.name,
                "path": str(exp_dir.relative_to(root)),
                "run_name": run_name_for(std, mv_dir.name, exp_dir.name),
            }
            try:
                exp = load_experiment(exp_dir, std, root)
                item.update(valid=True, problems=[], model_type=exp.model_type, lib=exp.lib)
            except StandardError as err:
                item.update(valid=False, problems=err.problems)
            out.append(item)
    return out
