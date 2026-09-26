from agentic_rag.api.generation import build_context


def _article(**overrides):
    base = {
        "article_number": 6,
        "book": None,
        "chapter": "SECTION I",
        "topic": "1. Laws and Rights",
        "text_ar": "نص عربي",
        "text_en": "English text",
        "is_repealed": False,
    }
    base.update(overrides)
    return base


def test_build_context_includes_both_languages_and_heading():
    ctx = build_context([_article()])
    assert "Article 6" in ctx
    assert "SECTION I - 1. Laws and Rights" in ctx
    assert "AR: نص عربي" in ctx
    assert "EN: English text" in ctx


def test_build_context_flags_repealed_articles():
    ctx = build_context([_article(is_repealed=True)])
    assert "[REPEALED]" in ctx


def test_build_context_skips_missing_language():
    ctx = build_context([_article(text_en="")])
    assert "AR: نص عربي" in ctx
    assert "EN:" not in ctx


def test_build_context_joins_multiple_articles():
    ctx = build_context([_article(article_number=6), _article(article_number=110)])
    assert "Article 6" in ctx
    assert "Article 110" in ctx
