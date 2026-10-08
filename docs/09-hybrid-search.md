# 09 — Hybrid Search (BM25 + Vector Fusion)

## Motivation
Investigating a real retrieval failure (a live question about real-estate
registration never retrieved Article 934) traced the root cause to a
vocabulary/terminology gap between how users phrase questions ("تسجيل")
and how the Civil Code's actual text is worded ("الشهر العقاري"). Article
934 ranked #18/50 for a vector-only query -- not missing from the index,
just outranked. The working hypothesis was that adding BM25 (keyword)
scoring alongside vector similarity, via Weaviate's native hybrid search,
would help surface articles with exact keyword overlap that pure vector
search under-ranks.

## Implementation
Added `vectorstore.hybrid_search()` using `collection.query.hybrid()`
(Weaviate's built-in BM25 + vector fusion, no separate BM25 engine),
and threaded `use_hybrid` / `alpha` through `pipeline.retrieve()` and
the eval CLI (`--hybrid`, `--alpha`) so both search modes share the same
code path for a fair comparison.

## Results: 40-question golden set, alpha=0.5

| Metric | Vector-only (baseline) | Hybrid |
|---|---|---|
| hit_rate | 0.763 (29/38) | 0.816 (31/38) |
| mean_precision | 0.153 | 0.163 |
| abstention_rate | 1.0 | 1.0 |
| ragas_faithfulness | 0.940 | 0.927 |
| ragas_answer_relevancy | 0.692 | 0.742 |
| ragas_context_precision | 0.872 | 0.846 |
| ragas_context_recall | 0.896 | 0.893 |

Net positive on retrieval (+2/38 questions), roughly flat-to-mixed on
RAGAS's LLM-judged metrics. With n=38 retrieval questions, a 2-question
swing is a real but modest effect, not strong enough to treat as a large
win on its own.

One RAGAS evaluation job hit a `TimeoutError` during this run (job 19/160);
`_run_ragas()`'s `df[name].mean()` silently drops NaNs, so the reported
RAGAS means are computed over 159 rather than 160 judged samples for
whichever metric that job belonged to. Noted here for honesty, not
expected to materially change the numbers above.

## Important negative result: the original failure case is NOT fixed

Re-testing the exact kind of question that motivated this work
("ما أثر عدم تسجيل العقار على انتقال الملكية؟") against hybrid search
(alpha=0.5): **Article 934 does not appear even in the top 20 results**,
same as -- arguably worse than -- the pre-hybrid #18/50 ranking.

Root cause: BM25 can only boost a document that contains the literal
query terms. Article 934's text never contains the word "تسجيل" at all
-- it uses "الشهر العقاري" exclusively. So the BM25 half of the hybrid
score contributes ~0 for this specific query/article pair, and ranking
falls back entirely to the vector component, unchanged from before.

**Conclusion: hybrid search measurably improves aggregate retrieval
metrics (likely by helping other query/article pairs that do have
literal keyword overlap), but it does not and structurally cannot fix a
true vocabulary/terminology gap where the target article never uses the
query's words.** That requires closing the gap on the query side (query
expansion/rewriting), not the retrieval-algorithm side -- see
docs/10-query-expansion.md for that follow-up.

## Decision
Keeping hybrid search (alpha=0.5) as the default -- net positive on
aggregate metrics, zero regression on abstention -- while treating
query expansion as a separate, necessary follow-up for the vocabulary-gap
class of failure specifically.