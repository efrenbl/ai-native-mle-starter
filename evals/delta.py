"""Report the with-skill vs baseline delta from a promptfoo results file.

    python3 evals/delta.py evals/output/results.json

Deterministic assertions are the evidence; llm-rubric is reported separately as a
secondary check, so judge noise cannot hide a deterministic regression.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict


def main(path: str) -> int:
    with open(path) as fh:
        data = json.load(fh)
    rows = data["results"]["results"]
    by_prompt: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        label = r["prompt"].get("label") or r.get("promptId")
        by_prompt[label]["case_pass"].append(bool(r["success"]))
        for c in (r.get("gradingResult") or {}).get("componentResults", []):
            a = c.get("assertion") or {}
            kind = "rubric" if a.get("type") == "llm-rubric" else "deterministic"
            by_prompt[label][kind].append(bool(c.get("pass")))
            if a.get("metric"):
                by_prompt[label][f"  {a['metric']}"].append(bool(c.get("pass")))

    def rate(xs: list[bool]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    labels = ["baseline", "with_skill"]
    if not all(lbl in by_prompt for lbl in labels):
        print(f"expected prompts {labels}, found {sorted(by_prompt)}")
        return 2
    keys = ["case_pass", "deterministic", "rubric"] + sorted(k for k in by_prompt["with_skill"] if k.startswith("  "))
    print(f"{'check':<24}{'baseline':>10}{'with_skill':>12}{'delta':>9}")
    for k in keys:
        b, w = rate(by_prompt["baseline"][k]), rate(by_prompt["with_skill"][k])
        fmt = lambda v: "   -" if v is None else f"{v:6.0%}"  # noqa: E731
        d = "" if b is None or w is None else f"{(w - b) * 100:+.0f}pp"
        print(f"{k:<24}{fmt(b):>10}{fmt(w):>12}{d:>9}")
    print("\nThe delta on deterministic checks is the signal; the rubric row is a secondary guardrail.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "evals/output/results.json"))
