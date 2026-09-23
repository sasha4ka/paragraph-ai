"""Extraction of textbook paragraphs from PDF files.

The module intentionally returns a plain mapping (``{"1": "...", ...}``) so
the resulting JSON can be consumed directly by the bot without an additional
schema conversion step.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from pypdf import PdfReader


class ParagraphParsingError(RuntimeError):
    """Raised when a book cannot be split into paragraphs."""


class BookParagraphParser:
    """Extract sections headed by markers such as ``§ 1.`` from a PDF book.

    The parser works page by page, which makes it possible to discard page
    numbers and to detect answer/index pages containing repeated paragraph
    markers.  The marker expression is configurable for books using a
    different section convention.

    Args:
        book_path: Path to a PDF with an embedded text layer.
        marker_pattern: Regular expression with named groups ``number`` and
            ``title``. It must match a marker at the beginning of a line.
        boundary_pattern: Headings which end a paragraph but are not themselves
            paragraphs (chapter summaries, practical work, indexes, etc.).
        min_text_characters: Minimum amount of text expected in the PDF. This
            provides a useful error for scanned books that require OCR.
        page_text_extractor: Optional extractor used mainly for tests. It must
            accept a pypdf page and return text (or ``None``).
    """

    DEFAULT_MARKER_PATTERN = r"^\s*§\s*(?P<number>\d+)\s*[.．]?\s*(?P<title>\S.*)?$"
    _PAGE_NUMBER_RE = re.compile(r"^\s*[–—-]?\s*\d{1,4}\s*[–—-]?\s*$")
    _TOC_LEADER_RE = re.compile(r"(?:\.{3,}|…{2,})")
    _SPACE_RE = re.compile(r"[ \t\u00a0]+")

    def __init__(
        self,
        book_path: str | Path,
        *,
        marker_pattern: str | re.Pattern[str] = DEFAULT_MARKER_PATTERN,
        boundary_pattern: str | re.Pattern[str] = (
            r"^\s*(?:практическая\s+работа\s+\d+|выводы\s+к\s+главе\b|"
            r"предметный\s+указатель\b|ответы\s+к\s+заданиям\b|"
            r"оглавление\b|содержание\b)"
        ),
        min_text_characters: int = 100,
        page_text_extractor: Callable[[Any], str | None] | None = None,
    ) -> None:
        self.book_path = Path(book_path)
        self.marker_re = (
            re.compile(marker_pattern)
            if isinstance(marker_pattern, str)
            else marker_pattern
        )
        self.boundary_re = (
            re.compile(boundary_pattern, re.IGNORECASE)
            if isinstance(boundary_pattern, str)
            else boundary_pattern
        )
        self.min_text_characters = min_text_characters
        self.page_text_extractor = page_text_extractor or self._extract_page_text

        required_groups = {"number", "title"}
        if not required_groups.issubset(self.marker_re.groupindex):
            raise ValueError(
                "marker_pattern must contain named groups 'number' and 'title'"
            )

    @staticmethod
    def _extract_page_text(page: Any) -> str:
        return page.extract_text() or ""

    @staticmethod
    def _natural_number(value: str) -> tuple[int, str]:
        """Return a stable sort key without losing the original marker text."""
        return int(value), value

    def _clean_page_lines(self, text: str) -> list[str]:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\x00", "").replace("\u00ad", "")
        lines = [self._SPACE_RE.sub(" ", line).strip() for line in text.splitlines()]

        # PDF extractors commonly put the printed page number at either edge.
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()
        if lines and self._PAGE_NUMBER_RE.fullmatch(lines[0]):
            lines.pop(0)
        if lines and self._PAGE_NUMBER_RE.fullmatch(lines[-1]):
            lines.pop()

        # Collapse runs of blank lines while retaining paragraph boundaries.
        cleaned: list[str] = []
        for line in lines:
            if line or (cleaned and cleaned[-1]):
                cleaned.append(line)
        while cleaned and not cleaned[-1]:
            cleaned.pop()
        return cleaned

    def _match_marker(self, line: str) -> re.Match[str] | None:
        return self.marker_re.match(line)

    def _is_heading(self, match: re.Match[str]) -> bool:
        title = (match.group("title") or "").strip()
        if not title or self._TOC_LEADER_RE.search(title):
            return False

        # Exercise answer lines usually look like "§ 3. 7. ...". A real
        # textbook heading starts with a word (possibly after punctuation).
        first_content = title.lstrip("«„\"'([{—–- ")
        return bool(first_content and first_content[0].isalpha())

    def _iter_pages(self) -> Iterator[list[str]]:
        if not self.book_path.is_file():
            raise FileNotFoundError(f"Book not found: {self.book_path}")
        if self.book_path.suffix.lower() != ".pdf":
            raise ValueError(f"Only PDF books are supported: {self.book_path}")

        try:
            reader = PdfReader(self.book_path)
        except Exception as exc:  # pypdf exposes several backend exceptions
            raise ParagraphParsingError(
                f"Cannot open PDF {self.book_path}: {exc}"
            ) from exc

        extracted_characters = 0
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = self.page_text_extractor(page) or ""
            except Exception as exc:
                raise ParagraphParsingError(
                    f"Cannot extract text from page {page_number}: {exc}"
                ) from exc
            extracted_characters += len(text.strip())
            yield self._clean_page_lines(text)

        if extracted_characters < self.min_text_characters:
            raise ParagraphParsingError(
                "The PDF contains too little extractable text. "
                "It is probably scanned and must be OCR-processed first."
            )

    @staticmethod
    def _join_lines(lines: list[str]) -> str:
        """Normalize whitespace without destroying meaningful line breaks."""
        result: list[str] = []
        for line in lines:
            if line or (result and result[-1]):
                result.append(line.rstrip())
        while result and not result[-1]:
            result.pop()
        return "\n".join(result).strip()

    def parse(self) -> dict[str, str]:
        """Parse the PDF and return paragraph number -> complete paragraph text."""
        paragraphs: dict[str, str] = {}
        current_number: str | None = None
        current_lines: list[str] = []

        for lines in self._iter_pages():
            page_markers = [
                match
                for line in lines
                if (match := self._match_marker(line)) is not None
            ]
            repeated = [
                match
                for match in page_markers
                if match.group("number") in paragraphs
                or match.group("number") == current_number
            ]

            # Answer keys and indexes contain several already-seen markers on
            # one page. Stop before adding those pages to the final paragraph.
            if current_number is not None and len(repeated) >= 2:
                break

            for line in lines:
                if self.boundary_re.match(line):
                    if current_number is not None:
                        paragraphs[current_number] = self._join_lines(current_lines)
                        current_number = None
                        current_lines = []
                    continue

                match = self._match_marker(line)
                if match is not None and self._is_heading(match):
                    number = match.group("number")

                    # A repeated marker is normally a cross-reference or an
                    # index entry, never a new paragraph body.
                    if number in paragraphs or number == current_number:
                        if current_number is not None:
                            current_lines.append(line)
                        continue

                    if current_number is not None:
                        paragraphs[current_number] = self._join_lines(current_lines)
                    current_number = number
                    current_lines = [line]
                elif current_number is not None:
                    current_lines.append(line)

        if current_number is not None:
            paragraphs[current_number] = self._join_lines(current_lines)

        if not paragraphs:
            raise ParagraphParsingError(
                "No paragraph headings were found. Adjust marker_pattern for "
                "this book or OCR the PDF if it has no text layer."
            )

        # Numeric ordering makes JSON deterministic even if a PDF stores pages
        # in an unusual internal order.
        return dict(
            sorted(
                paragraphs.items(),
                key=lambda item: self._natural_number(item[0]),
            )
        )

    def save_json(
        self,
        output_path: str | Path,
        paragraphs: dict[str, str] | None = None,
        *,
        indent: int = 2,
    ) -> Path:
        """Write parsed paragraphs as UTF-8 JSON and return the output path."""
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = self.parse() if paragraphs is None else paragraphs
        destination.write_text(
            json.dumps(data, ensure_ascii=False, indent=indent) + "\n",
            encoding="utf-8",
        )
        return destination

    def parse_to_json(self, output_path: str | Path, *, indent: int = 2) -> Path:
        """Convenience wrapper combining :meth:`parse` and :meth:`save_json`."""
        paragraphs = self.parse()
        return self.save_json(output_path, paragraphs, indent=indent)


# A short alias is convenient at call sites and preserves a natural public API.
ParagraphParser = BookParagraphParser


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract §-numbered textbook paragraphs from a PDF into JSON."
    )
    parser.add_argument("book", type=Path, help="source PDF file")
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="output JSON (default: source name with .json suffix)",
    )
    return parser


def main() -> None:
    args = _build_cli().parse_args()
    output = args.output or args.book.with_suffix(".json")
    book_parser = BookParagraphParser(args.book)
    parsed = book_parser.parse()
    book_parser.save_json(output, parsed)
    print(f"Extracted {len(parsed)} paragraphs to {output}")


if __name__ == "__main__":
    main()
