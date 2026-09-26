"""
Thin wrapper around the OpenAI embeddings API.

Kept as a small interface (embed_texts / embed_query) so the rest of the
pipeline doesn't care which provider sits behind it. Swapping to a
different embedding model later means implementing this same interface --
nothing in chunking.py or vectorstore.py needs to change.

Provider history: started on Gemini's `gemini-embedding-001` (see git
history / docs/02-chunking-embedding.md) but the free tier's 100
requests/minute quota kept blocking a full ~68-batch indexing run.
Switched to OpenAI's `text-embedding-3-large` on a paid key -- still a
strong multilingual/Arabic performer (MIRACL ~55), and the paid tier
doesn't hit the same wall for a corpus this size (~2,172 chunks).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from openai import OpenAI, RateLimitError

from agentic_rag import (
    config,  # noqa: F401 -- side effect: loads .env before os.environ reads below
)

DEFAULT_MODEL = "text-embedding-3-large"
# Matryoshka-truncated from the model's native 3072 dims: good
# accuracy/storage trade-off at our corpus size (~2.2k vectors). Keeping
# this the same value as the Gemini attempt means the Weaviate schema
# doesn't need to change if we ever compare the two providers.
DEFAULT_DIMENSIONS = 768
# OpenAI accepts up to 2048 inputs per embeddings request; we stay well
# under that so a single failed batch doesn't cost much retry work.
BATCH_SIZE = 100
MAX_RETRIES = 5
INTER_BATCH_SLEEP_SECONDS = 0.2
RATE_LIMIT_BACKOFF_SECONDS = 10


@dataclass
class EmbeddingConfig:
    model: str = DEFAULT_MODEL
    dimensions: int = DEFAULT_DIMENSIONS
    batch_size: int = BATCH_SIZE


class OpenAIEmbeddingClient:
    """Wraps OpenAI's embeddings.create with batching + retry.

    Unlike Gemini, OpenAI's embedding API doesn't distinguish a "document"
    vs "query" task type -- embed_query() exists mainly so callers don't
    need to know that, and so a future provider that *does* care about the
    distinction is a drop-in replacement.
    """

    def __init__(self, api_key: str | None = None, embedding_config: EmbeddingConfig | None = None):
        api_key = api_key or os.environ["OPENAI_API_KEY"]
        self._client = OpenAI(api_key=api_key)
        self.config = embedding_config or EmbeddingConfig()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of documents for indexing. Batches internally."""
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single user query."""
        return self._embed([text])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        total_batches = (len(texts) + self.config.batch_size - 1) // self.config.batch_size
        for i in range(0, len(texts), self.config.batch_size):
            batch = texts[i:i + self.config.batch_size]
            batch_num = i // self.config.batch_size + 1
            out.extend(self._embed_batch(batch))
            print(f"  embedded batch {batch_num}/{total_batches}")
            if batch_num < total_batches:
                time.sleep(INTER_BATCH_SLEEP_SECONDS)
        return out

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.embeddings.create(
                    model=self.config.model,
                    input=batch,
                    dimensions=self.config.dimensions,
                )
                return [e.embedding for e in resp.data]
            except RateLimitError as e:
                last_err = e
                wait = RATE_LIMIT_BACKOFF_SECONDS * (attempt + 1)
                print(f"  rate limited, waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
            except Exception as e:  # noqa: BLE001 -- deliberately broad: any
                # transient network/SDK error should be retried the same way
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Embedding batch failed after {MAX_RETRIES} retries") from last_err
