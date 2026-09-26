"""
Turn parsed article records (from ingestion.parse_pdf) into embeddable chunks.

Chunking unit = one full article per language. A legal article is already
the smallest self-contained unit of meaning in the Civil Code; splitting it
further risks cutting a sentence mid-clause and losing the condition it
depends on. Each article contributes up to two chunks (Arabic + English) so
they can be embedded and stored as separate vectors -- see
docs/02-chunking-embedding.md for why.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Language = Literal["ar", "en"]


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    article_number: int
    language: Language
    text: str
    book: str | None
    chapter: str | None
    section: str | None
    topic: str | None
    is_repealed: bool
    citation: str

    def to_weaviate_properties(self) -> dict:
        """Everything except chunk_id, which is used to derive the object's
        UUID rather than being stored as a property."""
        d = asdict(self)
        d.pop("chunk_id")
        return d

    def embedding_text(self) -> str:
        """Text sent to the embedding model -- distinct from `text`, which
        stays the clean article body used for citation and as LLM context
        later.

        Prepending the book/chapter/section/topic heading gives the model
        surrounding legal context a bare 1-3 sentence article often lacks
        on its own (e.g. distinguishing "a minor's transactions are void"
        under Book I - capacity from "the owner's right to use property"
        under Book III - ownership, which share surface vocabulary like
        "تصرف" but are unrelated legal concepts). Wired into the indexing
        pipeline now that ingestion/parse_pdf.py's heading tracker
        actually produces distinct headings per article (previously it
        was a no-op - see docs/02-chunking-embedding.md history).
        """
        heading = " - ".join(p for p in (self.book, self.chapter, self.section, self.topic) if p)
        return f"{heading}\n{self.text}" if heading else self.text


def build_chunks(articles: list[dict]) -> list[Chunk]:
    """One Chunk per (article, language) pair that actually has text.

    A repealed article with no body in either language contributes zero
    chunks -- there's nothing meaningful to embed or retrieve.
    """
    chunks: list[Chunk] = []
    for a in articles:
        for lang, text in (("ar", a.get("text_ar", "")), ("en", a.get("text_en", ""))):
            if not text:
                continue
            chunks.append(Chunk(
                chunk_id=f"article-{a['article_number']}-{lang}",
                article_number=a["article_number"],
                language=lang,  # type: ignore[arg-type]
                text=text,
                book=a.get("book"),
                chapter=a.get("chapter"),
                section=a.get("section"),
                topic=a.get("topic"),
                is_repealed=a["is_repealed"],
                citation=a["citation"],
            ))
    return chunks
