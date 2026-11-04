"""Skill frontmatter validation and the one-source/many-clients installer."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from validate_skills import validate_skill

REPO = Path(__file__).resolve().parents[1]
SKILLS = sorted(p for p in (REPO / "skills").iterdir() if p.is_dir())


def test_expected_skills_exist():
    assert {p.name for p in SKILLS} == {"scaffold-experiment", "review-experiment", "explore-data", "promote-model"}


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_repo_skills_are_valid(skill):
    assert validate_skill(skill) == []


def _write(tmp_path, folder, frontmatter, body="## MCP tools\n- x\n"):
    d = tmp_path / folder
    d.mkdir()
    (d / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n{body}")
    return d


@pytest.mark.parametrize(
    "folder,frontmatter,body,needle",
    [
        ("a-skill", "name: other\ndescription: Use when x. Do not use for y.", "## MCP tools\n", "folder name"),
        ("a-skill", "name: A_Skill\ndescription: Use when x. Do not use for y.", "## MCP tools\n", "invalid name"),
        ("a-skill", "name: a-skill", "## MCP tools\n", "description"),
        ("a-skill", "name: a-skill\ndescription: Helps.", "## MCP tools\n", "when to use"),
        ("a-skill", "name: a-skill\ndescription: Use when x.", "## MCP tools\n", "NOT"),
        ("a-skill", "name: a-skill\ndescription: Use when x. Do not use for y.", "body\n", "MCP tools"),
        (
            "promote-model",
            "name: promote-model\ndescription: Use when x. Never otherwise.",
            "## MCP tools\n",
            "explicit",
        ),
    ],
)
def test_invalid_skills_are_caught(tmp_path, folder, frontmatter, body, needle):
    errors = validate_skill(_write(tmp_path, folder, frontmatter, body))
    assert errors and any(needle in e for e in errors), errors


def test_frontmatter_must_be_first_line(tmp_path):
    d = tmp_path / "x-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("\n---\nname: x-skill\n---\n")
    assert "line 1" in validate_skill(d)[0]


def test_promote_model_is_explicit_only():
    text = (REPO / "skills/promote-model/SKILL.md").read_text()
    assert "disable-model-invocation: true" in text.split("---")[1]


def test_install_skills_is_idempotent(tmp_path):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "scripts/install-skills.sh", root / "scripts/")
    shutil.copytree(REPO / "skills", root / "skills")
    script = root / "scripts/install-skills.sh"
    first = subprocess.run(["bash", str(script)], capture_output=True, text=True, check=True).stdout
    second = subprocess.run(["bash", str(script)], capture_output=True, text=True, check=True).stdout
    assert f"{2 * len(SKILLS)} created" in first
    assert f"0 created, {2 * len(SKILLS)} unchanged" in second
    for client in (".claude/skills", ".agents/skills"):
        for s in SKILLS:
            link = root / client / s.name
            assert link.is_symlink() and (link / "SKILL.md").is_file()
    # A removed skill leaves no dangling link behind.
    shutil.rmtree(root / "skills/explore-data")
    third = subprocess.run(["bash", str(script)], capture_output=True, text=True, check=True).stdout
    assert "2 pruned" in third and not (root / ".claude/skills/explore-data").exists()
