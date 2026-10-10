# Egyptian Civil Code RAG

An Arabic/English legal RAG (Retrieval-Augmented Generation) assistant that
answers questions about the Egyptian Civil Code (1949, as amended), citing
the exact article number for every claim. Built as an end-to-end MLOps
project — ingestion, indexing, retrieval, evaluation, and deployment are
each tracked, tested, and documented as separate, reproducible stages (see
`docs/`).

## What it does

Ask a question in Arabic or English about Egyptian civil law — property,
contracts, obligations, possession, inheritance, and so on — and get an
answer grounded in the actual bilingual text of the Civil Code (~1,149
articles, some repealed by later amendments), with article-level citations
and confidence scores. The system is designed to abstain rather than guess
when the retrieved articles don't actually cover the question.

## Architecture

```
PDF (Egyptian Civil Code, Arabic + English)
  -> pdftotext -layout + a heading-aware parser (tracks book/chapter/section/topic)
  -> structured per-article JSON corpus
  -> per-article chunking
  -> OpenAI text-embedding-3-large embeddings (one object per article per language)
  -> Weaviate Cloud (self-provided vectors)
  -> retrieval: LLM query expansion -> hybrid search (BM25 + vector fusion)
  -> generation: gpt-5-mini, citation-grounded system prompt
  -> FastAPI (/health, /ask) + static Arabic RTL frontend
```

### Retrieval pipeline

A question first goes through **query expansion**: an LLM call rewrites it
to include the Civil Code's formal legal terminology alongside the
original wording (e.g. adds "الشهر العقاري" when the question says
"تسجيل" — see `docs/10-query-expansion.md` for why this was necessary).
The expanded query then goes through **hybrid search** — Weaviate's native
BM25 + vector fusion (`alpha=0.5`) — rather than vector similarity alone.

Both steps are on by default in `pipeline.retrieve()` but independently
toggleable (`use_hybrid`, `expand`), which is how the before/after
comparisons in `docs/09-hybrid-search.md` and `docs/10-query-expansion.md`
were produced.

## Why this exists

This started as a straightforward RAG build and turned into a real
debugging story, documented step by step in `docs/`:

- Two separate bugs in the PDF heading parser silently made every article
  inherit the wrong book/chapter/section context, polluting what got
  embedded (`docs/01-corpus-extraction.md`).
- Live testing (not the automated eval set) surfaced a case where the
  article that actually governs real-estate registration (Article 934)
  wasn't retrieved for an obvious registration question — in Arabic *or*
  English.
- Root-causing that traced to a genuine vocabulary gap: users ask about
  "تسجيل" (registration), but the Code's actual term is "الشهر العقاري"
  (real-estate publication). Hybrid search alone measurably improved
  aggregate metrics but did **not** fix this specific case (`docs/09`) —
  BM25 can only match literal terms, and the article never contains the
  word "تسجيل" at all. Query expansion closed it (`docs/10`): Article 934
  now ranks #1 for the original failing query.
- A metrics bug of our own: `abstention_rate` appeared to regress from
  1.0 to 0.5 after expanding the golden set, which turned out to be a
  substring-matching heuristic missing a new (but correct) refusal
  phrasing, not an actual model regression — fixed by switching to an
  LLM-judged abstention check (`docs/07-evaluation-monitoring.md`).

The docs are written to be honest about what didn't work, not just what
did — several "fixes" here are deliberately documented alongside the
negative results that preceded them.

## Tech stack

- **Embeddings & generation:** OpenAI (`text-embedding-3-large`, `gpt-5-mini`)
- **Vector store:** Weaviate Cloud (self-provided vectors, dual-language objects per article, native hybrid search)
- **API:** FastAPI
- **Frontend:** self-contained Arabic RTL HTML/CSS/JS, no build step, served by FastAPI
- **Experiment tracking:** MLflow — every indexing and evaluation run is a logged run with params/metrics
- **Pipeline/data versioning:** DVC (`build_corpus` -> `build_index` -> `evaluate`)
- **Evaluation:** RAGAS (faithfulness, answer relevancy, context precision/recall) + custom deterministic metrics (hit@k, precision@k) + LLM-judged abstention scoring, against a 40-question golden set
- **CI:** GitHub Actions — ruff, pytest, and a Docker build with smoke tests that actually run the image and hit `/health` and `/`
- **Containerization:** Docker

## Project structure

