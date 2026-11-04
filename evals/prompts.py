"""promptfoo prompt functions: the same task and evidence, without and with the skill.

The evidence is a JSON snapshot of real standards-mcp tool outputs (fixtures/), so
the eval measures the skill's procedure, not the model's ability to call tools.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "skills" / "review-experiment" / "SKILL.md"

CONTEXT = (
    "You are an assistant in a machine-learning repository. The following JSON holds the "
    "outputs of read-only tools you already called (MLflow runs, the repo's ML standard, a "
    "baseline comparison).\n\n<tool_outputs>\n{evidence}\n</tool_outputs>\n\nUser request: {task}"
)


def _evidence(context) -> str:
    path = HERE / context["vars"]["evidence"]
    return json.dumps(json.loads(path.read_text()), indent=1)


def baseline(context):
    v = context["vars"]
    return CONTEXT.format(evidence=_evidence(context), task=v["task"])


def with_skill(context):
    v = context["vars"]
    body = SKILL.read_text().split("---", 2)[2].strip()
    return (
        'Follow this skill exactly.\n<skill name="review-experiment">\n'
        + body
        + "\n</skill>\n\n"
        + CONTEXT.format(evidence=_evidence(context), task=v["task"])
    )
