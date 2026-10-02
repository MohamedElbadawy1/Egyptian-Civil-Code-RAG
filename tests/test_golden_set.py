from agentic_rag.eval.golden_set import load_golden_set


def test_golden_set_loads_and_has_expected_shape():
    examples = load_golden_set()
    assert len(examples) >= 35
    ids = [ex.id for ex in examples]
    assert len(ids) == len(set(ids)), "golden set ids must be unique"
    for ex in examples:
        assert ex.question
        assert ex.ground_truth
        assert all(isinstance(n, int) for n in ex.expected_articles)
        # every question has either expected articles, or is explicitly
        # flagged as deliberately out-of-scope (expect_no_answer) -- never
        # neither, which would be an ungraded question
        assert ex.expected_articles or ex.expect_no_answer


def test_golden_set_covers_both_languages():
    examples = load_golden_set()
    # at least one question should be English, to exercise the API's
    # language-mirroring behavior (see docs/03) during evaluation
    assert any(ex.id.startswith("en-") for ex in examples)


def test_golden_set_covers_multi_article_questions():
    examples = load_golden_set()
    assert any(len(ex.expected_articles) > 1 for ex in examples)


def test_golden_set_covers_out_of_scope_questions():
    examples = load_golden_set()
    no_answer = [ex for ex in examples if ex.expect_no_answer]
    assert len(no_answer) >= 1
    for ex in no_answer:
        assert ex.expected_articles == []
