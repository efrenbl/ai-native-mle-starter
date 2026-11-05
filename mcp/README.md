# mcp/ — layer 3: MCP servers that expose the standard

## standards-mcp (this folder)

Written with the official MCP Python SDK (`FastMCP`, `mcp==1.30.0`), served over
streamable HTTP at `http://localhost:8765/mcp` by the `standards-mcp` compose service.
Claude Code finds it through the project-scoped `.mcp.json` at the repo root.

| Tool | Reads | Returns |
|---|---|---|
| `get_standard` | `standard/standard.yaml` | the standard as JSON |
| `list_experiments` | `model_versions/` + MLflow | local folders (with problems) and MLflow runs (with contract status) |
| `get_run` | MLflow | params, metrics, tags, registered versions of one run (id or run name) |
| `compare_runs` | MLflow | metrics side by side + delta vs a named baseline, direction-aware |
| `check_run_contract` | MLflow | `missing` and `invalid` required tags, naming checks |
| `query_lakehouse` | `lakehouse/` | one read-only DuckDB query, row-capped |

Every tool is annotated `readOnlyHint: true`, has typed parameters, and returns
`{"ok": true, ...}` or `{"ok": false, "error": {"code", "message", "hint"?}}`.

### Why read-only holds

- There is no write tool. Logging, tagging, registering and promoting happen only in
  `make train` / `make promote`, which run in a separate container and show a
  permission prompt in Claude Code.
- The container mounts the repo **read-only** (`.:/workspace:ro`).
- `query_lakehouse` checks SQL three ways: DuckDB's own parser must see exactly one
  `SELECT` statement; a keyword deny-list blocks `INSERT`/`COPY`/`ATTACH`/`DROP`/`PRAGMA`/…;
  and the DuckDB connection is in-memory, limited to the lakehouse directory, with its
  configuration locked. Tests cover each guard.
- Honest limit: MLflow itself has no auth in this demo, so "read-only" is enforced by
  the tool surface, not by credentials. In a real platform each user's MCP session
  carries **their own** read-only credentials, never a shared token.

### Why our own `query_lakehouse` instead of the community DuckDB MCP

`mcp-server-motherduck` is a good read-only-by-default option. We chose a tool inside
`standards-mcp` because: it reads the parquet directly (no `.duckdb` file to build or
keep in sync), it needs no extra image or Node/uv on the host, the row cap comes from the
standard, and the SELECT-only guard is our own code with our own tests, which is the
point of the demo. Swapping in the community server is a good exercise.

### Verify it

```bash
make doctor                                   # sends a real MCP initialize request
claude mcp list                               # from the repo root: standards-mcp ✔ Connected
uv run --with mcp==1.30.0 scripts/verify_mcp.py   # calls every tool over HTTP
```

### SDK version note

`mcp` 2.x renamed `FastMCP` to `MCPServer` (`from mcp.server.mcpserver import MCPServer`).
This repo pins the maintained 1.x line (`1.30.0`), which keeps `FastMCP`, because it is the
API most docs and examples still show. Migrating is mostly the import and constructor.

### Audit log

Every tool call writes one line to the server's stderr: tool, arguments (truncated),
`ok`, the error code if any, and the time it took. Follow it with `make logs-mcp`:

```
19:02:11 audit tool=check_run_contract args={"run":"v1.lgbm_missing_tags"} ok=true 41ms
19:02:12 audit tool=query_lakehouse args={"sql":"DROP VIEW features"} ok=false error=query_rejected 1ms
```

`ok` is whether the tool answered, not whether the run passed the contract. Calls that fail
MCP argument validation (e.g. `max_rows=9999`) are rejected before the tool runs and do not
appear. Health probes and per-request transport lines are filtered out.

## Optional: the reference `memory` server

JSON has no comments, so the optional memory server lives in
`mcp/memory.mcp.json.example` instead of a commented block in `.mcp.json`.
To enable it (needs Node.js):

```bash
claude mcp add --scope project memory -- npx -y @modelcontextprotocol/server-memory@2026.8.31
```

That writes the entry into `.mcp.json` (or copy the `memory` block from the example file,
which also sets `MEMORY_FILE_PATH=.memory/memory.jsonl`; `.memory/` is git-ignored).
TODO(verify): whether a relative `MEMORY_FILE_PATH` resolves against the project directory
in every client; use an absolute path if your client starts servers elsewhere. It stores a small knowledge graph in a local
JSON file: good for "remember our conventions" across sessions, nothing team-wide.
