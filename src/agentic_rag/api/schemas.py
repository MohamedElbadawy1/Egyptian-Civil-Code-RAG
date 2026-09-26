"""Pydantic request/response models for the API. Kept separate from
main.py so they're importable (e.g. from tests) without pulling in the
FastAPI app itself."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Question in Arabic or English")
    top_k: int = Field(default=5, ge=1, le=10)


class RetrievedArticleOut(BaseModel):
    article_number: int
    citation: str
    is_repealed: bool
    score: float


class AskResponse(BaseModel):
    answer: str
    articles: list[RetrievedArticleOut]
