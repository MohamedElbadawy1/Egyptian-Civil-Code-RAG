"""
FastAPI app exposing the RAG pipeline as a single /ask endpoint.

Kept thin on purpose: retrieval lives in rag/pipeline.py, generation in
api/generation.py, article lookups in rag/corpus.py -- this module only
wires the HTTP layer around them.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from agentic_rag.api.generation import GenerationClient
from agentic_rag.api.schemas import AskRequest, AskResponse, RetrievedArticleOut
from agentic_rag.rag.corpus import load_corpus_index
from agentic_rag.rag.pipeline import retrieve

app = FastAPI(title="Egyptian Civil Code RAG", version="0.1.0")

# Lazily constructed so importing this module (e.g. for tests) doesn't
# require OPENAI_API_KEY to be set until a request actually needs it.
_generation_client: GenerationClient | None = None


def get_generation_client() -> GenerationClient:
    global _generation_client
    if _generation_client is None:
        _generation_client = GenerationClient()
    return _generation_client


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    retrieved = retrieve(request.question, top_k=request.top_k)
    if not retrieved:
        raise HTTPException(status_code=404, detail="No relevant articles found")

    corpus_index = load_corpus_index()
    full_articles = [
        corpus_index[r.article_number]
        for r in retrieved
        if r.article_number in corpus_index
    ]

    answer = get_generation_client().answer(request.question, full_articles)

    return AskResponse(
        answer=answer,
        articles=[
            RetrievedArticleOut(
                article_number=r.article_number,
                citation=r.citation,
                is_repealed=r.is_repealed,
                score=r.score,
            )
            for r in retrieved
        ],
    )
