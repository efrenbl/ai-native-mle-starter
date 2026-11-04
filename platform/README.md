# platform/ — layer 1: where the work lives

- **MLflow** (`ghcr.io/mlflow/mlflow:v3.17.2`): tracking server + model registry, sqlite
  backend and served artifacts on Docker volumes (`mlflow-db`, `mlflow-artifacts`).
  UI at <http://localhost:5050>.
- **Lakehouse stand-in**: partitioned parquet in `../lakehouse/`, queried with DuckDB.
- **App image** (`Dockerfile`): one image, `python:3.12.16-slim-bookworm` + the fully pinned
  lock in `requirements/app.txt`, used by both the `trainer` job and the `standards-mcp`
  server. The repo is mounted at `/workspace`, so code changes need no rebuild.
- **Test image**: the app image + `requirements/dev.txt` (full `mlflow` for a throwaway
  sqlite store, pytest, ruff).

Locks are compiled with uv from the `.in` files:

```bash
uv pip compile --universal --python-version 3.12 platform/requirements/app.in -o platform/requirements/app.txt
uv pip compile --universal --python-version 3.12 platform/requirements/dev.in -o platform/requirements/dev.txt
```

Telemetry is off everywhere (`MLFLOW_DISABLE_TELEMETRY=true`, `DO_NOT_TRACK=true`), and
after `make up` nothing in the stack needs the internet.
