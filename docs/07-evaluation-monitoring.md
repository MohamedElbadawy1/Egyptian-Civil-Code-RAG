# 07 - Evaluation (RAGAS)

**Status:** Done - ran end-to-end against the live system, real results below
**Date:** 2026-09-30

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
`tests/test_eval_metrics.py` (6 tests) and `tests/test_golden_set.py` (2
tests) passing - pure logic, no network. Full suite: 27/27, `ruff check`
clean.

Ran `uv run python -m scripts.run_evaluation` for real against the live
system (`top_k=5`, all 10 golden questions, RAGAS enabled):

| Metric | Score |
|---|---|
| `hit_rate` | **0.80** (8/10) |
| `mean_precision` | 0.16 |
| `ragas_faithfulness` | 0.81 |
| `ragas_answer_relevancy` | 0.83 |
| `ragas_context_precision` | 0.90 |
| `ragas_context_recall` | 0.90 |

**Read `mean_precision` relative to its ceiling, not out of 1.0.** Every
golden question has exactly one `expected_articles` entry, retrieved
against `top_k=5` - the best possible `precision_at_k` per question is
therefore `1/5 = 0.2`, not `1.0`. A score of 0.16 is ~80% of the
achievable maximum (matches `hit_rate` closely, as expected: every hit
scored exactly 0.2, every miss scored 0.0). Worth normalizing by the
ceiling in a future pass so the raw number doesn't mislead anyone
skimming this table.

This is a meaningfully better picture than the single-question manual
check in docs/02 (which found 3/5 relevant in an ad-hoc test) suggested -
across 10 questions, retrieval hits 8/10, and RAGAS's faithfulness/
relevancy/context scores are all in the 0.8-0.9 range.

**The two misses are informative, not just failures:**
- `cap-02` ("can a person waive their own legal capacity?", expecting
  article 48) - article 48 never appeared in the retrieved set at all.
  Notably, the model **did not hallucinate an answer** - it explicitly
  said the provided articles don't contain enough information, exactly
  the behavior the Step 03 system prompt asks for when context is
  insufficient. A retrieval failure that doesn't become a generation
  failure.
- `en-01` ("what is the general rule for how legal provisions apply?",
  expecting article 1) - article 1 never retrieved, but the articles that
  *were* retrieved (2, 23 - rules about repeal and precedence between
  laws) are genuinely on-topic. This looks more like a golden-set design
  issue (article 1 is a very short, generic statement; 2/23 may be
  equally or more defensible answers to this phrasing) than a retrieval
  bug - worth rewording this question rather than treating it as a
  system failure.

## Known issues / next steps
- **Two bugs hit and fixed while first running this for real:**
  1. `ragas` does an unconditional top-level import of `ChatVertexAI`
     from `langchain-community`, which removed that class in `0.4.2` -
     broke `import ragas` entirely regardless of provider used. Fixed by
     pinning `langchain-community<0.4.2` as a dev dependency.
  2. `_run_ragas()` originally called `.items()` on the `EvaluationResult`
     `evaluate()` returns - not a stable API across ragas versions. Fixed
     by using `.to_pandas()` and averaging each metric column instead.
- **`mean_precision`'s ceiling is `1/top_k` per question** (see above) -
  worth normalizing in a future pass.
- `en-01`'s expected article is arguably under-specified (see above) -
  reword or accept articles 2/23 as alternate correct answers.
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
