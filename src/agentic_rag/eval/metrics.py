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
