"""
Orchestration glue: corpus JSON -> chunks -> embeddings -> Weaviate.

Kept separate from chunking/embeddings/vectorstore so each stays
independently testable and swappable; this module just wires them
together in the order the CLI script / DVC stage needs.
"""
from __future__ import annotations

import json
from pathlib import Path

import mlflow

from agentic_rag.rag import vectorstore
from agentic_rag.rag.chunking import Chunk, build_chunks
from agentic_rag.rag.embeddings import OpenAIEmbeddingClient
from agentic_rag.rag.vectorstore import RetrievedArticle


def load_articles(processed_json_path: Path) -> list[dict]:
    return json.loads(processed_json_path.read_text(encoding="utf-8"))


def index_corpus(processed_json_path: Path, embedding_client: OpenAIEmbeddingClient | None = None) -> int:
    """Full indexing pipeline: read data/processed/*.json -> embed -> upsert
    to Weaviate. Returns the number of chunks indexed.

    Logged as an MLflow run so successive indexing attempts (different
    embedding models, dimensions, or a fixed heading tracker producing
    different embedding_text() output) are comparable later instead of
    only living in scrollback -- see docs/05-experiment-tracking.md.
    """
    articles = load_articles(processed_json_path)
    chunks: list[Chunk] = build_chunks(articles)

    client = embedding_client or OpenAIEmbeddingClient()

    with mlflow.start_run(run_name="index_corpus"):
        mlflow.log_param("embedding_model", client.config.model)
        mlflow.log_param("embedding_dimensions", client.config.dimensions)
        mlflow.log_param("batch_size", client.config.batch_size)
        mlflow.log_param("corpus_path", str(processed_json_path))
        mlflow.log_metric("article_count", len(articles))
        mlflow.log_metric("chunk_count", len(chunks))

        # Embeds the heading-prefixed text now that the heading tracker
        # produces real per-article context (see Chunk.embedding_text
        # docstring) instead of the same constant string for every chunk.
        vectors = client.embed_texts([c.embedding_text() for c in chunks])

        with vectorstore.connect() as weaviate_client:
            vectorstore.ensure_collection(weaviate_client)
            vectorstore.upsert_chunks(weaviate_client, chunks, vectors)

        mlflow.log_metric("vectors_indexed", len(vectors))

    return len(chunks)


from agentic_rag.rag.query_expansion import expand_query


def retrieve(
    query: str,
    top_k: int = 5,
    embedding_client: OpenAIEmbeddingClient | None = None,
    use_hybrid: bool = False,
    alpha: float = 0.5,
    expand: bool = False,
) -> list[RetrievedArticle]:
    """Embed a user query and return the top-k matching articles, deduped
    across the Arabic/English vector pair for each article.

    expand=True rewrites the query through expand_query() first, adding
    formal legal terminology (e.g. "الشهر العقاري" alongside "تسجيل") so
    BM25 and the embedding both have the Code's actual vocabulary to
    match against -- see docs/10-query-expansion.md for why hybrid
    search alone couldn't close this specific gap.
    """
    search_query = expand_query(query) if expand else query
    client = embedding_client or OpenAIEmbeddingClient()
    query_vector = client.embed_query(search_query)
    with vectorstore.connect() as weaviate_client:
        if use_hybrid:
            return vectorstore.hybrid_search(
                weaviate_client, search_query, query_vector, top_k=top_k, alpha=alpha
            )
        return vectorstore.search(weaviate_client, query_vector, top_k=top_k)