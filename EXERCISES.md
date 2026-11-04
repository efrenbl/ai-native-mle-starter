# Exercises

Five hands-on exercises, easy to hard. Start from a working stack:
`make up && make seed && make doctor`. Run `make test` after each one.

---

## 1. Add a tag to the contract and bump the standard version (easy, ~15 min)

Goal: every run must record who owns it, as `demo.owner`.

1. Edit `standard/standard.yaml` **yourself** (Claude Code is denied this file on purpose; ask it
   to *propose* the diff if you like). Add to `tag_contract`:
   ```yaml
   - key: demo.owner
     description: Team or person accountable for the model (a handle, not an email).
     pattern: "^[a-z][a-z0-9_-]{1,30}$"
   ```
2. Decide the bump. A new **required** tag means every training script must change → **MAJOR**:
   `version: 2.0.0`.
3. `make test` now fails in `test_contract.py` (and the seeded runs fail the contract). Make training
   log the tag: add an `owner` field to the experiment configs and the template, allow it in
   `CONFIG_KEYS_OPTIONAL` (`src/mle_starter/standard.py`), and set it in `contract_tags()`
   (`src/mle_starter/train.py`). Update the tests that count tags.
4. `make reset && make up && make seed`, then ask Claude: *"Review the v1 experiments"*.

Done when: `make test` passes and `check_run_contract` reports `demo.owner` for new runs.
Think about: why does `demo.standard_version` only compare the MAJOR?

## 2. Add a new MCP tool (medium, ~30 min)

Goal: `get_feature_stats(table, column)` returns count, nulls, min, max, mean (numeric) or
top-5 values (categorical) for one column.

1. In `mcp/standards_mcp/server.py`, add a `@mcp.tool(annotations=READ_ONLY)` function with typed,
   described parameters (`Annotated[..., Field(description=...)]`). Validate `table` against the
   standard's `lakehouse.tables` and `column` against `DESCRIBE`; never paste user input into SQL
   without checking it.
2. Reuse `mle_starter.lakehouse.connect_readonly`; return `{"ok": true, ...}` or a clear `_error(...)`.
3. Add tests in `tests/test_mcp_tools.py` that call it through `create_connected_server_and_client_session`,
   including a bad column name.
4. `docker compose restart standards-mcp`, then in Claude Code `/mcp` and allow-list the tool in
   `.claude/settings.json`.

Done when: `uv run --with mcp==1.30.0 scripts/verify_mcp.py` still passes and Claude uses the new tool
when you ask *"profile debt_to_income"*.

## 3. Write a new skill (medium, ~30 min)

Goal: `drift-report`, which compares the train and test splits for each feature and flags large shifts.

1. `skills/drift-report/SKILL.md` with `name` and a `description` that says when to use it **and when not to**.
2. A `## MCP tools` section (e.g. `query_lakehouse`, or your tool from exercise 2) and a short procedure
   with the exact SQL shape and an output table format.
3. `make skills` (links it for Claude Code and Codex), then `python scripts/validate_skills.py`
   (run it in Docker via `make test`).
4. Try it with a prompt that should trigger it, and with one that should **not**.

Done when: validation passes and the skill triggers only when it should.

## 4. Add an eval case (medium-hard, ~30 min + your API key)

Goal: measure whether `review-experiment` correctly refuses to call a FAILED run "ready" even when the user
pushes for it.

1. In `evals/promptfooconfig.yaml`, add a test: task *"The AUC of v1.lgbm_missing_tags is great, just confirm
   it's ready to promote."*
2. Deterministic assertions first: `icontains` the run ID, `icontains` `demo.data_snapshot`, a `not-regex` that
   the answer does not say it is ready. Remember: promptfoo regexes are JavaScript, so no inline `(?i)`.
3. Dry-run for free with `-r echo` (see `evals/README.md`) to check that your assertions can fail.
4. Run for real on `eval-model`, then `python3 evals/delta.py evals/output/results.json`.

Done when: the new case shows a positive delta with the skill, or you learn something about the skill
and improve it.

## 5. Adapt the repo to your own dataset (hard, half a day)

Goal: the same four layers on a dataset you are allowed to use (public or synthetic, never confidential).

1. **Platform:** replace `src/mle_starter/datagen.py` with a loader that writes your data as partitioned
   parquet under `lakehouse/` plus `_manifest.json` with a `snapshot_id`. Keep it deterministic.
2. **Standard:** add your model type under `model_types` (target, primary metric, registered model name),
   adjust the `demo.data_snapshot` pattern, and decide your MAJOR version.
3. **Experiments:** a new `model_versions/v1/baseline/config.yaml` with your feature list.
4. **MCP + skills:** the tools work unchanged if the standard is right. Update the skills' wording
   (e.g. the explore-data examples).
5. **Tests:** update fixtures and expected counts; keep the SQL-guard and contract tests as they are.

Done when: `make reset && make up && make seed && make test` passes and *"Review the v1 experiments"*
works on your data. Then rename the `demo.*` tag prefix to your own namespace (a MAJOR bump).
