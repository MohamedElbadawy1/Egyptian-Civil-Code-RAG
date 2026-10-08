"""
Deterministic retrieval metrics -- no LLM judge needed, unlike the RAGAS
metrics in run.py. Cheap to compute and unit-test, and the direct
quantified version of the manual "is article X actually relevant" checks
done by hand in docs/02 and docs/03 (802/949 mis-ranking, etc.) -- now
reproducible across the whole golden set instead of one anecdotal query.
"""
from __future__ import annotations


def hit_at_k(retrieved: list[int], expected: list[int]) -> bool:
    """True if any expected article appears anywhere in the retrieved list."""
    return any(a in retrieved for a in expected)


def precision_at_k(retrieved: list[int], expected: list[int]) -> float:
    """Fraction of retrieved articles that are actually in the expected set.
    0.0 for an empty retrieval (not undefined) -- an empty result is a
    failure to retrieve anything relevant, which precision should reflect."""
    if not retrieved:
        return 0.0
    hits = sum(1 for a in retrieved if a in expected)
    return hits / len(retrieved)


# Simple substring heuristic, not a classifier -- good enough to catch the
# system prompt's own phrasing (see api/generation.py's SYSTEM_PROMPT,
# which asks the model to say so explicitly when context is insufficient)
# but will miss paraphrased refusals and could false-positive on an answer
# that happens to contain one of these words. Treat abstention_rate as a
# directional signal, not a precise score -- see docs/07.
_ABSTENTION_MARKERS = [
    "لا تتوفر", "لا توجد معلومات", "لا يغطي", "خارج نطاق", "غير كافية",
    "لا يحتوي", "لا تتضمن", "غير متوفرة",
     "لا يمكن",       
    "لا توجد",       
    "لا تحتوي",
    "لا تتضمن",  
    "do not have", "does not have", "not contain", "not covered",
    "cannot answer", "no information", "insufficient information",
    "outside the scope", "not available in",
]


def contains_abstention(answer: str) -> bool:
    """True if the answer looks like it declined to answer rather than
    guessing -- used to score the golden set's `expect_no_answer`
    questions (hit_at_k/precision_at_k don't apply to those: there's no
    correct article to retrieve, the correct behavior is abstaining)."""
    lowered = answer.lower()
    return any(marker.lower() in lowered for marker in _ABSTENTION_MARKERS)

import os
from openai import OpenAI

_judge_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def contains_abstention_llm(question: str, answer: str) -> bool:
    """LLM-judged abstention check for the golden set's expect_no_answer
    questions. Robust to paraphrasing (unlike the substring heuristic
    above, which repeatedly missed new refusal phrasings in practice —
    see docs/07-evaluation-monitoring.md for the history).

    Only used on the ~2 deliberately out-of-scope questions in the
    golden set, so the extra API call per eval run is negligible.
    """
    prompt = (
        "You are grading whether an AI assistant's answer is a genuine "
        "refusal/abstention (it says the provided legal context does not "
        "contain enough information to answer definitively) versus a "
        "substantive answer that states a definitive legal rule or fact.\n\n"
        f"Question: {question}\n"
        f"Answer: {answer}\n\n"
        "Reply with exactly one word: ABSTAINED or ANSWERED."
    )
    # gpt-5-mini is a reasoning model and rejects non-default temperature,
    # same constraint as GenerationClient.answer() in api/generation.py
    response = _judge_client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    verdict = response.choices[0].message.content.strip().upper()
    return "ABSTAINED" in verdict