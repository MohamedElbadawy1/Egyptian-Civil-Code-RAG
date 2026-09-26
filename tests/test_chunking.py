from agentic_rag.rag.chunking import build_chunks


def _article(**overrides):
    base = {
        "article_number": 1,
        "text_ar": "نص عربي",
        "text_en": "English text",
        "book": None,
        "chapter": "SECTION I",
        "section": None,
        "topic": None,
        "is_repealed": False,
        "citation": "Egyptian Civil Code, Article 1",
    }
    base.update(overrides)
    return base


def test_bilingual_article_produces_two_chunks():
    chunks = build_chunks([_article()])
    assert len(chunks) == 2
    assert {c.language for c in chunks} == {"ar", "en"}
    assert all(c.article_number == 1 for c in chunks)
    assert all(c.chunk_id.startswith("article-1-") for c in chunks)


def test_missing_language_is_skipped_not_padded():
    chunks = build_chunks([_article(text_en="")])
    assert len(chunks) == 1
    assert chunks[0].language == "ar"


def test_fully_repealed_article_produces_no_chunks():
    chunks = build_chunks([_article(article_number=55, text_ar="", text_en="", is_repealed=True)])
    assert chunks == []


def test_metadata_is_carried_through():
    chunks = build_chunks([_article(chapter="SECTION I")])
    ar_chunk = next(c for c in chunks if c.language == "ar")
    assert ar_chunk.chapter == "SECTION I"
    assert ar_chunk.citation == "Egyptian Civil Code, Article 1"


def test_embedding_text_prefixes_full_heading_but_leaves_text_clean():
    chunks = build_chunks([_article(book="Book I", chapter="Chapter I", section="Section I", topic="Laws and Rights")])
    ar_chunk = next(c for c in chunks if c.language == "ar")
    assert ar_chunk.text == "نص عربي"  # stored/display text stays untouched
    assert ar_chunk.embedding_text() == "Book I - Chapter I - Section I - Laws and Rights\nنص عربي"


def test_embedding_text_skips_missing_heading_levels():
    chunks = build_chunks([_article(book=None, chapter=None, section="Section I", topic=None)])
    ar_chunk = next(c for c in chunks if c.language == "ar")
    assert ar_chunk.embedding_text() == "Section I\nنص عربي"


def test_embedding_text_falls_back_to_plain_text_with_no_heading():
    chunks = build_chunks([_article(chapter=None, topic=None)])
    ar_chunk = next(c for c in chunks if c.language == "ar")
    assert ar_chunk.embedding_text() == ar_chunk.text
