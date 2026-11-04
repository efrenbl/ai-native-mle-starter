# Skill evals (optional module)

This module measures whether the `review-experiment` skill makes the model better at
the review, on top of what the model already does on its own. The core demo does not
need it.

| What | How |
|---|---|
| Comparison | Every case runs twice on the same model: once **without** the skill (`baseline`), once **with** it (`with_skill`). The **delta** is the signal. |
| Evidence | Deterministic assertions first: must name the missing tag, must cite a run ID, must not claim it wrote anything, must not just dump the raw evidence. |
| Guardrail | `llm-rubric` is a secondary check, reported on its own row so judge noise cannot hide a deterministic regression. |
| Model | Calls go through a local LiteLLM gateway to the alias `eval-model`, which points at a **dated** model ID (`evals/litellm.yaml`). |
| Inputs | `fixtures/review_v1_evidence.json` holds real `standards-mcp` tool outputs captured from `make seed`, so the eval tests the procedure, not tool calling. |

## Why pin a dated model ID

If `eval-model` pointed at an alias that moves, a score change could be a skill
regression or a silent model update, and you could not tell which. With a dated ID,
the model stays the same across runs. Moving to a new model is a deliberate step:
add a second alias, run both, compare, then repoint `eval-model` and treat the new
numbers as the new baseline. Pinning the *alias* is not enough; the alias must point
at a dated model.

`drop_params: true` in the gateway config absorbs request parameters a newer model
rejects (for example a default `temperature`), so clients do not each have to change.

## Run it (paid calls, your own key)

```bash
cp .env.example .env                 # set ANTHROPIC_API_KEY and LITELLM_MASTER_KEY
docker compose --profile gateway up -d gateway
set -a; source .env; set +a
npx promptfoo@0.125.1 eval -c evals/promptfooconfig.yaml -o evals/output/results.json
python3 evals/delta.py evals/output/results.json
docker compose --profile gateway stop gateway
```

Requires Node.js (for `npx`) and Python 3 on the host. Cost: 3 cases × 2 prompts,
plus one rubric grading call per case and prompt, on `eval-model`.

Example `delta.py` output shape:

```
check                     baseline  with_skill    delta
case_pass                      33%        100%    +67pp
deterministic                  80%        100%    +20pp
rubric                         67%        100%    +33pp
  names_missing_tag            100%        100%     +0pp
  ...
```
(The numbers above only show the format; run it to get yours.)

## Lessons this module already taught

- **Check the checker.** A dry run with promptfoo's `echo` provider (free, no model
  call) showed two bugs before any money was spent: JavaScript regexes reject the
  inline `(?i)` flag, so two assertions could never pass; and an answer that just
  echoes the evidence passed every other deterministic check. Hence the `not_a_dump`
  canary. Try it yourself:
  `LITELLM_MASTER_KEY=x npx promptfoo@0.125.1 eval -c evals/promptfooconfig.yaml -r echo`
  (rubric rows fail with a connection error while the gateway is down; that is expected).
- **Keep the judge out of the gate.** The rubric is a secondary signal. A judge with a
  small token budget can return empty answers on reasoning models and score them 0.
