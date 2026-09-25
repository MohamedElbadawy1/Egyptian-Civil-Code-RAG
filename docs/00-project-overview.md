# 00 - Project Overview

**Status:** In progress
**Date:** 2026-09-24

## What we're building
An Arabic legal RAG assistant that answers questions over the Egyptian
Civil Code (1949, as amended), citing the exact article number for every
answer. Bilingual source (Arabic original + English translation),
~1149 articles across the code, with some ranges repealed by later
amendments.

## Roadmap (docs get one entry per finished step)
1. `01-corpus-extraction.md` - PDF -> structured per-article JSON
2. `02-chunking-embedding.md` - chunking strategy, embedding model, vector store
3. `03-api-serving.md` - FastAPI service, request/response contracts
4. `04-packaging-docker-cicd.md` - packaging, Docker, GitHub Actions
5. `05-experiment-tracking.md` - MLflow runs, DVC data versioning
6. `06-optimization-serving.md` - BentoML / vLLM / quantization (if in scope)
7. `07-evaluation-monitoring.md` - RAGAS eval set, Langfuse tracing, guardrails

## Repo layout
```
src/agentic_rag/
  ingestion/   - PDF -> JSON corpus building
  rag/         - chunking, embeddings, vector store, retrieval+generation pipeline
  api/         - FastAPI app exposed to users
  config.py    - paths/settings
scripts/       - thin CLI entrypoints used as DVC stages
data/raw/      - source PDF (DVC-tracked, not git-tracked)
data/processed/- structured JSON corpus (DVC-tracked)
tests/         - pytest suite
docs/          - one file per finished step (this convention)
reports/       - eval outputs, screenshots, generated artifacts
infra/         - deployment config (added when we get there)
```
