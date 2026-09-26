# 03 - API Serving

**Status:** Done - ran end-to-end against a live server, OpenAI, and Weaviate
**Date:** 2026-09-24

## What we built
- `src/agentic_rag/rag/corpus.py` - loads/caches the processed JSON corpus,
  indexed by `article_number`. Separated from the vector store on purpose:
  Weaviate only needs to rank article numbers, not carry full bilingual
  text around.
- `src/agentic_rag/api/generation.py` - `GenerationClient` wraps the
  OpenAI chat completion call; `build_context()` turns full article
  records into the prompt context (both languages included per article,
  repealed articles flagged) - kept as a standalone function so it's
  testable without a real API key.
- `src/agentic_rag/api/schemas.py` - `AskRequest` / `AskResponse` /
  `RetrievedArticleOut` Pydantic models.
- `src/agentic_rag/api/main.py` - `POST /ask` and `GET /health`. Thin by
  design: retrieve -> look up full article text -> generate -> respond.

## Why / decisions
- **Generation model: OpenAI `gpt-5-mini`, not Groq.** Since embeddings
  already moved to OpenAI (see docs/02), using the same provider for
  generation keeps the stack to one API key to manage instead of two.
  `gpt-4o-mini` (the original plan) was retired by OpenAI in Feb 2026;
  `gpt-5-mini` is the current cost-tier equivalent. Groq keys stay in
  `.env` unused for now - easy to switch back if latency or cost becomes
  an issue.
- **Response shape:** `answer` (LLM text) and `articles` (retrieved
  article numbers + citations + scores) as separate fields, not just a
  single answer string - lets the frontend show sources independently of
  whatever the model chose to cite inline.
- **Language mirroring is a prompt instruction, not code logic.** The
  system prompt tells the model to answer in the question's language
  regardless of which language the matched article text came from, since
  Arabic and English text for the same article are both always available
  in the context.
- **Full article text comes from `data/processed/*.json` via
  `corpus.py`, not from Weaviate.** The vector store's stored `text`
  property is per-language (one object per article per language); the
  generation step needs both languages together per article, which the
  original corpus record already has.
- **Repealed articles are flagged in the context** (`[REPEALED]` marker)
  rather than silently included, so the model can say "this article was
  repealed" instead of presenting outdated law as current.
- **No `temperature` override on the generation call.** Originally set
  `temperature=0.1` for more deterministic legal answers, but `gpt-5-mini`
  is a reasoning model and rejects any value other than the default (1) -
  `400 Unsupported value`. Removed rather than worked around, since there
  isn't a way to lower it on this model family.

## How to run
```
uv sync
uv run python -m uvicorn agentic_rag.api.main:app --host 127.0.0.1 --port 8000
# then: POST http://127.0.0.1:8000/ask  {"question": "ما هي أهلية التصرف؟"}
```
(Use `python -m uvicorn` rather than the bare `uvicorn` command on
Windows - a stray global `uvicorn.exe` on PATH can shadow the venv's own
copy and load the wrong Python environment entirely.)

## Results / validation
- `tests/test_generation.py` (4 tests) - `build_context()` heading
  formatting, bilingual inclusion, repealed flagging, multi-article joins
- `tests/test_schemas.py` (4 tests) - request/response validation
- Full suite: 14/14 passing, `ruff check` clean

**Not yet validated:** never made a real HTTP request against a running
server - no network route to `api.openai.com` from this environment.
Known retrieval-quality caveat from docs/02 still applies (heading
tracker bug) - expect the retrieved-articles list to occasionally include
a lexically-similar-but-wrong-topic article until that's fixed.

Ran end-to-end locally afterward with a real question
(`"ما هي أهلية التصرف؟"`): `/ask` returned a coherent, correctly-cited
Arabic answer citing articles 6, 110 and 118 (all genuinely relevant per
docs/02's manual check) plus 802. Notably, the model **skipped citing
article 949** (possession - the clearly irrelevant retrieval from docs/02)
on its own, even though it was in the context - the generation step adds
a second filtering pass on top of imperfect retrieval, which softens the
impact of the known heading-tracker bug somewhat. It still worked article
802 (ownership/property rights) into the answer despite it not really
being about legal capacity, because it's in the context and shares
surface vocabulary ("تصرف") with the real topic.

## Known issues / next steps
- No API-level tests yet (e.g. `TestClient` hitting `/ask` with mocked
  retrieve/generation) - worth adding once we've run it live at least
  once and know what the real response shape looks like.
- No auth/rate-limiting on the endpoint - fine for local dev, needed
  before any public deployment.
- `GenerationClient` is constructed lazily as a module-level singleton in
  `main.py` - fine for a single-process dev server, will need revisiting
  once we containerize (Step 04) if multiple workers each need their own.
