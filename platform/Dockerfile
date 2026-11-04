# One image for the two Python services (trainer + standards-mcp), so the
# footprint stays small and both run the exact same pinned dependencies.
# Code is NOT baked in: docker-compose mounts the repo at /workspace, so editing
# src/, mcp/ or model_versions/ needs no rebuild (restart standards-mcp to reload).

FROM python:3.12.16-slim-bookworm AS app

# libgomp1: OpenMP runtime that LightGBM links against.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/workspace/src:/workspace/mcp \
    MLE_REPO_ROOT=/workspace \
    MLFLOW_DISABLE_AGENT_HINT=1 \
    HOME=/tmp

COPY platform/requirements/app.txt /tmp/requirements/app.txt
# --no-deps: app.txt is a complete, fully pinned lock (compiled with uv), so pip
# installs exactly what is listed and nothing else.
RUN pip install --no-deps -r /tmp/requirements/app.txt

WORKDIR /workspace

# Test image: app + full mlflow (sqlite tracking store for tests) + pytest + ruff.
FROM app AS test
COPY platform/requirements/dev.txt /tmp/requirements/dev.txt
RUN pip install --no-deps -r /tmp/requirements/dev.txt
