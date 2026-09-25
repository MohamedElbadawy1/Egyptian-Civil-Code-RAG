"""
CLI entrypoint for the "embed + index" stage.

Usage:
    python scripts/build_index.py --corpus data/processed/civil_code_articles.json
"""
import argparse
from pathlib import Path

from agentic_rag.rag.pipeline import index_corpus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', type=Path, required=True)
    args = ap.parse_args()

    n = index_corpus(args.corpus)
    print(f"Indexed {n} chunks into Weaviate collection.")


if __name__ == '__main__':
    main()
