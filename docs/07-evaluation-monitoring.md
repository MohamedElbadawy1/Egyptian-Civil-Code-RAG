# 07 - Evaluation (RAGAS)

**Status:** Code done, not yet run - needs live OpenAI + Weaviate, which
this environment can't reach
**Date:** 2026-09-28

Scoped to evaluation only for now (RAGAS). Monitoring (Langfuse) and
guardrails from the original roadmap are deferred - see "Known issues /
next steps".

## What we built
- `eval/golden_qa.json` - a 10-question golden set (8 Arabic, 2 English)
  with `expected_articles` and a `ground_truth` answer per question.
  Grounded directly in article text we'd already read while debugging
  retrieval in docs/02 and docs/03 (articles 1, 6, 48, 110, 118, 802,
  806, 848, 949) - not sourced from a lawyer. Good enough to catch
  regressions; not a substitute for legal review.
- `src/agentic_rag/eval/golden_set.py` - loads/validates the golden set.
- `src/agentic_rag/eval/metrics.py` - `hit_at_k` / `precision_at_k`:
  deterministic retrieval metrics, no LLM judge needed. The quantified,
  reproducible version of the manual "is article X actually relevant"
  checks done by hand in docs/02 (the 802/949 mis-ranking).
- `src/agentic_rag/eval/run.py` - runs the golden set through the live
  `retrieve()` + `GenerationClient.answer()` pipeline, computes the
  retrieval metrics, optionally runs RAGAS's four LLM-judged metrics
  (faithfulness, answer relevancy, context precision, context recall),
  writes `reports/evaluation_latest.csv`, and logs everything to MLflow
  as an `evaluate_golden_set` run - same pattern as `index_corpus` in
  Step 05.
- `scripts/run_evaluation.py` - CLI entrypoint (`--no-ragas` to skip the
  slower/paid LLM-judge metrics and only get retrieval hit-rate).
- New `evaluate` stage in `dvc.yaml`.

## Why / decisions
- **Two metric families, not just RAGAS.** `hit_at_k`/`precision_at_k`
  are cheap, deterministic, and need no LLM call - a fast sanity check
  and the same thing we were eyeballing by hand before. RAGAS's four
  metrics add LLM-judged quality (does the answer actually follow from
  the context, is it relevant to the question) that set-overlap alone
  can't capture. Both get logged so a hit-rate regression and a
  faithfulness regression are both visible, not just one or the other.
- **Golden set grounded in article text we'd actually read**, not
  invented from general legal knowledge - every `ground_truth` traces
  back to text seen verbatim earlier in this project (docs/02's manual
  retrieval check, docs/03's `/ask` test). Keeps the eval set honest
  about what it's actually testing.
- **RAGAS import is lazy** (inside `_run_ragas`, not at module top level)
  so `eval/run.py` and `eval/metrics.py` stay importable - and testable -
  without `ragas`/`datasets` installed. Only `scripts/run_evaluation.py`
  actually needs them.
- **`reports/evaluation_latest.csv` is `cache: false`** in `dvc.yaml`,
  same reasoning as the processed corpus in Step 05: it's small, and
  something a person (or CI) might want to just look at in git history
  rather than pull from a DVC remote.
- **Logged to MLflow, not just written to CSV.** Consistent with Step 05
  - the point is comparing evaluation runs over time (did the heading-
  tracker fix actually move `hit_rate`? did switching embedding models
  help faithfulness?), not just producing one static report.

## How to run
```bash
uv sync --extra dev
uv run python -m scripts.run_evaluation
# or, to skip RAGAS's LLM-judge metrics (faster, no extra OpenAI cost):
uv run python -m scripts.run_evaluation --no-ragas

# or as a DVC stage:
uv run dvc repro evaluate

# view results
uv run mlflow ui   # look for the "evaluate_golden_set" run
```

## Results / validation
**Not yet run for real** - `run_evaluation()` needs a live Weaviate index
(Step 05's `build_index`) and live OpenAI calls for both generation and
RAGAS's LLM judge, none of which this environment can reach. What's
validated so far:
- `tests/test_eval_metrics.py` (6 tests) and `tests/test_golden_set.py`
  (2 tests) passing - pure logic, no network.
- All new modules compile cleanly; `dvc.yaml`'s new `evaluate` stage
  parses correctly.

Run `uv run python -m scripts.run_evaluation` for real and report back:
`hit_rate`, `mean_precision`, and the four RAGAS scores, so this doc can
be updated with actual numbers - particularly whether `hit_rate` reflects
the 802/949-style mis-ranking documented in docs/02, now measured across
10 questions instead of one.

## Known issues / next steps
- **Monitoring (Langfuse) and guardrails are deferred, not done.** The
  original roadmap bundled them into this step; scoped this step to
  evaluation only to keep it reviewable as one change. Worth its own
  step once there's a sense of what evaluation actually reveals.
- Only 10 questions in the golden set, all single-hop (one clearly
  correct article per question) - doesn't yet cover multi-article
  questions, deliberately out-of-scope questions (testing that the
  system says "I don't know" rather than hallucinating), or repealed-
  article edge cases.
- `context_recall` needs a `ground_truth` that's genuinely derivable from
  the retrieved contexts - our short one-sentence ground truths may
  score lower than a more complete reference answer would, independent
  of actual retrieval quality. Worth revisiting once real scores are in.
- No CI integration yet (running RAGAS costs real OpenAI credits per
  push, so this isn't wired into `ci.yml` the way `pytest`/`ruff` are) -
  intentionally a manual/scheduled step for now.
