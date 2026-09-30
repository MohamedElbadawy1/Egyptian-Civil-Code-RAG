from agentic_rag.eval.golden_set import load_golden_set


def test_golden_set_loads_and_has_expected_shape():
    examples = load_golden_set()
    assert len(examples) >= 8
    ids = [ex.id for ex in examples]
    assert len(ids) == len(set(ids)), "golden set ids must be unique"
    for ex in examples:
        assert ex.question
        assert ex.expected_articles
        assert all(isinstance(n, int) for n in ex.expected_articles)
        assert ex.ground_truth


def test_golden_set_covers_both_languages():
    examples = load_golden_set()
    # at least one question should be English, to exercise the API's
    # language-mirroring behavior (see docs/03) during evaluation
    assert any(ex.id.startswith("en-") for ex in examples)
