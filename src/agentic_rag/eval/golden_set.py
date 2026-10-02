"""
Loads the golden evaluation Q&A set used by scripts/run_evaluation.py.

Ground truths in eval/golden_qa.json were drafted directly from the
article text we'd already read while building/debugging retrieval (see
docs/02 and docs/03) -- not sourced from a lawyer. Good enough to catch
retrieval/generation regressions over time; not a substitute for legal
review if this were ever used to make real legal claims to a user.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agentic_rag.config import REPO_ROOT

DEFAULT_GOLDEN_SET_PATH = REPO_ROOT / "eval" / "golden_qa.json"


@dataclass(frozen=True)
class GoldenExample:
    id: str
    question: str
    expected_articles: list[int]
    ground_truth: str
    # True for questions deliberately outside the Civil Code (e.g.
    # criminal/immigration law) -- the "correct" behavior is abstaining,
    # not retrieving a specific article, so these are scored differently
    # (abstention_rate, not hit_at_k/precision_at_k) in eval/run.py.
    expect_no_answer: bool = False


def load_golden_set(path: Path | None = None) -> list[GoldenExample]:
    path = path or DEFAULT_GOLDEN_SET_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        GoldenExample(
            id=item["id"],
            question=item["question"],
            expected_articles=item["expected_articles"],
            ground_truth=item["ground_truth"],
            expect_no_answer=item.get("expect_no_answer", False),
        )
        for item in raw
    ]
