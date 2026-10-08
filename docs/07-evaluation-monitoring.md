# 07 - Evaluation (RAGAS)

**Status:** Done - 40-question golden set run end-to-end against the live
system, real results below, two new findings worth acting on
**Date:** 2026-10-02

Scoped to evaluation only for now (RAGAS). Monitoring (Langfuse) and
guardrails from the original roadmap are deferred - see "Known issues /
next steps".

## What we built
- `eval/golden_qa.json` - **40 questions** (grown from an initial 10),
  grounded in article text read directly from the real corpus (verified
  with a script, not assumed) - covering direct questions, paraphrased
  restatements, realistic scenarios, multi-hop questions needing more
  than one article (e.g. "does property transfer on contract alone or
  does it need registration, and what must the seller do?" -> articles
  932, 934, 428), English questions, and two deliberately out-of-scope
  questions (criminal law, immigration law) that should make the system
  abstain rather than hallucinate. Not sourced from a lawyer - good
  enough to catch regressions, not a substitute for legal review.
- `GoldenExample.expect_no_answer` (default `False`) flags the
  out-of-scope questions - `eval/run.py` scores these separately (see
  below) instead of against `hit_at_k`/`precision_at_k`, which don't make
  sense when there's no correct article to retrieve.
- `metrics.contains_abstention()` - a substring-heuristic check for
  whether an answer looks like a refusal (matches the system prompt's own
  "say so explicitly" phrasing from Step 03) rather than a guess. Not a
  classifier, a directional signal - see its docstring.
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
- **Golden set grounded in article text actually read from the corpus**
  (verified with a script each time, not assumed or taken on faith from
  an AI's claim) - not invented from general legal knowledge. Keeps the
  eval set honest about what it's actually testing.
- **Expanded 10 -> 40 questions, across six question types** (direct,
  paraphrased, scenario-based, multi-hop/multi-article, English,
  deliberately-out-of-scope) after a third-party review of the repo
  pointed out the original 10 were narrow (mostly single-hop, direct
  phrasing). The multi-hop questions in particular are only meaningful
  because they're grounded in real cross-references in the corpus - e.g.
  `multihop-01` needs articles 932 (ownership transfers by contract),
  934 (immovable property specifically needs registration), and 428
  (seller's obligation to effect the transfer) together, verified against
  the actual corpus text rather than assumed from the question design.
- **`expect_no_answer` questions scored separately, not folded into
  `hit_at_k`.** There's no "correct article" for a criminal-law or
  immigration-law question against the Civil Code - the correct system
  behavior is abstaining, which `contains_abstention()`'s substring check
  scores as `abstention_rate` instead.
- **Fixed a real bug a third-party review caught**: `eval/run.py` built
  RAGAS's `contexts` with `a.get("text_ar") or a.get("text_en") or ""` -
  since every article has Arabic text, this *always* picked Arabic, even
  for the English golden questions (`en-01`, `en-02`), so RAGAS was
  silently judging faithfulness/context metrics for English answers
  against Arabic-only context. Fixed by reusing
  `generation.format_article_block()` (both languages, exactly what the
  generator actually saw) instead of re-deriving a different, buggy
  single-language context independently. Verified the fix with a test
  asserting the eval context and the generation context are built
  identically (`tests/test_generation.py`).
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
`tests/test_eval_metrics.py` (9 tests) and `tests/test_golden_set.py` (5
tests) passing - pure logic, no network. Full suite: 37/37, `ruff check`
clean.

### 40-question results (current)
Ran `uv run python -m scripts.run_evaluation` for real against the live
system (`top_k=5`, all 40 golden questions, RAGAS enabled):

| Metric | Score | vs. 10-question baseline |
|---|---|---|
| `hit_rate` | **0.79** (30/38 retrieval questions) | 0.80 - essentially held up |
| `mean_precision` | 0.158 | 0.16 - essentially unchanged |
| `abstention_rate` | **1.00** (2/2) | n/a - new metric |
| `ragas_faithfulness` | **0.96** | 0.81 - notably higher, likely thanks to the context-bug fix making the judged context actually match what the generator saw |
| `ragas_answer_relevancy` | 0.71 | 0.83 - lower, expected: the 40-question set includes scenarios/paraphrases/multi-hop questions that are harder to answer cleanly than the original mostly-direct 10 |
| `ragas_context_precision` | 0.88 | 0.90 - close |
| `ragas_context_recall` | 0.90 | 0.90 - unchanged |

`hit_rate` and `mean_precision` held up well across 4x more questions and
6 question types, which is a meaningfully stronger signal than the
original 10 gave - this looks like a real, stable number rather than an
artifact of a small or easy sample. `abstention_rate = 1.0` is a genuinely
good result: both deliberately-out-of-scope questions (a criminal-law
question, an immigration question) got an explicit refusal instead of a
hallucinated answer.

**Two new findings from the larger set, both more actionable than
anything the original 10 surfaced:**

1. **Paraphrase inconsistency - the same legal question, worded two
   ways, got contradictory answers.** `contract-02`
   ("هل يجوز التعامل في تركة شخص لا يزال على قيد الحياة؟") correctly
   hedged: "لا يمكن الجزم ... لا توجد معلومات كافية". Its paraphrase,
   `contract-05-paraphrase` ("هل يصح التعامل في ميراث شخص لا يزال
   حيًا؟" - same question, different wording), confidently answered
   "نعم يجوز", reasoning from retrieved articles (916, 917 - about
   death-bed gifts treated as bequests) that don't actually answer the
   question asked. This isn't a retrieval ranking problem so much as an
   **inconsistency** problem: the correct behavior (abstain, as
   `contract-02` did) depends on which of two near-identical phrasings
   was used. Worth a dedicated regression test once this is looked at
   further - `tests/test_golden_set.py` already keeps both IDs so this
   pair stays easy to spot in future report diffs.
2. **`multihop-01` missed all three expected articles.** The question
   needing articles 932, 934, and 428 together retrieved none of
   them - instead articles like 204 and 418 (genuinely related, but not
   the ones the golden set expects) came back. Either retrieval
   genuinely struggles with compound/multi-hop questions more than
   single-fact ones, or this specific golden question is phrased in a
   way that pulls toward adjacent-but-different articles. Worth checking
   after a few more multi-hop examples before concluding which.

### Original 10-question results (superseded, kept for history)
Ran for real against the live system (`top_k=5`, all 10 golden questions,
RAGAS enabled), before the golden set was expanded and before the
contexts bug was fixed:

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
- **Three bugs hit and fixed so far:**
  1. `ragas` does an unconditional top-level import of `ChatVertexAI`
     from `langchain-community`, which removed that class in `0.4.2` -
     broke `import ragas` entirely regardless of provider used. Fixed by
     pinning `langchain-community<0.4.2` as a dev dependency.
  2. `_run_ragas()` originally called `.items()` on the `EvaluationResult`
     `evaluate()` returns - not a stable API across ragas versions. Fixed
     by using `.to_pandas()` and averaging each metric column instead.
  3. RAGAS `contexts` silently defaulted to Arabic-only even for English
     questions (see "Why" above) - fixed by reusing
     `format_article_block()` from `api/generation.py`.
- **`mean_precision`'s ceiling is `1/top_k` per question** (see the
  original-results section above) - worth normalizing in a future pass.
- `en-01`'s expected article is arguably under-specified (article 1 is a
  short, generic statement; articles 2/23 may be equally defensible) -
  reword or accept them as alternate correct answers once re-run.
- `contains_abstention()` is a substring heuristic, not a classifier -
  will miss paraphrased refusals and could false-positive. Treat
  `abstention_rate` as directional, not precise.
- `context_recall` needs a `ground_truth` that's genuinely derivable from
  the retrieved contexts - our short one-sentence ground truths may
  score lower than a more complete reference answer would, independent
  of actual retrieval quality. Worth revisiting once real scores are in.
- **Monitoring (Langfuse) and guardrails are deferred, not done.** The
  original roadmap bundled them into this step; scoped this step to
  evaluation only to keep it reviewable as one change. Worth its own
  step once there's a sense of what evaluation actually reveals.
- No CI integration yet (running RAGAS costs real OpenAI credits per
  push, so this isn't wired into `ci.yml` the way `pytest`/`ruff` are) -
  intentionally a manual/scheduled step for now.
- A third-party review also suggested hybrid (BM25 + vector) search,
  a reranking pass, and query decomposition for multi-hop questions.
  With the 40-question results in hand, `hit_rate`/`mean_precision`
  holding steady suggests retrieval itself isn't badly broken - but the
  paraphrase-inconsistency and multihop-01 findings above are concrete
  enough to act on now rather than needing another evaluation round
  first. Weaviate (already in use) supports hybrid search natively if
  this turns out to be a retrieval problem rather than a generation
  consistency problem - no new search engine required.
- **Next concrete step:** investigate the `contract-02` /
  `contract-05-paraphrase` inconsistency specifically - check whether
  the two questions' embeddings actually retrieve different articles
  (a retrieval problem) or retrieve the same ones but the model
  reasons about them differently (a generation/prompt problem). That
  distinguishes which half of the pipeline to fix.

## Fixing the abstention_rate measurement (2026-10-08)

### Problem
After expanding the golden set to 40 questions, `abstention_rate` dropped
from 1.0 to 0.5, even though the model was actually abstaining correctly
on `noanswer-01` (the general-theft-penalty question). The issue wasn't
the model — it was the measurement itself. `contains_abstention()` relied
on substring matching against a fixed list of refusal phrases.

### Investigation
Across three consecutive eval runs, the model's abstention for the same
question came back worded three different ways, all with the same
meaning but different verbs:
1. "لا يمكن تحديد عقوبة السرقة العامة" ("cannot determine the penalty")
2. "لا يمكنني بيان عقوبة السرقة" ("cannot state the penalty")
3. "لا تورد نصاً يحدد عقوبة جريمة السرقة العامة صراحةً" ("[the excerpts] do not provide text that explicitly specifies the penalty")

Each attempt to widen the marker list caught the previous phrasing but
missed the new one — a structural whack-a-mole problem with substring
matching, not a gap that more markers could close.

### Fix
Replaced the deterministic substring check with an LLM-judge function
(`contains_abstention_llm`), used only on the `expect_no_answer`
questions (2 of 40), so the added cost is negligible. It asks the model
a direct yes/no question — is this answer a genuine abstention or a
substantive answer? — which generalizes across phrasing instead of
relying on a hardcoded list.

The old `contains_abstention()` substring heuristic was kept as a fast
fallback but is no longer used to compute the official `abstention_rate`.

### Result
| Metric | Before fix | After fix |
|---|---|---|
| abstention_rate | 0.5 | **1.0** |
| hit_rate | 0.763 | 0.763 (unaffected, as expected) |
| mean_precision | 0.153 | 0.153 |
| ragas_faithfulness | — | 0.940 |
| ragas_answer_relevancy | — | 0.692 |
| ragas_context_precision | — | 0.872 |
| ragas_context_recall | — | 0.896 |

This run (MLflow run `7a310b17109c4df1a9f2700c2a960a5d`) is adopted as
the official **pre-hybrid-search baseline**, saved to
`reports/evaluation_before_hybrid.csv`.