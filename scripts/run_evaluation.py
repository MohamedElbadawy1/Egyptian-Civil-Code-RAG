"""
CLI entrypoint for the evaluation stage.

Usage:
    uv run python -m scripts.run_evaluation
    uv run python -m scripts.run_evaluation --no-ragas   # skip the slower/paid LLM-judge metrics
"""
import argparse

from agentic_rag.eval.run import run_evaluation


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument(
        "--no-ragas",
        action="store_true",
        help="skip RAGAS LLM-judge metrics, only compute retrieval hit_rate/precision",
    )
    args = ap.parse_args()

    report_path = run_evaluation(top_k=args.top_k, run_ragas=not args.no_ragas)
    print(f"Evaluation report written to {report_path}")


if __name__ == "__main__":
    main()
