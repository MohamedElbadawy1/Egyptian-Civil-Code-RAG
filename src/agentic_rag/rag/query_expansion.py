"""
Query expansion: rewrite a user's natural-language question into one that
also contains the formal legal terminology the Civil Code actually uses,
before it reaches retrieval.

Motivated by a real failure case: a question about registering real
estate ownership using "تسجيل" never retrieved Article 934, because
Article 934's actual text says "الشهر العقاري" (real-estate publication)
-- a different word for the same concept. BM25 can only match literal
terms present in a document, so hybrid search alone can't close a
vocabulary gap like this -- only rewriting the query can. See
docs/09-hybrid-search.md and docs/10-query-expansion.md.
"""
from __future__ import annotations

import os

from openai import OpenAI

_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

_EXPANSION_PROMPT = """You are helping a legal search system find the right \
Egyptian Civil Code articles for a layperson's question.

Rewrite the question below by ADDING the formal/technical Arabic or \
English legal terminology an Egyptian lawyer would use for the same \
concept, while KEEPING all of the original wording too. Do not answer \
the question. Do not remove any of the original words.

Known terminology gaps in this codebase (add the alternate term when \
relevant, don't limit yourself to only these):
- "تسجيل" (registration, colloquial) <-> "الشهر العقاري" (real-estate \
publication, the Code's actual term for real property)
- "عقوبة" (penalty) <-> "جزاء" depending on context

Question: {question}

Reply with only the expanded question text (original + added legal \
terms), nothing else."""


def expand_query(question: str) -> str:
    """Returns the question with legal-terminology synonyms appended, so
    both the BM25 and vector sides of hybrid search have more terms to
    match against. Falls back to the original question on any API error
    -- expansion is a quality improvement, never a hard dependency for
    retrieval to function."""
    try:
        response = _client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": _EXPANSION_PROMPT.format(question=question)}],
        )
        expanded = response.choices[0].message.content.strip()
        return expanded or question
    except Exception:
        return question