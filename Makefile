# AI-native ML engineering starter. Run `make help` for the list of targets.
# Every write to MLflow or the lakehouse goes through a target here, never through an MCP tool.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
export HOST_UID := $(shell id -u)
export HOST_GID := $(shell id -g)
RUN_JOB := $(COMPOSE) --profile jobs run --rm trainer

.PHONY: help up down seed train scaffold promote test skills doctor reset status demo-reset

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36mmake %-16s\033[0m %s\n", $$1, $$2}'

up: skills ## Build (if needed) and start mlflow + standards-mcp, then wait until healthy
	$(COMPOSE) up -d --build --wait mlflow standards-mcp
	@echo ""
	@echo "MLflow UI:      http://localhost:$${MLFLOW_PORT:-5050}"
	@echo "standards-mcp:  http://localhost:$${STANDARDS_MCP_PORT:-8765}/mcp"
	@echo "Next: make seed"

down: ## Stop the stack (keeps data volumes)
	$(COMPOSE) --profile jobs --profile test --profile gateway down

seed: ## Generate the synthetic lakehouse and log the 3 demo runs (idempotent)
	$(RUN_JOB) python -m mle_starter.seed

train: ## Train one experiment: make train EXP=model_versions/v1/<experiment_id>
	@test -n "$(EXP)" || { echo "usage: make train EXP=model_versions/<model_version>/<experiment_id>"; exit 2; }
	$(RUN_JOB) python -m mle_starter.train "$(EXP)"

scaffold: ## Create an experiment from _TEMPLATE: make scaffold MV=v1 EXP=my_experiment
	@test -n "$(MV)" -a -n "$(EXP)" || { echo "usage: make scaffold MV=v1 EXP=<experiment_id>"; exit 2; }
	$(RUN_JOB) python -m mle_starter.scaffold "$(MV)" "$(EXP)"

promote: ## Set a registry alias (dry run unless CONFIRM=yes): make promote RUN=<run_id> ALIAS=challenger
	@test -n "$(RUN)" -a -n "$(ALIAS)" || { echo "usage: make promote RUN=<run_id> ALIAS=<challenger|champion> [CONFIRM=yes]"; exit 2; }
	$(RUN_JOB) python -m mle_starter.promote --run-id "$(RUN)" --alias "$(ALIAS)" $(if $(filter yes,$(CONFIRM)),--confirm,)

test: ## Run ruff, skill validation and pytest inside the test image
	$(COMPOSE) --profile test build test
	$(COMPOSE) --profile test run --rm --no-deps test bash -c "ruff check . && ruff format --check . && python scripts/validate_skills.py && pytest -q"

skills: ## Symlink skills/ into .claude/skills and .agents/skills (safe to re-run)
	@./scripts/install-skills.sh

doctor: ## Check Docker, ports, MLflow, the MCP endpoint and the Claude Code CLI
	@./scripts/doctor.sh

status: ## Show container status
	$(COMPOSE) ps

reset: ## DESTRUCTIVE: stop everything, delete MLflow volumes and generated parquet
	$(COMPOSE) --profile jobs --profile test --profile gateway down -v
	rm -rf lakehouse/raw lakehouse/features lakehouse/_manifest.json
	@echo "Reset done. Run: make up && make seed"

demo-reset: ## DESTRUCTIVE: clean slate for the live demo (drops rehearsal experiments, reseeds, runs doctor)
	@# Only removes UNTRACKED folders under model_versions/ (rehearsal experiments); tracked edits are kept.
	@git clean -fd -- model_versions
	$(MAKE) reset
	$(MAKE) up
	$(MAKE) seed
	$(MAKE) doctor
