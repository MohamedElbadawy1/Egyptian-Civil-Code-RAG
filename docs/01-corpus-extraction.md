# 01 - Corpus Extraction

**Status:** Done (v1, known rough edges)
**Date:** 2026-09-24

## What we built
`src/agentic_rag/ingestion/parse_pdf.py` converts the raw bilingual PDF
into `data/processed/civil_code_articles.json`: one record per article
with `article_number`, `text_ar`, `text_en`, `book/chapter/section/topic`
heading context, `is_repealed`, and a `citation` string.

## Why / decisions
- Used `pdftotext -layout` instead of a Python PDF library: the source
  PDF renders Arabic (right) and English (left) as two visual columns,
  and `-layout` is what reliably preserves that column structure as
  parseable whitespace gaps.
- Anchored article boundaries on the English `Article N` heading rather
  than the Arabic `مادة (N)` heading: Arabic-Indic numerals and RTL
  glyph reshaping made the Arabic anchor less reliable to regex against.
- Repealed ranges (e.g. "Articles 54-80 have been repealed") are
  detected and every number in the range is flagged `is_repealed`, but
  we do not invent standalone records for 55-80 since the source PDF
  itself never gives them their own heading.

## How to run
```
pdftotext -layout data/raw/egyptian_civil_code.pdf /tmp/civil_code.txt
python -m agentic_rag.ingestion.parse_pdf --input /tmp/civil_code.txt --output data/processed/civil_code_articles.json
```
or via the DVC stage: `dvc repro build_corpus` (once `dvc.yaml` is added).

## Results / validation
- 1086 article records parsed, numbered 1-1149 (gaps = repealed ranges)
- 0 duplicate article numbers
- 0 records with empty Arabic text

## Known issues / next steps
- Some Arabic alef/hamza glyph sequences come out reshaped (e.g. a stray
  alef before a hamza-initial word) - needs a proper Arabic text
  normalizer before this goes into chunking/embedding.
- Sub-headings sometimes leak into the previous article's body instead
  of starting a fresh heading context.
- No page-number tracking yet (`source_page` is always null) - would help
  with citation display later.
- Repealed spans with no standalone heading (e.g. 55-80) have no record
  of their own; worth a placeholder-record pass if peer reviewers expect
  every number 1-1149 to resolve to *something*.
- **Heading tracker is effectively non-functional.** Verified against the
  live corpus (see docs/02-chunking-embedding.md): every one of the 1086
  articles' `chapter`/`topic` fields resolves to the document's very
  first heading ("SECTION I - 1. Laws and Rights"), including article 802
  near the end of the code. The tracker's `not current` guard means it
  basically never fires again once the first article starts. This matters
  more than it looked like at first pass - it's blocking heading context
  from being usable anywhere downstream (retrieval, citations). Tracked
  as a backlog item; needs a real rewrite of the heading-detection logic
  in `parse_pdf.py`, not a patch.
