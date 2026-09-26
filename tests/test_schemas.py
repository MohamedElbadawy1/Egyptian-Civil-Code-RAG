import pytest
from pydantic import ValidationError

from agentic_rag.api.schemas import AskRequest, AskResponse, RetrievedArticleOut


def test_ask_request_defaults_top_k_to_5():
    req = AskRequest(question="ما هي أهلية التصرف؟")
    assert req.top_k == 5


def test_ask_request_rejects_too_short_question():
    with pytest.raises(ValidationError):
        AskRequest(question="ok")


def test_ask_request_rejects_top_k_out_of_range():
    with pytest.raises(ValidationError):
        AskRequest(question="ما هي أهلية التصرف؟", top_k=20)


def test_ask_response_round_trip():
    resp = AskResponse(
        answer="...",
        articles=[RetrievedArticleOut(article_number=6, citation="Egyptian Civil Code, Article 6", is_repealed=False, score=0.9)],
    )
    assert resp.articles[0].article_number == 6
