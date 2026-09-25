import datetime
import json
import re
from pathlib import Path

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, model_validator
from pypdf import PdfReader

from app.books import BooksRepository
from app.models import BookChapter, BookMetadata, BookParagraph
from app.openai import get_async_openai_client
from app.settings import settings


class TableOfContentsEntry(BaseModel):
    book_page_start: int
    title: str


class TableOfContents(BaseModel):
    paragraphs: dict[str, TableOfContentsEntry] = Field(default_factory=dict)
    chapters: dict[str, TableOfContentsEntry] = Field(default_factory=dict)

    @staticmethod
    def _validate_unique_starts(
        entries: dict[str, TableOfContentsEntry], category: str
    ) -> None:
        starts = [entry.book_page_start for entry in entries.values()]
        duplicates = sorted({start for start in starts if starts.count(start) > 1})
        if duplicates:
            raise ValueError(
                f"Duplicate book_page_start values in {category}: {duplicates}"
            )

    @model_validator(mode="after")
    def validate_unique_starts(self) -> "TableOfContents":
        self._validate_unique_starts(self.paragraphs, "paragraphs")
        self._validate_unique_starts(self.chapters, "chapters")

        paragraph_starts = {entry.book_page_start for entry in self.paragraphs.values()}
        chapter_starts = {entry.book_page_start for entry in self.chapters.values()}
        shared_starts = sorted(paragraph_starts & chapter_starts)
        if shared_starts:
            raise ValueError(
                "Duplicate book_page_start values across paragraphs and chapters: "
                f"{shared_starts}"
            )
        return self


def _looks_like_chapter_key(key: str) -> bool:
    normalized = key.strip()
    return bool(re.fullmatch(r"[IVXLCDM]+", normalized, flags=re.IGNORECASE)) or bool(
        re.fullmatch(r"[A-ZА-ЯЁ]+", normalized)
    )


def _normalize_toc_payload(
    payload: dict[str, object],
) -> dict[str, dict[str, TableOfContentsEntry]]:
    paragraphs_raw = payload.get("paragraphs")
    chapters_raw = payload.get("chapters")

    if isinstance(paragraphs_raw, dict) or isinstance(chapters_raw, dict):
        paragraphs = paragraphs_raw or {}
        chapters = chapters_raw or {}
        return {
            "paragraphs": {
                str(number): TableOfContentsEntry.model_validate(entry)
                for number, entry in dict(paragraphs).items()
            },
            "chapters": {
                str(number): TableOfContentsEntry.model_validate(entry)
                for number, entry in dict(chapters).items()
            },
        }

    if isinstance(paragraphs_raw, list) or isinstance(chapters_raw, list):
        normalized = {"paragraphs": {}, "chapters": {}}
        for category_name, entries in (
            ("paragraphs", paragraphs_raw),
            ("chapters", chapters_raw),
        ):
            if not isinstance(entries, list):
                continue
            for index, item in enumerate(entries):
                if not isinstance(item, dict):
                    continue
                normalized[category_name][str(index)] = (
                    TableOfContentsEntry.model_validate(item)
                )
        if normalized["paragraphs"] or normalized["chapters"]:
            return normalized

    normalized = {"paragraphs": {}, "chapters": {}}
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        entry = TableOfContentsEntry.model_validate(value)
        target = "chapters" if _looks_like_chapter_key(str(key)) else "paragraphs"
        normalized[target][str(key)] = entry

    if not normalized["paragraphs"] and not normalized["chapters"]:
        raise ValueError("Table of contents payload does not contain valid entries")

    if not normalized["chapters"] and set(payload) & {"I", "II", "III", "IV"}:
        for key, value in payload.items():
            if not isinstance(value, dict):
                continue
            if _looks_like_chapter_key(str(key)):
                normalized["chapters"][str(key)] = TableOfContentsEntry.model_validate(
                    value
                )

    return normalized


def _extract_toc_text(reader: PdfReader) -> str:
    page_count = len(reader.pages)
    page_numbers = sorted(
        set(range(min(10, page_count)))
        | set(range(max(0, page_count - 10), page_count))
    )

    return "\n".join(
        f"--- PDF page {page_number + 1} ---\n"
        f"{reader.pages[page_number].extract_text() or ''}"
        for page_number in page_numbers
    )


def _normalize_text(value: str) -> str:
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip().casefold()


