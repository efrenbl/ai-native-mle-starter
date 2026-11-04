# Architecture: how the pieces work together

The [README](../README.md#the-four-layers) shows the four layers as folders. This page
shows them **at run time**: what calls what, where the checks happen, and which paths can
write. Every name below (tools, functions, make targets) exists in the code.

1. [Runtime topology](#1-runtime-topology): containers, ports, mounts
2. [Reviewing an experiment](#2-reviewing-an-experiment-read-only): the read-only path
3. [Training a run](#3-training-a-run-check-dont-trust): check, don't trust
4. [Promoting a model](#4-promoting-a-model-explicit-only-gated): explicit-only, gated
5. [Read-only SQL](#5-read-only-sql-over-the-lakehouse): the guards behind `query_lakehouse`
6. [The loop](#6-the-loop-standard--mcp--skills--feedback): standard → MCP → skills → feedback

---

## 1. Runtime topology

Everything binds to `127.0.0.1`. The MCP server sees the repo **read-only**; only the
one-off `trainer` job mounts it read-write. After `make up`, nothing here needs the internet.

```mermaid
flowchart LR
    subgraph host["Your laptop"]
        CC["Claude Code<br/>reads .mcp.json, .claude/settings.json,<br/>CLAUDE.md, .claude/skills/"]
        MK["make up · seed · train · promote"]
        UI["Browser<br/>localhost:5050"]
        REPO[("repo checkout<br/>standard/ · model_versions/<br/>lakehouse/ · src/ · mcp/")]
    end
    subgraph docker["docker compose project: ai-native-mle-starter"]
        MCP["standards-mcp<br/>FastMCP, streamable HTTP :8765/mcp<br/>6 read-only tools"]
        TR["trainer (profile: jobs)<br/>one-off container per make target"]
        ML["mlflow :5000<br/>tracking + registry<br/>sqlite + served artifacts"]
        VOL[("volumes<br/>mlflow-db · mlflow-artifacts")]
    end
    CC -- "MCP over HTTP<br/>localhost:8765" --> MCP
    CC -- "Bash: make ..." --> MK
    MK -- "docker compose run" --> TR
    UI -- "localhost:5050" --> ML
    MCP -- "MlflowClient reads" --> ML
    TR -- "log runs, register models,<br/>set aliases" --> ML
    ML --- VOL
    REPO -. "mounted :ro" .-> MCP
    REPO -. "mounted rw" .-> TR
```

| Piece | Image | Writes? |
|---|---|---|
| `mlflow` | `ghcr.io/mlflow/mlflow:v3.17.2` | stores what it is sent |
| `standards-mcp` | `ai-native-mle-starter-app:local` | no: no write tools, repo mounted `:ro` |
| `trainer` | same app image | yes, and only through `make train` / `make promote` / `make seed` / `make scaffold` |

---

## 2. Reviewing an experiment (read-only)

Prompt: *"Review the v1 experiments. Is anything ready to promote?"* The
`review-experiment` skill turns that into a fixed procedure. Every tool is allow-listed in
`.claude/settings.json`, so no permission prompt appears, and nothing is written.

```mermaid
sequenceDiagram
    actor U as You
    participant CC as Claude Code
    participant SK as Skill review-experiment
    participant MCP as standards-mcp
    participant STD as standard.yaml
    participant ML as MLflow

    U->>CC: Review the v1 experiments
    CC->>SK: load procedure (matched by description)
    CC->>MCP: get_standard()
    MCP->>STD: load_standard()
    MCP-->>CC: version 1.0.0, 6 demo.* tags, required metrics
    CC->>MCP: list_experiments(model_type=credit_default)
    MCP->>ML: search_experiments / search_runs
    MCP-->>CC: runs with status and contract summary
    loop each run in scope
        CC->>MCP: check_run_contract(run)
        MCP->>ML: get_run(run_id)
        MCP->>STD: check_tags(tags, run_name, experiment_name)
        MCP-->>CC: ok / missing / invalid
    end
    CC->>MCP: compare_runs(runs, baseline=v1.baseline)
    MCP->>ML: get_run for each run and the baseline
    MCP-->>CC: metric deltas, direction-aware
    CC-->>U: report citing run IDs: ready / not ready, next action
    Note over CC,ML: read-only end to end, no permission prompt
```

---

## 3. Training a run: check, don't trust

`make train EXP=model_versions/v1/<id>` → `python -m mle_starter.train`. The run is
accepted only after its tags are **read back from the server** and checked against the
contract. A run that "forgets" a tag is marked `FAILED` and registers nothing.

```mermaid
flowchart TD
    A["make train EXP=model_versions/v1/id"] --> B{"load_experiment()<br/>layout, config keys,<br/>supported lib and estimator"}
    B -- "problems" --> R["REJECTED before training<br/>exit 2, nothing logged"]
    B -- "valid" --> C["load_features()<br/>read-only DuckDB over lakehouse/features<br/>snapshot_id from _manifest.json"]
    C --> D["mlflow.start_run(run_name = v1.id)<br/>in experiment = model_type"]
    D --> E["set contract tags, log params<br/>fit pipeline, log roc_auc, pr_auc, log_loss, brier"]
    E --> F["client.get_run(run_id)<br/>read the run BACK from the server"]
    F --> G{"check_tags() + run/experiment names<br/>+ required metrics"}
    G -- "missing or invalid" --> H["tag demo.contract_status=failed<br/>end_run(FAILED), exit 3<br/>no model registered"]
    G -- "ok" --> I["tag demo.contract_status=passed<br/>log_model (skops, trusted types)<br/>register new version of credit_default"]
    I --> J["exit 0: run_id, metrics, registered_version"]
```

The seeded run `v1.lgbm_missing_tags` exercises the left branch on purpose: same model and
metrics as `v1.lgbm_monotonic`, but its config's `demo_fault` drops `demo.data_snapshot` and
sets `demo.standard_version=0.9.0`.

---

## 4. Promoting a model (explicit-only, gated)

The only write the agent can trigger outside training. Four independent gates: the skill
is never auto-invoked, the script refuses runs that fail the contract, the default is a dry
run, and `make promote` is an `ask` rule, so Claude Code always shows a permission prompt.

```mermaid
sequenceDiagram
    actor U as You
    participant CC as Claude Code
    participant SK as Skill promote-model
    participant MCP as standards-mcp
    participant PERM as Permission prompt
    participant PR as make promote
    participant ML as MLflow registry

    U->>CC: /promote-model v1.lgbm_monotonic challenger
    Note over CC,SK: disable-model-invocation: true<br/>only an explicit /promote-model loads it
    CC->>SK: load procedure
    CC->>MCP: check_run_contract(run)
    MCP-->>CC: contract ok (else stop and explain)
    CC->>MCP: get_run(run)
    MCP-->>CC: FINISHED, registered version N
    CC->>MCP: compare_runs(run, baseline=v1.baseline)
    MCP-->>CC: deltas shown to you
    CC->>PERM: make promote RUN=id ALIAS=challenger
    PERM-->>U: allow? (ask rule)
    U-->>PERM: yes
    PERM->>PR: dry run
    PR->>ML: re-check contract, find version, read current alias
    PR-->>CC: would_set version N, previous version
    CC-->>U: confirm run, version and alias?
    U-->>CC: yes
    CC->>PERM: make promote ... CONFIRM=yes
    PERM-->>U: allow? (ask rule)
    U-->>PERM: yes
    PERM->>PR: promote --confirm
    PR->>ML: set_registered_model_alias(credit_default, challenger, N)
    PR-->>CC: status promoted
```

---

## 5. Read-only SQL over the lakehouse

`query_lakehouse(sql, max_rows)` in `mcp/standards_mcp/server.py` calls
`mle_starter.lakehouse.run_query`. Each guard would stop a write on its own; together they
mean a single bug does not open a write path.

```mermaid
flowchart TD
    Q["query_lakehouse(sql, max_rows)"] --> T{"typed params<br/>max_rows 1..500"}
    T -- "out of range" --> X0["MCP validation error"]
    T --> G1{"1 · leading keyword<br/>SELECT, WITH, FROM,<br/>DESCRIBE, SUMMARIZE"}
    G1 -- "anything else" --> X["query_rejected<br/>clear reason, ok=false"]
    G1 --> G2{"2 · deny-list outside string literals<br/>INSERT, UPDATE, DELETE, DROP, CREATE,<br/>COPY, ATTACH, INSTALL, LOAD, PRAGMA, SET, ..."}
    G2 -- "hit" --> X
    G2 --> G3{"3 · DuckDB parser<br/>extract_statements: exactly 1,<br/>type SELECT"}
    G3 -- "0, 2+ or not SELECT" --> X
    G3 --> S["4 · sandboxed connection<br/>in-memory, views raw + features,<br/>allowed_directories = lakehouse/,<br/>enable_external_access=false, config locked"]
    S --> L["SELECT * FROM (query) LIMIT cap+1<br/>cap = min(max_rows, standard.query_row_cap)"]
    L --> O["ok: columns, rows, row_count, truncated"]
    S -. "read_csv('/etc/hosts') etc." .-> X2["query failed: permission error"]
    M["5 · container mount<br/>repo is :ro for standards-mcp"] -.- S
```

Tests in `tests/test_sql_guard.py` and `tests/test_mcp_tools.py` cover each guard,
including `DROP`, `INSERT`, `COPY`, `ATTACH`, multi-statement, comment-hidden and
file-access attempts.

---

## 6. The loop: standard → MCP → skills → feedback

Why the order matters: the MCP can only expose evidence the standard makes comparable,
and skills can only encode a procedure the tools support. Real failures flow back as
eval cases and standard changes, which ship like a product (version bump, tests, PR).

```mermaid
flowchart LR
    PL["Platform<br/>MLflow + lakehouse/<br/>possible but inconsistent"] --> ST["Standard<br/>standard/standard.yaml v1.0.0<br/>makes runs comparable"]
    ST --> TR["make train<br/>enforces the contract,<br/>FAILS bad runs"]
    ST --> MC["standards-mcp<br/>exposes the evidence,<br/>read-only"]
    TR --> PL
    MC --> SK["Skills<br/>scaffold · review · explore · promote<br/>encode the procedure"]
    SK --> WK["Experiment · train · review · promote"]
    WK --> FB["Feedback<br/>review findings, failed runs,<br/>eval deltas (evals/)"]
    FB -- "new eval case" --> EV["evals/promptfooconfig.yaml"]
    FB -- "new rule, version bump, PR" --> ST
    EV -- "measures" --> SK
```

Where to go next: [`EXERCISES.md`](../EXERCISES.md) walks this loop yourself (add a tag →
bump the standard → new tool → new skill → new eval case).
