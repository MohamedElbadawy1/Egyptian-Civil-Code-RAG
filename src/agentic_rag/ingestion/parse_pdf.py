"""
Egyptian Civil Code PDF -> structured per-article JSON.

Strategy: pdftotext -layout preserves a left/right column layout on most
lines (English on the left, Arabic on the right). We split each line on
runs of 2+ spaces, classify each fragment as Arabic or English by script,
strip bidi control chars, and reassemble two parallel text streams
(English, Arabic) in original line order. Article boundaries are detected
on the English stream ("Article N"), which is the most reliable anchor
since Arabic-Indic numerals and RTL reshaping make the Arabic side noisier.

Heading hierarchy (Book > Chapter > Section > numbered topic) is tracked
the same way, anchored on the English side: "BOOK I", "Chapter I" /
"CHAPTER I", "Section I" / "SECTION I", and numbered sub-headings like
"1. Laws and Rights". A heading line is recognized and consumed *before*
either the repeal-marker check or the "append to current article" step,
so it never leaks into the body of whatever article came before it - see
docs/01-corpus-extraction.md for the earlier bug this replaces (the old
tracker only matched fully-uppercase headings, so "Chapter I" / "Section
I" in mixed case were invisible to it and every article ended up with the
same first-heading metadata).

Known rough edges (tracked in docs/01-corpus-extraction.md):
- Some Arabic alef/hamza glyph sequences come out reshaped (e.g. a stray
  alef before a hamza-initial word). Needs a proper Arabic text
  normalizer pass before embedding.
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

# Case-insensitive on purpose: the source PDF is inconsistent, mixing
# "SECTION II" (all caps) with "Section I" (title case) for the same
# hierarchy level. A trailing title fragment is captured where present
# (e.g. "Section I The Right of Ownership in General").
BOOK_RE = re.compile(r'^BOOK\s+([IVXLCDM]+)\.?\s*$', re.IGNORECASE)
CHAPTER_RE = re.compile(r'^Chapter\s+([IVXLCDM]+)\b\.?\s*(.*)$', re.IGNORECASE)
SECTION_RE = re.compile(r'^Section\s+([IVXLCDM]+)\b\.?\s*(.*)$', re.IGNORECASE)
TOPIC_RE = re.compile(r'^(\d+)\.\s+([A-Za-z].*)$')


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

        # Heading lines are recognized (and consumed via `continue`)
        # *before* the repeal-marker check or the article-body append
        # below, so they never end up appended to the previous article's
        # text. A heading also resets every level below it, so a stale
        # section/topic from the previous chapter can't linger.
        m_book = BOOK_RE.match(en)
        if m_book:
            heading_stack['book'] = f"Book {m_book.group(1)}"
            heading_stack['chapter'] = None
            heading_stack['section'] = None
            heading_stack['topic'] = None
            continue

        m_chapter = CHAPTER_RE.match(en)
        if m_chapter:
            label = f"Chapter {m_chapter.group(1)}"
            if m_chapter.group(2):
                label += f" - {m_chapter.group(2).strip()}"
            heading_stack['chapter'] = label
            heading_stack['section'] = None
            heading_stack['topic'] = None
            continue

        m_section = SECTION_RE.match(en)
        if m_section:
            label = f"Section {m_section.group(1)}"
            if m_section.group(2):
                label += f" - {m_section.group(2).strip()}"
            heading_stack['section'] = label
            heading_stack['topic'] = None
            continue

        m_topic = TOPIC_RE.match(en)
        if m_topic:
            heading_stack['topic'] = m_topic.group(2).strip()
            continue

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
