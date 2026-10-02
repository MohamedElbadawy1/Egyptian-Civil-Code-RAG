from agentic_rag.api.generation import build_context, format_article_block


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


def test_format_article_block_matches_what_build_context_uses_per_article():
    # build_context() is just format_article_block() joined with "\n\n" --
    # callers that need one block per article (eval/run.py, for RAGAS
    # contexts) must see exactly the same text per article, not a
    # different reconstruction of it. See docs/07 for the bug this guards
    # against (contexts silently defaulting to Arabic-only for English
    # questions).
    a1, a2 = _article(article_number=6), _article(article_number=110)
    assert build_context([a1, a2]) == format_article_block(a1) + "\n\n" + format_article_block(a2)


def test_format_article_block_includes_both_languages():
    block = format_article_block(_article())
    assert "AR: نص عربي" in block
    assert "EN: English text" in block
