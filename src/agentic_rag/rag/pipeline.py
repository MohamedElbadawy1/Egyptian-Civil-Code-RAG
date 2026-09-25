"""
Orchestration glue: corpus JSON -> chunks -> embeddings -> Weaviate.

Kept separate from chunking/embeddings/vectorstore so each stays
independently testable and swappable; this module just wires them
together in the order the CLI script / DVC stage needs.
"""
from __future__ import annotations
import json
from pathlib import Path

from agentic_rag.rag.chunking import Chunk, build_chunks
from agentic_rag.rag.embeddings import OpenAIEmbeddingClient
from agentic_rag.rag import vectorstore
from agentic_rag.rag.vectorstore import RetrievedArticle


def load_articles(processed_json_path: Path) -> list[dict]:
    return json.loads(processed_json_path.read_text(encoding="utf-8"))


def index_corpus(processed_json_path: Path, embedding_client: OpenAIEmbeddingClient | None = None) -> int:
    """Full indexing pipeline: read data/processed/*.json -> embed -> upsert
    to Weaviate. Returns the number of chunks indexed."""
    articles = load_articles(processed_json_path)
    chunks: list[Chunk] = build_chunks(articles)

    client = embedding_client or OpenAIEmbeddingClient()
    vectors = client.embed_texts([c.text for c in chunks])

    with vectorstore.connect() as weaviate_client:
        vectorstore.ensure_collection(weaviate_client)
        vectorstore.upsert_chunks(weaviate_client, chunks, vectors)

    return len(chunks)


def retrieve(query: str, top_k: int = 5, embedding_client: OpenAIEmbeddingClient | None = None) -> list[RetrievedArticle]:
    """Embed a user query and return the top-k matching articles, deduped
    across the Arabic/English vector pair for each article."""
    client = embedding_client or OpenAIEmbeddingClient()
    query_vector = client.embed_query(query)
    with vectorstore.connect() as weaviate_client:
        return vectorstore.search(weaviate_client, query_vector, top_k=top_k)
