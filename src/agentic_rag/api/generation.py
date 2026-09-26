"""
Wraps the OpenAI chat completion call that turns retrieved articles into a
grounded answer.

Kept separate from api/main.py so prompt-building (`build_context`) is
unit-testable without spinning up FastAPI or hitting a real API key.
"""
from __future__ import annotations

import os

from openai import OpenAI

from agentic_rag import (
    config,  # noqa: F401 -- side effect: loads .env before os.environ reads below
)

GENERATION_MODEL = "gpt-5-mini"

SYSTEM_PROMPT = """You are a legal assistant answering questions about the \
Egyptian Civil Code. Answer ONLY using the article excerpts given to you \
in the context below -- never from general knowledge. If the context \
doesn't contain enough information to answer, say so explicitly instead \
of guessing.

Always answer in the same language as the question (an Arabic question \
gets an Arabic answer, an English question gets an English answer), \
regardless of which language the matched source text happened to be in.

Cite the article number for every claim you make, in the form \
"(Article N)" / "(مادة N)" matching the answer's language. If an article \
is marked as repealed, say so explicitly rather than presenting it as \
current law."""


def build_context(articles: list[dict]) -> str:
    """Turn full article records (book/chapter/topic/text_ar/text_en) into
    the context block the model sees. Includes both languages per article
    -- the vector match might be on either one, but the model should be
    able to answer in whichever language the question was asked in."""
    blocks = []
    for a in articles:
        heading = " - ".join(p for p in (a.get("book"), a.get("chapter"), a.get("topic")) if p)
        header = f"Article {a['article_number']}"
        if heading:
            header += f" ({heading})"
        if a.get("is_repealed"):
            header += " [REPEALED]"
        body_lines = []
        if a.get("text_ar"):
            body_lines.append(f"AR: {a['text_ar']}")
        if a.get("text_en"):
            body_lines.append(f"EN: {a['text_en']}")
        blocks.append(header + "\n" + "\n".join(body_lines))
    return "\n\n".join(blocks)


class GenerationClient:
    def __init__(self, api_key: str | None = None, model: str = GENERATION_MODEL):
        api_key = api_key or os.environ["OPENAI_API_KEY"]
        self._client = OpenAI(api_key=api_key)
        self.model = model

    def answer(self, question: str, articles: list[dict]) -> str:
        context = build_context(articles)
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
        )
        return resp.choices[0].message.content
