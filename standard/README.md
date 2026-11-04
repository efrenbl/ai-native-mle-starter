# standard/ — layer 2: the versioned ML standard

`standard.yaml` is the one file that says what "a correct experiment" means here:

- **layout**: `model_versions/<model_version>/<experiment_id>/config.yaml`, created from `_TEMPLATE/`;
- **libraries**: scikit-learn and LightGBM only, with the allowed estimators;
- **tracking**: one MLflow experiment per model type, run name `<model_version>.<experiment_id>`;
- **tag contract**: six required `demo.*` tags with patterns or allowed values;
- **registry**: which aliases may be set;
- **lakehouse**: table globs and the SQL row cap.

Code reads it, never copies it: `src/mle_starter/standard.py` is the only place the rules
are interpreted, and training, the MCP server, promotion and tests all import it.

## Versioning

| Bump | When | Example |
|---|---|---|
| MAJOR | someone has to change how they work | new required tag, renamed field, dropped library |
| MINOR | additive, backwards compatible | new optional estimator |
| PATCH | wording only | description text |

`demo.standard_version` on a run must share the current MAJOR, so a MAJOR bump makes
older runs fail `check_run_contract` until they are re-trained: that is the point.

Claude Code is denied edits to `standard.yaml` (`.claude/settings.json`). A human changes
it in a PR; the agent can propose the diff.
