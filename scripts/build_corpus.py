"""
CLI entrypoint for the corpus-building DVC stage.

Usage:
    python scripts/build_corpus.py \
        --raw-pdf data/raw/egyptian_civil_code.pdf \
        --output data/processed/civil_code_articles.json

This just wires the raw PDF -> pdftotext -layout -> parse_pdf.parse()
pipeline together so it can be a single `dvc.yaml` stage with a clear
dep/out pair. Keep business logic in src/agentic_rag/ingestion/, keep
this file a thin wrapper.
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

from agentic_rag.ingestion.parse_pdf import parse, validate
import json


def pdf_to_layout_text(pdf_path: Path) -> Path:
    tmp = Path(tempfile.mkstemp(suffix='.txt')[1])
    subprocess.run(['pdftotext', '-layout', str(pdf_path), str(tmp)], check=True)
    return tmp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw-pdf', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()

    layout_txt = pdf_to_layout_text(args.raw_pdf)
    records = parse(layout_txt)
    problems = validate(records)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"Parsed {len(records)} articles -> {args.output}")
    if problems:
        print("Validation problems:")
        for p in problems:
            print(f"  - {p}")


if __name__ == '__main__':
    main()
