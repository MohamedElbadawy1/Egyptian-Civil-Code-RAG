"""
Tests for the heading tracker specifically, since it was broken silently
for a while (see docs/01-corpus-extraction.md). Uses small synthetic
`pdftotext -layout`-style fixtures rather than the full ~1MB real corpus
dump, so these stay fast and self-contained.
"""
from pathlib import Path

from agentic_rag.ingestion.parse_pdf import parse

FIXTURE = """\
BOOK I                                                                   نص عربي
Chapter I                                                                نص عربي
Section I                                                                نص عربي
1. Laws and Rights                                                       نص عربي
Article 1
Some article one text                                                    نص عربي
Section II                                                               نص عربي
Article 2
Some article two text                                                    نص عربي
BOOK II                                                                  نص عربي
Chapter I                                                                نص عربي
Article 3
Some article three text                                                  نص عربي
"""


def test_headings_are_tracked_per_level(tmp_path: Path):
    f = tmp_path / "fixture.txt"
    f.write_text(FIXTURE, encoding="utf-8")
    records = parse(f)
    by_num = {r["article_number"]: r for r in records}

    assert by_num[1]["book"] == "Book I"
    assert by_num[1]["section"] == "Section I"
    assert by_num[1]["topic"] == "Laws and Rights"


def test_new_section_resets_topic_but_keeps_book_and_chapter(tmp_path: Path):
    f = tmp_path / "fixture.txt"
    f.write_text(FIXTURE, encoding="utf-8")
    records = parse(f)
    by_num = {r["article_number"]: r for r in records}

    assert by_num[2]["book"] == "Book I"
    assert by_num[2]["chapter"] == "Chapter I"
    assert by_num[2]["section"] == "Section II"
    assert by_num[2]["topic"] is None  # not re-stated after Section II


def test_new_book_resets_chapter_section_and_topic(tmp_path: Path):
    f = tmp_path / "fixture.txt"
    f.write_text(FIXTURE, encoding="utf-8")
    records = parse(f)
    by_num = {r["article_number"]: r for r in records}

    assert by_num[3]["book"] == "Book II"
    assert by_num[3]["chapter"] == "Chapter I"
    assert by_num[3]["section"] is None
    assert by_num[3]["topic"] is None


def test_heading_lines_do_not_leak_into_previous_article_body(tmp_path: Path):
    f = tmp_path / "fixture.txt"
    f.write_text(FIXTURE, encoding="utf-8")
    records = parse(f)
    by_num = {r["article_number"]: r for r in records}

    # "Section II" must not have become part of article 1's body text
    assert "Section II" not in by_num[1]["text_en"]
    assert "Section" not in by_num[1]["text_en"]
