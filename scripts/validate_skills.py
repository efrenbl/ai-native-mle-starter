"""Validate every skills/<name>/SKILL.md against the Agent Skills format.

Rules (agentskills.io/specification, plus this repo's conventions):
  - frontmatter is the first thing in the file, between `---` lines, valid YAML
  - name: 1-64 chars, [a-z0-9-], no leading/trailing/double hyphen, equals the folder name
  - description: 1-1024 chars, says when to use AND when not to use the skill
  - body lists the MCP tools the skill relies on (a "## MCP tools" section)
  - promote-model must be explicit-only (disable-model-invocation: true)

    python scripts/validate_skills.py [skills_dir]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
EXPLICIT_ONLY = {"promote-model"}


def parse(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("frontmatter must start on line 1 with ---")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("frontmatter is not closed with ---")
    meta = yaml.safe_load(text[4:end])
    if not isinstance(meta, dict):
        raise ValueError("frontmatter is not a YAML mapping")
    return meta, text[end + 4 :]


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        return [f"{skill_dir.name}: missing SKILL.md"]
    try:
        meta, body = parse(path)
    except (ValueError, yaml.YAMLError) as err:
        return [f"{skill_dir.name}: {err}"]
    name, desc = meta.get("name"), meta.get("description")
    if not isinstance(name, str) or not (1 <= len(name) <= 64) or not NAME_RE.match(name):
        errors.append(f"{skill_dir.name}: invalid name {name!r}")
    elif name != skill_dir.name:
        errors.append(f"{skill_dir.name}: name {name!r} must equal the folder name")
    if not isinstance(desc, str) or not (1 <= len(desc) <= 1024):
        errors.append(f"{skill_dir.name}: description must be 1-1024 characters")
    else:
        if not re.search(r"\buse\b[^.]{0,20}\bwhen\b|\buse for\b", desc, re.IGNORECASE):
            errors.append(f"{skill_dir.name}: description must say when to use the skill")
        if not re.search(r"\b(do not|don't|not for|never)\b", desc, re.IGNORECASE):
            errors.append(f"{skill_dir.name}: description must say when NOT to use the skill")
    if "## MCP tools" not in body:
        errors.append(f"{skill_dir.name}: body must have a '## MCP tools' section listing the tools it relies on")
    if skill_dir.name in EXPLICIT_ONLY and meta.get("disable-model-invocation") is not True:
        errors.append(f"{skill_dir.name}: must set disable-model-invocation: true (explicit-only)")
    if len(path.read_text(encoding="utf-8").splitlines()) > 500:
        errors.append(f"{skill_dir.name}: SKILL.md is over 500 lines")
    return errors


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "skills"
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    if not dirs:
        print(f"no skills found under {root}")
        return 1
    errors = [e for d in dirs for e in validate_skill(d)]
    for e in errors:
        print(f"FAIL {e}")
    print(f"validated {len(dirs)} skills: {'OK' if not errors else f'{len(errors)} error(s)'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
