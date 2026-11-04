"""Create model_versions/<model_version>/<experiment_id>/ from model_versions/_TEMPLATE.

    make scaffold MV=v1 EXP=lgbm_shallow

Refuses to overwrite an existing folder, and validates the result against the standard.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys

from mle_starter.standard import StandardError, load_experiment, load_standard, repo_root


def scaffold(model_version: str, experiment_id: str) -> str:
    std = load_standard()
    layout = std["layout"]
    problems = []
    if not re.fullmatch(layout["model_version_pattern"], model_version):
        problems.append(f"model_version {model_version!r} must match {layout['model_version_pattern']}")
    if not re.fullmatch(layout["experiment_id_pattern"], experiment_id):
        problems.append(f"experiment_id {experiment_id!r} must match {layout['experiment_id_pattern']}")
    if problems:
        raise StandardError(problems)
    root = repo_root()
    template = root / layout["template_dir"]
    target = root / layout["experiment_path"].format(model_version=model_version, experiment_id=experiment_id)
    if target.exists():
        raise StandardError([f"{target.relative_to(root)} already exists; pick another experiment_id"])
    shutil.copytree(template, target)
    for path in target.rglob("*"):
        if path.is_file() and path.suffix in (".yaml", ".yml", ".md"):
            text = path.read_text()
            text = text.replace("{{model_version}}", model_version).replace("{{experiment_id}}", experiment_id)
            path.write_text(text)
    try:
        load_experiment(target, std, root)
    except StandardError:
        shutil.rmtree(target)
        raise
    return str(target.relative_to(root))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model_version")
    ap.add_argument("experiment_id")
    args = ap.parse_args(argv)
    try:
        path = scaffold(args.model_version, args.experiment_id)
    except StandardError as err:
        print("scaffold refused:", *[f"\n  - {p}" for p in err.problems], file=sys.stderr)
        return 2
    print(f"created {path}/config.yaml  ->  next: make train EXP={path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
