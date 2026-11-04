# Contributing

Small, focused pull requests are welcome.

1. `make up && make seed && make test` must pass. CI runs ruff, pytest, skill validation
   and `docker compose config` with no secrets.
2. Changing `standard/standard.yaml`? Bump `version` (MAJOR if anyone has to change how they
   work, e.g. a new required tag; MINOR if additive; PATCH for wording) and say why in the PR.
3. New or changed skill? Keep `SKILL.md` short, say when to use it **and when not to**, list the
   MCP tools it relies on under `## MCP tools`, and run `python scripts/validate_skills.py`.
4. New MCP tool? It must be read-only, typed, return `{"ok": ...}` JSON, and have a test that
   calls it through an MCP client session (`tests/test_mcp_tools.py`).
5. Pin every new dependency to an exact version (`platform/requirements/*.in`, then recompile
   the lock with the `uv pip compile` command at the top of the `.in` file).
6. Install the pre-commit hooks (gitleaks + ruff): `pip install pre-commit==4.5.1 && pre-commit install`.
   Never commit `.env` or real data.
