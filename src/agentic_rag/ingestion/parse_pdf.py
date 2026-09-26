"""
Egyptian Civil Code PDF -> structured per-article JSON.

Strategy: pdftotext -layout preserves a left/right column layout on most
lines (English on the left, Arabic on the right). We split each line on
runs of 2+ spaces, classify each fragment as Arabic or English by script,
strip bidi control chars, and reassemble two parallel text streams
(English, Arabic) in original line order. Article boundaries are detected
on the English stream ("Article N"), which is the most reliable anchor
since Arabic-Indic numerals and RTL reshaping make the Arabic side noisier.

Known rough edges (tracked in docs/01-corpus-extraction.md):
- Some Arabic alef/hamza glyph sequences come out reshaped (e.g. a stray
  alef before a hamza-initial word). Needs a proper Arabic text
  normalizer pass before embedding.
- Sub-headings that appear on the same "paragraph" as the previous
  article's closing line can leak into that article's text instead of
  starting a fresh heading context.
- Repealed ranges (e.g. Articles 54-80) are flagged via a `repealed_set`
  but only the anchor article gets its own record; the source PDF itself
  never gives 55-80 their own "Article N" headings, so there is nothing
  to promote to a full record without inventing data.
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path

BIDI_CHARS = '\u200e\u200f\u202a\u202b\u202c\u202d\u202e'
BIDI_RE = re.compile(f'[{BIDI_CHARS}]')
ARABIC_RE = re.compile(r'[\u0600-\u06FF]')
SPLIT_RE = re.compile(r'\s{2,}')

ARABIC_INDIC_DIGITS = '٠١٢٣٤٥٦٧٨٩'


def normalize_digits(s: str) -> str:
    return s.translate(str.maketrans(ARABIC_INDIC_DIGITS, '0123456789'))


def clean(s: str) -> str:
    s = BIDI_RE.sub('', s)
    s = unicodedata.normalize('NFC', s)
    return s.strip()


def split_line(line: str) -> tuple[str, str]:
    """Return (english_fragment, arabic_fragment) for one line of -layout text."""
    frags = [f for f in SPLIT_RE.split(line) if f.strip()]
    en_parts, ar_parts = [], []
    for f in frags:
        c = clean(f)
        if not c:
            continue
        if ARABIC_RE.search(c):
            ar_parts.append(c)
        else:
            en_parts.append(c)
    return ' '.join(en_parts).strip(), ' '.join(ar_parts).strip()


ARTICLE_EN_RE = re.compile(r'^Article\s+(\d+)\s*$', re.IGNORECASE)
REPEALED_RANGE_RE = re.compile(r'Articles?\s+(\d+)\s*-\s*(\d+)\s+(?:have been\s+)?repealed', re.IGNORECASE)
REPEALED_SINGLE_RE = re.compile(r'^Article\s+(\d+)\s+repealed', re.IGNORECASE)


def parse(layout_text_path: Path) -> list[dict]:
    """Parse a `pdftotext -layout` text dump of the Civil Code into article records."""
    raw_lines = layout_text_path.read_text(encoding='utf-8').splitlines()

    records: list[dict] = []
    current: dict | None = None
    repealed_set: set[int] = set()
    heading_stack = {'book': None, 'chapter': None, 'section': None, 'topic': None}

    def flush():
        nonlocal current
        if current is not None:
            current['text_en'] = current['text_en'].strip()
            current['text_ar'] = current['text_ar'].strip()
            records.append(current)
            current = None

    for raw in raw_lines:
        line = raw.rstrip('\n')
        if not line.strip():
            continue
        en, ar = split_line(line)

        m_range = REPEALED_RANGE_RE.search(en)
        if m_range:
            lo, hi = int(m_range.group(1)), int(m_range.group(2))
            repealed_set.update(range(lo, hi + 1))

        m_single = REPEALED_SINGLE_RE.match(en)
        if m_single:
            repealed_set.add(int(m_single.group(1)))

        m = ARTICLE_EN_RE.match(en)
        if m:
            flush()
            current = {
                'article_number': int(m.group(1)),
                'book': heading_stack['book'],
                'chapter': heading_stack['chapter'],
                'section': heading_stack['section'],
                'topic': heading_stack['topic'],
                'text_ar': '',
                'text_en': '',
                'is_repealed': False,
                'source_page': None,  # TODO: track page number via form-feed splitting
                'citation': f"Egyptian Civil Code, Article {m.group(1)}",
            }
            continue

        # Crude heading tracker: short all-caps English lines outside an
        # article update the chapter; numbered "N. Topic" lines update topic.
        if en and en.isupper() and len(en.split()) <= 8 and not current:
            heading_stack['chapter'] = en
        elif en and re.match(r'^\d+\.\s+\S', en) and not current:
            heading_stack['topic'] = en

        if current is not None:
            current['text_en'] += (' ' if current['text_en'] else '') + en
            current['text_ar'] += (' ' if current['text_ar'] else '') + ar

    flush()

    for r in records:
        if r['article_number'] in repealed_set:
            r['is_repealed'] = True

    return records


def validate(records: list[dict]) -> list[str]:
    """Return a list of validation problems (empty list = clean)."""
    problems = []
    nums = [r['article_number'] for r in records]
    dupes = {n for n in nums if nums.count(n) > 1}
    if dupes:
        problems.append(f"duplicate article numbers: {sorted(dupes)}")
    empty_ar = [r['article_number'] for r in records if not r['text_ar']]
    if empty_ar:
        problems.append(f"{len(empty_ar)} records with empty text_ar: {empty_ar[:10]}...")
    huge = [r['article_number'] for r in records if len(r['text_en']) > 4000]
    if huge:
        problems.append(f"suspiciously long records (possible failed split): {huge}")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, required=True, help='pdftotext -layout output (.txt)')
    ap.add_argument('--output', type=Path, required=True, help='destination JSON path')
    args = ap.parse_args()

    records = parse(args.input)
    problems = validate(records)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"Parsed {len(records)} article records -> {args.output}")
    if problems:
        print("Validation problems:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("Validation: OK")


if __name__ == '__main__':
    main()