```
src/agentic_rag/
  ingestion/         # PDF -> structured JSON corpus (parse_pdf.py)
  rag/                # chunking, embeddings, vectorstore, retrieval pipeline, query expansion
  api/                 # FastAPI app, request/response schemas, generation client
  eval/                 # golden set, metrics (deterministic + LLM-judged), evaluation runner
  config.py              # paths/settings
scripts/                  # thin CLI entrypoints used as DVC stages (build_corpus, build_index, run_evaluation)
frontend/                  # static Arabic RTL chat UI
eval/golden_qa.json          # 40-question golden evaluation set
reports/                       # evaluation CSV reports (baseline / hybrid / hybrid+expand comparisons)
data/raw/, data/processed/       # source PDF and structured corpus (DVC-tracked)
docs/                               # one file per development step, with real results and bugs found/fixed
dvc.yaml                              # build_corpus -> build_index -> evaluate pipeline
tests/                                  # pytest suite
Dockerfile, docker-compose.yml
.github/workflows/                        # CI
```

## Setup

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and
[Poppler](https://poppler.freedesktop.org/) (`pdftotext`) for corpus
extraction.

```bash
uv sync
cp .env.example .env   # fill in OPENAI_API_KEY, WEAVIATE_URL, WEAVIATE_API_KEY
```

### Build the corpus and index

```bash
uv run dvc repro
```

Or run stages individually:

```bash
pdftotext -layout data/raw/egyptian_civil_code.pdf data/interim/civil_code_layout.txt
uv run python src/agentic_rag/ingestion/parse_pdf.py \
  --input data/interim/civil_code_layout.txt \
  --output data/processed/civil_code_articles.json

uv run python -m scripts.build_index --corpus data/processed/civil_code_articles.json
```

### Run the API + frontend

```bash
uv run python -m uvicorn agentic_rag.api.main:app --reload
```

Open `http://127.0.0.1:8000/` for the chat UI, or call the API directly:

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "ما هي الحقوق التي يملكها مالك الشيء؟", "top_k": 5}'
```

### Run with Docker

```bash
docker compose up --build
```

## Evaluation

```bash
uv run python -m scripts.run_evaluation                    # default config (hybrid + expansion)
uv run python -m scripts.run_evaluation --hybrid            # hybrid search only, for comparison
uv run python -m scripts.run_evaluation --hybrid --expand    # same as default, explicit
uv run python -m scripts.run_evaluation --no-ragas             # skip the paid LLM-judge metrics
```

Results are written to `reports/evaluation_latest.csv` (or an `_expanded`-suffixed
file with `--expand`) and logged as an MLflow run (`uv run mlflow ui` to view).

### Current results (40-question golden set)

| Metric | Vector-only (baseline) | + Hybrid search | + Query expansion |
|---|---|---|---|
| hit_rate | 0.763 | 0.816 | **0.868** |
| mean_precision | 0.153 | 0.163 | **0.184** |
| abstention_rate | 1.0 | 1.0 | 1.0 |
| ragas_faithfulness | 0.940 | 0.927 | **0.959** |
| ragas_answer_relevancy | 0.692 | 0.742 | **0.787** |
| ragas_context_precision | 0.872 | 0.846 | **0.893** |
| ragas_context_recall | 0.896 | 0.893 | **0.954** |

See `docs/09-hybrid-search.md` and `docs/10-query-expansion.md` for the
full methodology, including the negative result (hybrid search alone did
not fix the motivating failure case) that justified adding query
expansion on top.

## Tests & linting

```bash
uv run pytest -q
uv run ruff check src tests
```

## Documentation

Each development step has its own file in `docs/`, written to include real
results and bugs encountered, not just what was intended:

| Doc | Covers |
|---|---|
| `00-project-overview.md` | Scope, roadmap, repo layout |
| `01-corpus-extraction.md` | PDF parsing, two heading-tracker bugs found and fixed |
| `02-chunking-embedding.md` | Chunking strategy, embedding model, vector store design |
| `03-api-serving.md` | FastAPI service, request/response contracts |
| `04-packaging-docker-cicd.md` | Docker, GitHub Actions, the smoke-test regression they catch |
| `05-experiment-tracking.md` | MLflow runs, DVC pipeline design |
| `07-evaluation-monitoring.md` | Golden set, RAGAS metrics, the abstention-measurement bug and its fix |
| `08-frontend.md` | The static Arabic RTL chat UI |
| `09-hybrid-search.md` | Hybrid search implementation and results — including the negative result on the motivating failure case |
| `10-query-expansion.md` | Query expansion implementation, full results, and closing out the Article 934 investigation |

## Known limitations

- `abstention_rate` and other LLM-judged metrics are computed on a
  40-question golden set — informative directionally, not statistically
  large.
- Query expansion and the abstention judge both add an extra LLM call per
  request/question; acceptable for this project's scale, worth revisiting
  if request volume grows.
- RAGAS evaluation isn't wired into CI (it costs real API credits per
  run), so it's a manual/scheduled step rather than a required check.
- Monitoring (e.g. Langfuse) and guardrails were scoped out of the
  evaluation step to keep it reviewable; not yet implemented.
