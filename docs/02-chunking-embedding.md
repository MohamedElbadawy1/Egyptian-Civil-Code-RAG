# 02 - Chunking & Embedding

**Status:** Done - indexed successfully against live OpenAI + Weaviate Cloud
**Date:** 2026-09-24 (updated: switched embedding provider from Gemini to OpenAI; fixed Weaviate gRPC timeout + a config deprecation warning)

## What we built
- `src/agentic_rag/rag/chunking.py` - turns each article record into up to
  two `Chunk`s (Arabic + English), skipping a language with no text.
- `src/agentic_rag/rag/embeddings.py` - `OpenAIEmbeddingClient`, a thin
  batching/retrying wrapper around `text-embedding-3-large`.
- `src/agentic_rag/rag/vectorstore.py` - Weaviate wrapper: schema creation,
  idempotent upsert (UUID derived from `chunk_id`), and `search()` which
  dedupes the Arabic/English pair per article by best score.
- `src/agentic_rag/rag/pipeline.py` - wires the three together:
  `index_corpus()` for building the index, `retrieve()` for querying it.
- `scripts/build_index.py` - CLI entrypoint for the indexing stage.

## Why / decisions
- **Chunk = one full article per language.** A legal article is the
  smallest unit that stands on its own; splitting further risks losing a
  clause's condition.
- **Two vectors per article (Arabic + English), not one merged embedding.**
  Avoids diluting the embedding with a mixed-language blend, and lets a
  query in either language match natively. `search()` over-fetches
  (`top_k * 2`) then dedupes by `article_number`, keeping the higher-scoring
  (i.e. same-language) hit.
- **Embedding provider: OpenAI `text-embedding-3-large`, not Gemini.**
  Originally built against `gemini-embedding-001` (chosen for multilingual
  benchmark strength), but the free-tier key repeatedly hit Gemini's
  100 requests/minute embed_content quota partway through a ~68-batch
  indexing run, even with pacing and backoff. Switched to a paid OpenAI
  key: `text-embedding-3-large` is also a strong multilingual/Arabic
  performer (MIRACL ~55) and doesn't hit a comparable wall at this corpus
  size. Groq stays in the stack for fast LLM generation later, not
  embeddings - its hosted embedding model (`nomic-embed-text-v1.5`) is
  general-purpose, not Arabic-tuned.
- **768 output dimensions** (Matryoshka-truncated from the model's native
  3072) - good accuracy/storage trade-off at ~2,172 vectors; cheap to bump
  to 1536/3072 later if retrieval quality needs it. Kept the same value
  across the Gemini and OpenAI attempts so the Weaviate schema doesn't
  need to change if we ever want to compare providers head-to-head.
- **Idempotent upserts.** Object UUIDs are derived from `chunk_id`
  (`article-<n>-<lang>`), so re-running the indexing script after a corpus
  fix updates existing objects instead of duplicating them.

## How to run
```
pip install -e .
cp .env.example .env   # fill in OPENAI_API_KEY, WEAVIATE_URL, WEAVIATE_API_KEY
python scripts/build_index.py --corpus data/processed/civil_code_articles.json
```

## Results / validation
Ran `build_chunks()` against the real 1086-article corpus (pure Python, no
network needed):
- 2,172 chunks total (1,086 Arabic + 1,086 English - every article has both)
- chunk length: 33-2,148 characters (min/max), 261 median
- `tests/test_chunking.py` (4 tests) passing

Ran the full pipeline end-to-end against live APIs:
- All 22 embedding batches (OpenAI `text-embedding-3-large`, batch size
  100) completed successfully, no rate-limit errors
- **2,172 chunks indexed into the Weaviate `CivilCodeArticle` collection**
  - matches the chunk count above exactly

Two issues hit and fixed along the way:
- Weaviate Cloud connection failed with a gRPC `DEADLINE_EXCEEDED` on the
  first attempt. Fixed by passing a longer `AdditionalConfig(timeout=...)`
  to `connect_to_weaviate_cloud()`. If this resurfaces for someone else on
  a different machine, it's more often a local VPN/antivirus doing SSL
  inspection on HTTP/2 than a Weaviate-side problem.
- `collection.create()` warned that `vectorizer_config=Configure.Vectorizer.none()`
  is deprecated in newer weaviate-client versions; switched to
  `vector_config=Configure.Vectors.self_provided()`. Since the
  `CivilCodeArticle` collection already existed by the time this was
  fixed, the running collection is still on the old-style config -
  harmless (it works fine), but a full `dvc repro` / fresh environment
  from now on creates it with the new-style config.

## Retrieval quality baseline (MVP, not final)
Manually tested one query end-to-end: `"ما هي أهلية التصرف؟"` (capacity to
transact) against the live index, `top_k=5`:

| Article | Relevant? | Notes |
|---|---|---|
| 802 | No | Property/ownership rights - lexical collision on the word "تصرف" (disposal), wrong legal domain |
| 949 | No | Possession (الحيازة) - unrelated |
| 118 | Yes | Guardians'/custodians' transactions |
| 6 | Yes | Directly defines scope of "أهلية" provisions - **should rank #1, ranked #4** |
| 110 | Yes | A minor's transactions are void |

3/5 relevant, weak similarity scores (0.45-0.48), and the most obviously
on-topic article (6) under-ranked. Root-caused this to the chapter/topic
metadata being useless for context enrichment right now (see the heading
tracker bug logged in docs/01-corpus-extraction.md) - tried prefixing
chunks with heading context before embedding
(`Chunk.embedding_text()`), but since every chunk currently resolves to
the same first heading, it added zero discriminating signal. Reverted
that from the indexing pipeline rather than ship a change that does
nothing.

**Decision:** accept this as the MVP baseline rather than block on fixing
headings now. Reasoning: (1) the fix belongs in Step 0's parser, not
here, and is a real rewrite, not a patch; (2) Step 07
(evaluation/monitoring) already has RAGAS evaluation on the roadmap,
which will give a systematic quality signal across many questions instead
of one anecdotal query - better to prioritize headings once we have that
data showing how much it actually matters, not guess. Revisit after Step
07, or sooner if API-level testing in Step 03 surfaces retrieval quality
as a bigger blocker than expected.

## Known issues / next steps
- Sub-headings sometimes leak into the previous article's body instead
  of starting a fresh heading context.
- The longest chunk (2,148 chars) is worth spot-checking - could be a
  heading-leak artifact from the Step 0 parser rather than a genuinely
  long article.
- No retry/backoff tuning done yet for Weaviate batch upserts specifically
  (only the embedding calls retry) - watch for batch failures at scale.
- `search()`'s over-fetch factor (`top_k * 2`) is a starting guess, not
  tuned against real retrieval results yet.
- `Chunk.embedding_text()` (heading-prefixed embedding input) exists but
  is unused until the Step 0 heading tracker is fixed - see "Retrieval
  quality baseline" above.
