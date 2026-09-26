"""
Weaviate wrapper for the dual-language (Arabic + English) article index.

Each article contributes up to two objects to the same collection -- one
per language it has text in -- instead of one blended-language object.
A query in either language then matches natively against same-language
vectors rather than diluting similarity against a mixed embedding. See
docs/02-chunking-embedding.md for the reasoning.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import weaviate
from weaviate.auth import AuthApiKey
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.init import AdditionalConfig, Timeout
from weaviate.util import generate_uuid5

from agentic_rag import (
    config,  # noqa: F401 -- side effect: loads .env before os.environ reads below
)
from agentic_rag.rag.chunking import Chunk

COLLECTION_NAME = "CivilCodeArticle"


def connect() -> weaviate.WeaviateClient:
    """Caller is expected to use this as a context manager
    (`with vectorstore.connect() as client:`) so the connection is
    always closed, matching weaviate-client v4's recommended usage.

    Generous timeouts here because the free Sandbox tier can be slow on
    a cold start; if the gRPC health check still times out after this,
    it's almost always a local firewall/VPN/antivirus doing SSL
    inspection that breaks HTTP/2, not a Weaviate-side problem -- see
    docs/02-chunking-embedding.md.
    """
    return weaviate.connect_to_weaviate_cloud(
        cluster_url=os.environ["WEAVIATE_URL"],
        auth_credentials=AuthApiKey(os.environ["WEAVIATE_API_KEY"]),
        additional_config=AdditionalConfig(
            timeout=Timeout(init=60, query=60, insert=120)
        ),
    )


def ensure_collection(client: weaviate.WeaviateClient) -> None:
    """Create the collection if it doesn't exist yet. We supply our own
    vectors (Gemini embeddings), so Weaviate's built-in vectorizer is
    disabled."""
    if client.collections.exists(COLLECTION_NAME):
        return
    client.collections.create(
        COLLECTION_NAME,
        vector_config=Configure.Vectors.self_provided(),
        properties=[
            Property(name="article_number", data_type=DataType.INT),
            Property(name="language", data_type=DataType.TEXT),
            Property(name="text", data_type=DataType.TEXT),
            Property(name="book", data_type=DataType.TEXT),
            Property(name="chapter", data_type=DataType.TEXT),
            Property(name="section", data_type=DataType.TEXT),
            Property(name="topic", data_type=DataType.TEXT),
            Property(name="is_repealed", data_type=DataType.BOOL),
            Property(name="citation", data_type=DataType.TEXT),
        ],
    )


def upsert_chunks(client: weaviate.WeaviateClient, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    """Batch-upsert chunks. UUIDs are derived deterministically from
    chunk_id, so re-running this is idempotent -- re-embedding an article
    updates its existing object instead of duplicating it."""
    assert len(chunks) == len(vectors), "chunk/vector count mismatch"
    collection = client.collections.get(COLLECTION_NAME)
    with collection.batch.dynamic() as batch:
        for chunk, vector in zip(chunks, vectors):
            batch.add_object(
                properties=chunk.to_weaviate_properties(),
                uuid=generate_uuid5(chunk.chunk_id),
                vector=vector,
            )
    failed = collection.batch.failed_objects
    if failed:
        raise RuntimeError(f"{len(failed)} objects failed to upsert, e.g. {failed[0]}")


@dataclass
class RetrievedArticle:
    article_number: int
    citation: str
    is_repealed: bool
    score: float


def search(client: weaviate.WeaviateClient, query_vector: list[float], top_k: int = 5) -> list[RetrievedArticle]:
    """Search across both languages at once and dedupe by article number,
    keeping the best-scoring hit per article (in practice, the hit whose
    language matches the query language)."""
    collection = client.collections.get(COLLECTION_NAME)
    results = collection.query.near_vector(
        near_vector=query_vector,
        limit=top_k * 2,  # over-fetch: both languages compete for the same articles
        return_metadata=["distance"],
    )
    best: dict[int, RetrievedArticle] = {}
    for obj in results.objects:
        num = obj.properties["article_number"]
        score = 1 - obj.metadata.distance  # cosine distance -> similarity
        if num not in best or score > best[num].score:
            best[num] = RetrievedArticle(
                article_number=num,
                citation=obj.properties["citation"],
                is_repealed=obj.properties["is_repealed"],
                score=score,
            )
    return sorted(best.values(), key=lambda r: r.score, reverse=True)[:top_k]
