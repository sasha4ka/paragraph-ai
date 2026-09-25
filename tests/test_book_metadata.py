import pytest

from app.logics.parser import (
    TableOfContentsEntry,
    _find_page_offset,
    _find_title_page,
    _get_file_end,
    _normalize_toc_payload,
)
from app.models import BookMetadata, BookParagraph


def test_duplicate_paragraph_book_page_starts_are_rejected():
    with pytest.raises(ValueError, match="Duplicate book_page_start"):
        BookMetadata(
            title=None,
            pdf_path="books/test.pdf",
            created_at="2026-09-24",
            paragraphs={
                "1": BookParagraph(
                    title="First",
                    book_page_start=10,
                    file_start=10,
                    file_end=20,
                ),
                "2": BookParagraph(
                    title="Second",
                    book_page_start=10,
                    file_start=21,
                    file_end=30,
                ),
            },
        )


def test_normalize_toc_payload_accepts_list_based_llm_output():
    payload = {
        "paragraphs": [
            {"title": "Глава 1 - Параграф 1", "book_page_start": 10},
            {"title": "Глава 1 - Параграф 2 - Пункт 1", "book_page_start": 20},
        ],
    }

    normalized = _normalize_toc_payload(payload)

    assert normalized["paragraphs"]["0"].book_page_start == 10
    assert normalized["paragraphs"]["1"].book_page_start == 20


def test_find_title_page_matches_leaf_of_hierarchical_title():
    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        def __init__(self):
            self.pages = [
                Page("1 Предмет стереометрии"),
                Page("Оглавление: 1. Предмет стереометрии 3"),
            ]

    assert _find_title_page(Reader(), "Введение - 1. Предмет стереометрии") == 0


def test_file_end_includes_page_where_next_section_starts():
    entries = [
        ("first", TableOfContentsEntry(title="First", book_page_start=10)),
        ("second", TableOfContentsEntry(title="Second", book_page_start=12)),
    ]

    assert _get_file_end(0, entries, page_offset=3, page_count=20) == 15


def test_find_page_offset_uses_consensus_of_multiple_entries():
    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        pages = [
            Page("First distinctive section"),
            Page("Second distinctive section"),
            Page("Third distinctive section"),
            Page("First distinctive section"),
        ]

    entries = [
        (
            "0",
            TableOfContentsEntry(title="First distinctive section", book_page_start=1),
        ),
        (
            "1",
            TableOfContentsEntry(title="Second distinctive section", book_page_start=2),
        ),
        (
            "2",
            TableOfContentsEntry(title="Third distinctive section", book_page_start=3),
        ),
    ]

    assert _find_page_offset(Reader(), entries) == -1