def _title_candidates(title: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\s+-\s+", title) if part.strip()]
    return [" - ".join(parts[index:]) for index in range(len(parts))]


def _find_title_page(reader: PdfReader, title: str) -> int:
    normalized_titles = [
        _normalize_text(candidate) for candidate in _title_candidates(title)
    ]
    page_count = len(reader.pages)
    preferred_pages = range(10, max(10, page_count - 10))
    fallback_pages = range(page_count)

    for page_numbers in (preferred_pages, fallback_pages):
        page_texts = {
            page_number: _normalize_text(reader.pages[page_number].extract_text() or "")
            for page_number in page_numbers
        }
        for normalized_title in normalized_titles:
            if not normalized_title:
                continue
            matches = [
                page_number
                for page_number, page_text in page_texts.items()
                if normalized_title in page_text
            ]
            if matches:
                return matches[0]

    raise ValueError(f"Could not find paragraph title in PDF: {title}")


def _get_file_end(
    index: int,
    entries: list[tuple[str, TableOfContentsEntry]],
    page_offset: int,
    page_count: int,
) -> int:
    if index + 1 < len(entries):
        return min(entries[index + 1][1].book_page_start + page_offset, page_count - 1)
    return page_count - 1


async def _parse_table_of_contents(text: str, client: AsyncOpenAI) -> TableOfContents:
    messages = [
        {
            "role": "system",
            "content": (
                "Extract only the deepest / most specific entries from the book's "
                "table of contents. Ignore parent headings and repeated labels when "
                "the book has chapters, paragraphs, subparagraphs, or points. "
                "Return the final leaf sections only. "
                "Each returned value must contain book_page_start (integer) and "
                "title (string). For the title, build a full hierarchical path in the "
                "exact order from the book, for example: 'Глава 1 - Параграф 3 - Пункт 89'. "
                "Use the section labels exactly as they appear in the book, without "
                "translating, shortening, or normalizing them. For example, keep 'Глава', "
                "'Параграф', 'Пункт', 'Раздел', 'Тема' exactly as in the source text. "
                "Do not output a separate entry for a chapter or paragraph if it is only a "
                "parent heading; only the most granular section should be kept. "
                "Return a JSON object with top-level keys 'paragraphs' and 'chapters', "
                "but in practice the final leaf entries should usually go under 'paragraphs'; "
                "'chapters' is only for true chapter-root entries when no deeper leaf exists. "
                "Never assign the same book_page_start to two different entries, even if "
                "their titles look similar or belong to different nesting levels."
            ),
        },
        {
            "role": "user",
            "content": f"----- scanned pdf text -----\n{text}",
        },
    ]

    try:
        response = await client.chat.completions.parse(
            model=settings.openai_model,
            messages=messages,
            response_format=TableOfContents,
        )
        if response is not None and getattr(response, "choices", None):
            parsed = response.choices[0].message.parsed
            if parsed is not None:
                return parsed

            content = response.choices[0].message.content
            if content:
                payload = json.loads(content)
                if isinstance(payload, dict):
                    return TableOfContents.model_validate(
                        _normalize_toc_payload(payload)
                    )
    except (AttributeError, TypeError, ValueError):
        pass

    response = await client.chat.completions.create(
        model=settings.openai_model,
        response_format={"type": "json_object"},
        messages=messages,
    )
    if not response.choices:
        raise ValueError("LLM returned no choices while extracting table of contents")

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned an empty table of contents")

    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise TypeError("LLM returned an invalid table of contents format")

    return TableOfContents.model_validate(_normalize_toc_payload(payload))


async def parse_book(
    path: str | Path, client: AsyncOpenAI | None = None
) -> BookMetadata:
    pdf_path = Path(path)
    reader = PdfReader(pdf_path)
    if not reader.pages:
        raise ValueError(f"PDF contains no pages: {pdf_path}")

    toc = await _parse_table_of_contents(
        _extract_toc_text(reader),
        client if client is not None else get_async_openai_client(),
    )
    if not toc.paragraphs and not toc.chapters:
        raise ValueError("LLM returned an empty table of contents")

    ordered_paragraphs = sorted(
        toc.paragraphs.items(), key=lambda item: item[1].book_page_start
    )
    ordered_chapters = sorted(
        toc.chapters.items(), key=lambda item: item[1].book_page_start
    )

    first_entry = (ordered_paragraphs or ordered_chapters)[0][1]
    first_file_start = _find_title_page(reader, first_entry.title)
    page_offset = first_file_start - first_entry.book_page_start

    paragraphs: dict[str, BookParagraph] = {}
    for index, (number, entry) in enumerate(ordered_paragraphs):
        file_start = entry.book_page_start + page_offset
        file_end = _get_file_end(
            index, ordered_paragraphs, page_offset, len(reader.pages)
        )

        if file_start < 0 or file_start >= len(reader.pages) or file_end < file_start:
            raise ValueError(f"Invalid page range for paragraph: {number}")

        paragraphs[number] = BookParagraph(
            title=entry.title,
            book_page_start=entry.book_page_start,
            file_start=file_start,
            file_end=min(file_end, len(reader.pages) - 1),
        )

    chapters: dict[str, BookChapter] = {}
    for index, (number, entry) in enumerate(ordered_chapters):
        file_start = entry.book_page_start + page_offset
        file_end = _get_file_end(
            index, ordered_chapters, page_offset, len(reader.pages)
        )

        if file_start < 0 or file_start >= len(reader.pages) or file_end < file_start:
            raise ValueError(f"Invalid page range for chapter: {number}")

        chapters[number] = BookChapter(
            title=entry.title,
            book_page_start=entry.book_page_start,
            file_start=file_start,
            file_end=min(file_end, len(reader.pages) - 1),
        )

    metadata = BookMetadata(
        pdf_path=pdf_path,
        created_at=datetime.datetime.now(datetime.UTC).date(),
        paragraphs=paragraphs,
        chapters=chapters,
    )
    BooksRepository().add_book(metadata)
    return metadata
