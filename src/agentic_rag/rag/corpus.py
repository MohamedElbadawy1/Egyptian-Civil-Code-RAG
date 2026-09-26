"""
Loads the canonical article corpus and indexes it by article_number.

Kept separate from vectorstore.py on purpose: the vector store's only job
is ranking article numbers, not carrying full bilingual article text
around. Anything that needs the actual article content (the API's
generation step, future citation display, etc.) reads it from here
instead, off the same JSON file Step 0 produced.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from agentic_rag.config import DATA_PROCESSED


@lru_cache(maxsize=1)
def load_corpus_index(path: Path | None = None) -> dict[int, dict]:
    """Cached: the corpus doesn't change within a process's lifetime, and
    re-parsing a ~1.1MB JSON file on every request would be wasteful."""
    path = path or (DATA_PROCESSED / "civil_code_articles.json")
    articles = json.loads(path.read_text(encoding="utf-8"))
    return {a["article_number"]: a for a in articles}
