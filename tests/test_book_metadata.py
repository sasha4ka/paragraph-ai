import asyncio
from types import SimpleNamespace

import pytest

from app import books
from app.exc import InvalidTOC
from app.logics.parser import (
    TableOfContentsEntry,
    _extract_numbered_book,
    _find_page_offset,
    _find_title_page,
    _get_file_end,
    _normalize_toc_payload,
)
from app.models import BookMetadata, BookParagraph


def test_numbered_pdf_preserves_titles_and_cuts_shared_page(monkeypatch, tmp_path):
    texts = [
        "1\n§ 1. ПРЕДМЕТ\nОРГАНИЧЕСКОЙ ХИМИИ\nНачало.",
        "2\nКонец первой темы.\n§ 2. НЕФТЬ И СПОСОБЫ\nЕЁ ПЕРЕРАБОТКИ\nВторая тема.",
        "§ 1. Предмет органической химии ...... 1\n§ 2. Нефть ...... 2",
    ]
    reader = SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda text=text: text) for text in texts]
    )
    metadata = _extract_numbered_book(tmp_path / "book.pdf", reader)
    assert metadata is not None
    assert metadata.paragraphs["2"].title == "§ 2. НЕФТЬ И СПОСОБЫ ЕЁ ПЕРЕРАБОТКИ"
    # Metadata from older versions may have a model-generated typo.
    metadata.paragraphs["2"].title = "Глава I - § 2. Ошибочное название"
    monkeypatch.setattr(books, "PdfReader", lambda path: reader)
    book = books.Book(metadata)

    first = asyncio.run(book.get_text(["1"]))
    second = asyncio.run(book.get_text(["2"]))
    assert first.endswith("Конец первой темы.")
    assert "§ 2" not in first
    assert second.startswith("§ 2. НЕФТЬ")
    assert "Конец первой темы" not in second


def test_library_starts_empty_and_ignores_broken_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(books.BooksRepository, "_instance", None)
    repo = books.BooksRepository(tmp_path / "books")
    repo.load_library()
    assert repo.metadata_dir.is_dir()
    (repo.metadata_dir / "invalid.json").write_text("{", encoding="utf-8")
    repo.load_library()
    assert repo.list_books() == []


def test_invalid_pdf_is_removed_from_pending_books(monkeypatch, tmp_path):
    monkeypatch.setattr(books.BooksRepository, "_instance", None)
    repo = books.BooksRepository(tmp_path)
    pdf = tmp_path / "invalid.pdf"
    pdf.write_bytes(b"not a pdf")

    with pytest.raises(InvalidTOC, match="Could not read PDF"):
        asyncio.run(repo.parse_then_add_book(pdf))

    assert repo.list_books() == []
    assert not pdf.exists()


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
        def __init__(self):
            self.pages = [
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
