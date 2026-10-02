from agentic_rag.eval.metrics import contains_abstention, hit_at_k, precision_at_k


def test_hit_at_k_true_when_expected_present():
    assert hit_at_k([802, 6, 110], [6]) is True


def test_hit_at_k_false_when_expected_absent():
    assert hit_at_k([802, 949], [6]) is False


def test_hit_at_k_true_if_any_of_multiple_expected_present():
    assert hit_at_k([802, 949], [6, 949]) is True


def test_precision_at_k_counts_only_expected_hits():
    assert precision_at_k([6, 110, 802, 949], [6, 110]) == 0.5


def test_precision_at_k_perfect_when_all_retrieved_expected():
    assert precision_at_k([6, 110], [6, 110, 118]) == 1.0


def test_precision_at_k_empty_retrieved_is_zero_not_undefined():
    assert precision_at_k([], [6]) == 0.0


def test_contains_abstention_detects_arabic_refusal_phrasing():
    answer = "لا تتوفر معلومات كافية في المواد المقدمة للإجابة على هذا السؤال."
    assert contains_abstention(answer) is True


def test_contains_abstention_detects_english_refusal_phrasing():
    answer = "The provided articles do not contain information about this topic."
    assert contains_abstention(answer) is True


def test_contains_abstention_false_for_a_normal_grounded_answer():
    answer = "ليس للصغير غير المميز حق التصرف في ماله (مادة 110)."
    assert contains_abstention(answer) is False
