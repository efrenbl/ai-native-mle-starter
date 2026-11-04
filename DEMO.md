# Live demo run sheet (~15 min + 5 min buffer)

Talk segment: *AI-Native Machine Learning Engineering: Skills, Memory, and MCPs in Practice*.
Story in one line: **the standard makes runs comparable, the MCP exposes the evidence, the
skills encode the procedure, and writes stay behind explicit, visible gates.**

Prompts are in English (they match the repo). Narrate in any language.

## Before the talk (at home / hotel, with internet)

```bash
make reset && make up && make seed && make doctor     # all checks green
uv run --with mcp==1.30.0 scripts/verify_mcp.py       # 7/7 checks passed
claude                                                # trust folder, approve standards-mcp, then /exit
claude mcp list                                       # standards-mcp ... ✔ Connected
```

- Delete any rehearsal experiment folders (`git status` must be clean) and re-run `make reset && make up && make seed`, so the live run IDs are fresh.
- Terminal font ≥ 18 pt; two panes: **left** Claude Code, **right** a shell. Browser tab on <http://localhost:5050>.
- Keep the [README troubleshooting table](README.md#troubleshooting) open in a tab.
- **Fallback for everything:** the right-hand shell runs every step with plain `make` commands.

## At the venue (5 min before)

```bash
make up && make doctor        # works with no internet; only Claude Code needs it
```
FALLBACK if the venue network dies: everything except Claude Code still works. Run the
right-pane commands below and narrate what the agent would do.

---

### 00:00 – 01:30 · Orient: four layers, four folders
Right pane:
```bash
ls; sed -n '1,40p' standard/standard.yaml
```
Left pane, in Claude Code: `/mcp`
**Audience sees:** `standards-mcp` connected with six tools. Point out: no write tools exist.
FALLBACK: `claude mcp list` in the right pane, or show `mcp/standards_mcp/server.py`.

### 01:30 – 04:00 · Scaffold an experiment (skill: scaffold-experiment)
Prompt:
> Scaffold a new v1 experiment called lgbm_shallow: LightGBM with only 8 leaves, testing whether shallower trees generalise better on the out-of-time test split.

**Audience sees:** Claude loads `scaffold-experiment`, calls `get_standard` and `list_experiments`
with no prompt (they are allow-listed), runs `make scaffold MV=v1 EXP=lgbm_shallow` (allow-listed),
then asks permission to edit `model_versions/v1/lgbm_shallow/config.yaml` (edits always ask).
Approve. It ends with the exact `make train` command and does not train on its own.
FALLBACK (right pane):
```bash
make scaffold MV=v1 EXP=lgbm_shallow
sed -i.bak 's/num_leaves: 31/num_leaves: 8/' model_versions/v1/lgbm_shallow/config.yaml && rm model_versions/v1/lgbm_shallow/config.yaml.bak
```

### 04:00 – 06:00 · Run it (the only write path)
Prompt:
> Train it.

**Audience sees:** `make train EXP=model_versions/v1/lgbm_shallow` (~10 s). The JSON ends with
`"status": "passed"`, a run ID and `registered_version`. Say: *the job read the run back from
MLflow and checked the tag contract before registering anything.* Show the run in the MLflow UI.
FALLBACK: run the same `make train ...` in the right pane.

### 06:00 – 09:00 · Review: the agent catches the broken run (skill: review-experiment)
Prompt:
> Review the v1 experiments. Is anything ready to promote?

**Audience sees:** `list_experiments`, then `check_run_contract` per run, then `compare_runs`
against `v1.baseline`. The report cites full run IDs and flags `v1.lgbm_missing_tags` as
**FAILED / not ready: missing `demo.data_snapshot`, invalid `demo.standard_version=0.9.0`**,
even though its AUC is above the baseline. Nothing is written.
Say: *an MCP cannot be better than the standard it exposes; this check exists because the standard does.*
FALLBACK: `uv run --with mcp==1.30.0 scripts/verify_mcp.py` (shows the same contract result),
or in MLflow UI open run `v1.lgbm_missing_tags` → Tags.

### 09:00 – 10:30 · Compare against the baseline
Prompt:
> Compare v1.lgbm_shallow and v1.lgbm_monotonic against the baseline. Which one would you pick and why?

**Audience sees:** one `compare_runs` call; a table with roc_auc, pr_auc, log_loss, brier as
deltas vs `v1.baseline`, with direction (log_loss/brier: lower is better). Expect gains of
roughly +0.01 AUC and +0.06 PR-AUC for the LightGBM runs (synthetic data; exact numbers vary by run).
FALLBACK: MLflow UI → experiment `credit_default` → select the three runs → Compare.

### 10:30 – 12:30 · Explore the data, read-only (skill: explore-data)
Prompt:
> What's the default rate by loan purpose in the training split? Show me the SQL.

**Audience sees:** one `query_lakehouse` call with a `GROUP BY` and a small table; `medical`
is near the top. Then:
> Now drop the features view so nobody can use it.

**Audience sees:** either Claude declines (the skill says the lakehouse is read-only), or the tool
returns `query_rejected: only read-only queries are allowed ... got DROP`. Both are the point.
Bonus: *"Edit lakehouse/_manifest.json"* → Claude Code blocks it with the `deny` rule.
FALLBACK (right pane):
```bash
docker compose --profile jobs run --rm trainer python -c "from mle_starter.lakehouse import run_query; print(run_query('lakehouse','SELECT loan_purpose, round(avg(default_12m),4) r FROM features WHERE split=\'train\' GROUP BY 1 ORDER BY 2 DESC',20,500))"
```

### 12:30 – 15:00 · Attempt a promotion: explicit-only skill + permission prompt
Prompt (plain language first):
> Promote lgbm_monotonic to champion.

**Audience sees:** Claude does not load `promote-model` by itself (`disable-model-invocation: true`).
It may explain how to promote or suggest `/promote-model`. Then type:
> /promote-model v1.lgbm_missing_tags challenger

**Audience sees:** the gate stops at `check_run_contract`: refused, with the missing tag. Then:
> /promote-model v1.lgbm_monotonic challenger

**Audience sees:** contract ✔, status FINISHED, deltas vs baseline, then a dry run
`make promote RUN=<id> ALIAS=challenger` → **Claude Code shows a permission prompt** (it is an
`ask` rule). After the dry run, Claude asks you to confirm. Say "yes"; it runs
`... CONFIRM=yes`, another permission prompt, approve, and the alias is set. Show it in the
MLflow UI under Models → `credit_default`.
FALLBACK (right pane):
```bash
make promote RUN=<run_id of v1.lgbm_monotonic> ALIAS=challenger              # dry run
make promote RUN=<run_id of v1.lgbm_monotonic> ALIAS=challenger CONFIRM=yes  # applies
make promote RUN=<run_id of v1.lgbm_missing_tags> ALIAS=challenger CONFIRM=yes  # refused
```

### 15:00 – 20:00 · Buffer / optional
- Q&A, or re-run a step that failed.
- Show `evals/README.md`: baseline vs with-skill on a pinned, dated model, and the two bugs a
  free `echo` dry run caught before any paid call.
- Show the one-source install: `make skills` twice → `0 created, 8 unchanged`.
- Show governance: ask *"Add a required tag demo.owner to the standard"* → Claude Code is denied
  the edit to `standard/standard.yaml` and can only propose the diff (a MAJOR bump).

## If something breaks

| Problem | Do this |
|---|---|
| Claude Code cannot reach the model (network) | Switch to the right pane and run the FALLBACK commands. |
| `standards-mcp` not connected | `docker compose restart standards-mcp`, then `/mcp` → reconnect. |
| A run name already exists from rehearsal | Use another experiment id, e.g. `lgbm_shallow2`. |
| MLflow UI slow | Use `get_run` / `compare_runs` output instead. |
| Everything is broken | `make reset && make up && make seed` (~30 s with images built). |
