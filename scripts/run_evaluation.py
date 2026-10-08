"""
CLI entrypoint for the evaluation stage.

Usage:
    uv run python -m scripts.run_evaluation
    uv run python -m scripts.run_evaluation --no-ragas   # skip the slower/paid LLM-judge metrics
    uv run python -m scripts.run_evaluation --hybrid                # hybrid search, default alpha
    uv run python -m scripts.run_evaluation --hybrid --alpha 0.3    # more BM25-weighted
"""
import argparse
from pathlib import Path

from agentic_rag.config import REPO_ROOT
from agentic_rag.eval.run import run_evaluation


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument(
        "--no-ragas",
        action="store_true",
        help="skip RAGAS LLM-judge metrics, only compute retrieval hit_rate/precision",
    )
    ap.add_argument(
        "--hybrid",
        action="store_true",
        help="use Weaviate hybrid search (BM25 + vector fusion) instead of pure vector search",
    )
    ap.add_argument(
        "--alpha",
        type=float,
        default=0.5,
        help="hybrid search weight: 0.0 = pure BM25, 1.0 = pure vector (only used with --hybrid)",
    )
    args = ap.parse_args()

    # Writes hybrid runs to their own file by default so they never
    # clobber evaluation_latest.csv / evaluation_before_hybrid.csv --
    # keeps the before/after comparison artifacts unambiguous.
    report_path = (
        REPO_ROOT / "reports" / "evaluation_after_hybrid.csv"
        if args.hybrid
        else REPO_ROOT / "reports" / "evaluation_latest.csv"
    )

    report_path = run_evaluation(
        top_k=args.top_k,
        run_ragas=not args.no_ragas,
        report_path=report_path,
        use_hybrid=args.hybrid,
        alpha=args.alpha,
    )
    print(f"Evaluation report written to {report_path}")


if __name__ == "__main__":
    main()