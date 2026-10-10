# 10 — Query Expansion (Legal Terminology Rewriting)

## Motivation
docs/09-hybrid-search.md found that hybrid search (BM25 + vector fusion)
improved aggregate retrieval metrics but did NOT fix the original
motivating failure case: a real-estate-registration question using
"تسجيل" never retrieved Article 934, because the article's actual text
only says "الشهر العقاري" (real-estate publication) — a genuine
vocabulary gap that BM25 cannot bridge, since BM25 can only match terms
literally present in a document.

## Implementation
Added `rag/query_expansion.py::expand_query()`, an LLM call (gpt-5-mini)
that rewrites the user's question by adding formal legal terminology
alongside the original wording, before the query reaches either the BM25
or vector side of hybrid search. Wired through `pipeline.retrieve()`
(`expand` flag) and the eval CLI (`--expand`), composable with
`--hybrid`.

## Results: 40-question golden set

| Metric | Baseline (vector) | Hybrid | Hybrid + Expand |
|---|---|---|---|
| hit_rate | 0.763 (29/38) | 0.816 (31/38) | **0.868 (33/38)** |
| mean_precision | 0.153 | 0.163 | **0.184** |
| abstention_rate | 1.0 | 1.0 | 1.0 |
| ragas_faithfulness | 0.940 | 0.927 | **0.959** |
| ragas_answer_relevancy | 0.692 | 0.742 | **0.787** |
| ragas_context_precision | 0.872 | 0.846 | **0.893** |
| ragas_context_recall | 0.896 | 0.893 | **0.954** |

Hybrid + expand improves on every single metric versus both baseline and
hybrid-only, with no regressions. No RAGAS job timeouts on this run,
unlike one earlier run (noted in docs/09), so all 160 judged samples are
represented.

## Direct verification of the original failure case
Re-tested the exact motivating query at the production `top_k=5`:

```
Query: "ما أثر عدم تسجيل العقار على انتقال الملكية؟"
use_hybrid=True, alpha=0.5, expand=True, top_k=5

934  0.808   <== HERE (rank #1)
1054 0.764
1072 0.670
1071 0.600
1058 0.570
```

Article 934 now ranks **#1** at the default top_k=5 — previously absent
even from the top 20 with hybrid search alone, and ranked #18/50 with
vector-only search before that. This closes the original investigation
that started with a live user-reported failure on a property-registration
question (see docs/01 and docs/07 for the earlier heading-parser bugs
that were ruled out as the cause before the vocabulary gap was found).

Confirmed end-to-end through the actual frontend (not just the retrieval
script in isolation): asking the registration-ownership-transfer question
live returns an answer that cites and reasons from Article 934 directly,
with "المواد المستشهد بها" showing article 934 as the top-scoring citation
(0.97 after the follow-up precision tuning — see below).

## Making it the default
`pipeline.retrieve()`'s `use_hybrid` and `expand` parameters default to
`True` as of this step (previously both defaulted to `False` and had to
be passed explicitly). The eval CLI is unaffected, since
`scripts/run_evaluation.py` always passes these flags explicitly from
`--hybrid`/`--expand` rather than relying on the function defaults — so
historical before/after comparisons in this doc and docs/09 remain
reproducible regardless of this default change.

## Decision
Adopting hybrid search (alpha=0.5) + query expansion as the default
retrieval configuration used by the API and frontend.
