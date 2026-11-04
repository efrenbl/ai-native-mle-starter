# skills/ — layer 4: how the agent works

One source of truth, in the open [Agent Skills](https://agentskills.io/specification) format
(`<name>/SKILL.md` with `name` + `description` frontmatter). `make skills`
(`scripts/install-skills.sh`) symlinks each folder into `.claude/skills/` (Claude Code) and
`.agents/skills/` (Codex). Edit here, never in the symlinked copies.

| Skill | Invocation | Writes? | MCP tools |
|---|---|---|---|
| `scaffold-experiment` | automatic | creates one experiment folder (via `make scaffold`) | get_standard, list_experiments |
| `review-experiment` | automatic | nothing | get_standard, list_experiments, check_run_contract, get_run, compare_runs |
| `explore-data` | automatic | nothing | get_standard, query_lakehouse |
| `promote-model` | **explicit only** (`/promote-model`) | registry alias, via `make promote` + permission prompt | check_run_contract, get_run, compare_runs, get_standard |

Each `description` says when to use the skill and when not to. `python scripts/validate_skills.py`
checks the frontmatter rules, the `## MCP tools` section, and that `promote-model` stays explicit-only.
