"""
Runs the golden Q&A set (eval/golden_qa.json) through the live retrieval
+ generation pipeline, computes deterministic retrieval metrics
(hit_at_k, precision_at_k), and optionally RAGAS's LLM-judged metrics
(faithfulness, answer relevancy, context precision/recall). Both are
logged to MLflow -- same pattern as the indexing runs in
rag/pipeline.py -- so evaluation runs are comparable over time instead of
living only in a one-off terminal scrollback like the manual checks in
docs/02 and docs/03 were.
"""
from __future__ import annotations

import csv
from pathlib import Path

import mlflow

from agentic_rag.api.generation import GenerationClient, format_article_block
from agentic_rag.config import REPO_ROOT
from agentic_rag.eval.golden_set import GoldenExample, load_golden_set
from agentic_rag.eval.metrics import contains_abstention, hit_at_k, precision_at_k, contains_abstention_llm
from agentic_rag.rag.corpus import load_corpus_index
from agentic_rag.rag.pipeline import retrieve

DEFAULT_REPORT_PATH = REPO_ROOT / "reports" / "evaluation_latest.csv"


def run_evaluation(
    golden_set: list[GoldenExample] | None = None,
    top_k: int = 5,
    run_ragas: bool = True,
    report_path: Path = DEFAULT_REPORT_PATH,
    use_hybrid: bool = False,
    alpha: float = 0.5,
) -> Path:
    examples = golden_set or load_golden_set()
    corpus_index = load_corpus_index()
    gen_client = GenerationClient()

    rows = []
    for ex in examples:
        retrieved = retrieve(ex.question, top_k=top_k, use_hybrid=use_hybrid, alpha=alpha)
        retrieved_numbers = [r.article_number for r in retrieved]
        full_articles = [corpus_index[n] for n in retrieved_numbers if n in corpus_index]
        answer = gen_client.answer(ex.question, full_articles)
        # One context string per retrieved article, formatted exactly the
        # way GenerationClient.answer() formatted it for the LLM (both
        # languages included). Previously this picked text_ar OR text_en
        # with a plain `or`, which -- since every article has Arabic text
        # -- always picked Arabic even for English questions (en-01,
        # en-02), silently evaluating faithfulness/context metrics against
        # context the generator didn't actually see in isolation. Reusing
        # format_article_block() keeps this honest to what was generated
        # from, regardless of question language. See docs/07.
        contexts = [format_article_block(a) for a in full_articles]

        rows.append({
            "id": ex.id,
            "question": ex.question,
            "answer": answer,
            "contexts": contexts,
            "ground_truth": ex.ground_truth,
            "retrieved_articles": retrieved_numbers,
            "expected_articles": ex.expected_articles,
            "expect_no_answer": ex.expect_no_answer,
            # hit/precision are meaningless for expect_no_answer questions
            # (there's no correct article -- the correct behavior is
            # abstaining, scored separately as abstention_rate below).
            "hit": None if ex.expect_no_answer else hit_at_k(retrieved_numbers, ex.expected_articles),
            "precision": None if ex.expect_no_answer else precision_at_k(retrieved_numbers, ex.expected_articles),
            "abstained": contains_abstention_llm(ex.question, answer) if ex.expect_no_answer else None,
        })

    retrieval_rows = [r for r in rows if not r["expect_no_answer"]]
    abstention_rows = [r for r in rows if r["expect_no_answer"]]

    hit_rate = sum(r["hit"] for r in retrieval_rows) / len(retrieval_rows) if retrieval_rows else None
    mean_precision = sum(r["precision"] for r in retrieval_rows) / len(retrieval_rows) if retrieval_rows else None
    abstention_rate = sum(r["abstained"] for r in abstention_rows) / len(abstention_rows) if abstention_rows else None

    ragas_scores: dict[str, float] = {}
    if run_ragas:
        ragas_scores = _run_ragas(rows)

    _write_report(rows, report_path)

    with mlflow.start_run(run_name="evaluate_golden_set"):
        mlflow.log_param("golden_set_size", len(examples))
        mlflow.log_param("retrieval_question_count", len(retrieval_rows))
        mlflow.log_param("no_answer_question_count", len(abstention_rows))
        mlflow.log_param("top_k", top_k)
        mlflow.log_param("ragas_enabled", run_ragas)
        mlflow.log_param("use_hybrid", use_hybrid)
        mlflow.log_param("alpha", alpha if use_hybrid else None)
        if hit_rate is not None:
            mlflow.log_metric("hit_rate", hit_rate)
        if mean_precision is not None:
            mlflow.log_metric("mean_precision", mean_precision)
        if abstention_rate is not None:
            mlflow.log_metric("abstention_rate", abstention_rate)
        for name, value in ragas_scores.items():
            mlflow.log_metric(f"ragas_{name}", value)
        mlflow.log_artifact(str(report_path))

    return report_path


def _run_ragas(rows: list[dict]) -> dict[str, float]:
    """Imported lazily so `ragas`/`datasets` aren't required just to import
    this module -- only when someone actually runs an evaluation with
    RAGAS enabled (the default, but --no-ragas skips this entirely)."""
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    ds = Dataset.from_dict({
        "question": [r["question"] for r in rows],
        "answer": [r["answer"] for r in rows],
        "contexts": [r["contexts"] for r in rows],
        "ground_truth": [r["ground_truth"] for r in rows],
    })
    result = evaluate(
        ds,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    )
    # `.items()`/dict-style access on EvaluationResult isn't stable across
    # ragas versions; `.to_pandas()` -> per-metric column mean is the
    # robust way to get aggregate scores regardless of version.
    df = result.to_pandas()
    metric_names = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    return {name: float(df[name].mean()) for name in metric_names if name in df.columns}


def _write_report(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id", "question", "expect_no_answer", "hit", "precision", "abstained",
        "retrieved_articles", "expected_articles", "answer",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] for k in fieldnames})
