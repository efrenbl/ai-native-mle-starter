# ai-native-mle-starter

Demo repo for AI-native ML engineering: an agent works on ML experiments through
**skills** that call **read-only MCP tools**, which expose a **versioned standard**
on top of a small **platform** (MLflow + parquet queried with DuckDB). All data is synthetic.

## The standard in five lines (standard/standard.yaml, v1.0.0)
1. Experiments live in `model_versions/<model_version>/<experiment_id>/config.yaml`; start from `_TEMPLATE/`.
2. Supported libraries: scikit-learn and LightGBM only (estimators listed in the standard).
3. One MLflow experiment per model type; run name = `<model_version>.<experiment_id>`.
4. Every run logs six `demo.*` tags; training reads them back and FAILS the run if any is missing or invalid.
5. Registry aliases (`challenger`, `champion`) only on runs that pass the contract.

## Golden rules
- **Read-only by default.** Use the `standards-mcp` tools to inspect; they cannot write.
- **Never edit `standard/`** without bumping its `version` (you are denied edits to `standard/standard.yaml`; propose the change to the human instead).
- **All training goes through `make train EXP=...`**; all promotion through `make promote ...` (asks for permission).
- Never edit `lakehouse/` (generated, read-only), never hand-edit MLflow tags, never add libraries outside the standard.
- Cite run IDs for every claim about a run.

## Useful commands
`make doctor` · `make scaffold MV=v1 EXP=<id>` · `make train EXP=model_versions/v1/<id>` · `make test`

Skills: `scaffold-experiment`, `review-experiment`, `explore-data`, `promote-model` (explicit-only, `/promote-model`).
