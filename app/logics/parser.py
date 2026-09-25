import datetime
import json
import re
from collections import Counter
from pathlib import Path

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, model_validator
from pypdf import PdfReader

from app.models import BookMetadata, BookParagraph
from app.openai import get_async_openai_client
from app.settings import settings


class TableOfContentsEntry(BaseModel):
    book_page_start: int
    title: str


class TableOfContents(BaseModel):
    paragraphs: dict[str, TableOfContentsEntry] = Field(default_factory=dict)

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
        return self


def _normalize_toc_payload(
    payload: dict[str, object],
) -> dict[str, dict[str, TableOfContentsEntry]]:
    paragraphs_raw = payload.get("paragraphs")

    if isinstance(paragraphs_raw, dict):
        paragraphs = paragraphs_raw or {}
        return {
            "paragraphs": {
                str(number): TableOfContentsEntry.model_validate(entry)
                for number, entry in dict(paragraphs).items()
            },
        }

    if isinstance(paragraphs_raw, list):
        return {
            "paragraphs": {
                str(index): TableOfContentsEntry.model_validate(item)
                for index, item in enumerate(paragraphs_raw)
                if isinstance(item, dict)
            }
        }

    normalized = {"paragraphs": {}}
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        normalized["paragraphs"][str(key)] = TableOfContentsEntry.model_validate(value)

    if not normalized["paragraphs"]:
        raise ValueError("Table of contents payload does not contain valid entries")

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


def _find_title_pages(reader: PdfReader, title: str) -> list[int]:
    page_count = len(reader.pages)
    preferred_pages = list(range(10, max(10, page_count - 10)))
    fallback_pages = list(range(page_count))
    normalized_titles = [
        _normalize_text(candidate) for candidate in _title_candidates(title)
    ]

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
                return matches

    return []


def _find_page_offset(
    reader: PdfReader,
    entries: list[tuple[str, TableOfContentsEntry]],
) -> int:
    anchors = [
        entry for entry in entries[:20] if len(_normalize_text(entry[1].title)) >= 20
    ][:10]
    if not anchors:
        raise ValueError(
            "Could not find sufficiently specific TOC entries for page offset"
        )

    matches_by_entry = [
        (entry, _find_title_pages(reader, entry[1].title)) for entry in anchors
    ]
    matches_by_entry = [item for item in matches_by_entry if item[1]]
    if not matches_by_entry:
        raise ValueError(
            "Could not find TOC entries in PDF while calculating page offset"
        )

    candidate_offsets = Counter(
        page_number - entry[1].book_page_start
        for entry, page_numbers in matches_by_entry
        for page_number in page_numbers
    )

    scored_offsets: list[tuple[int, int, int]] = []
    for offset in candidate_offsets:
        support = 0
        distance = 0
        for entry, page_numbers in matches_by_entry:
            expected_page = entry[1].book_page_start + offset
            nearest_distance = min(
                abs(page_number - expected_page) for page_number in page_numbers
            )
            if nearest_distance <= 1:
                support += 1
                distance += nearest_distance
        scored_offsets.append((support, -distance, offset))

    support, _, offset = max(scored_offsets)
    required_support = max(2, (len(matches_by_entry) + 1) // 2)
    if support < required_support:
        raise ValueError(
            "Could not determine a consistent page offset: "
            f"{support}/{len(matches_by_entry)} anchors agree"
        )

    return offset


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
                "Return a JSON object with the single top-level key 'paragraphs'. "
                "Never return chapters, parent headings, or any non-leaf section. "
                "Never assign the same book_page_start to two different entries, even if "
                "their titles look similar or belong to different nesting levels."
            ),
        },
        {
            "role": "user",
            "content": f"----- scanned pdf text -----\n{text}",
        },
    ]

    response = await client.chat.completions.create(
        model=settings.parsing_model,
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
    if not toc.paragraphs:
        raise ValueError("LLM returned an empty table of contents")

    ordered_paragraphs = sorted(
        toc.paragraphs.items(), key=lambda item: item[1].book_page_start
    )

    page_offset = _find_page_offset(reader, ordered_paragraphs)

    paragraphs: dict[str, BookParagraph] = {}
    for index, (number, entry) in enumerate(ordered_paragraphs):
        file_start = entry.book_page_start + page_offset
        file_end = _get_file_end(
            index, ordered_paragraphs, page_offset, len(reader.pages)
        )

        if file_start < 0 or file_start >= len(reader.pages) or file_end < file_start:
            raise ValueError(
                f"Invalid page range for paragraph {number}: "
                f"title={entry.title!r}, book_page_start={entry.book_page_start}, "
                f"file_start={file_start}, file_end={file_end}, "
                f"page_offset={page_offset}, page_count={len(reader.pages)}"
            )

        paragraphs[number] = BookParagraph(
            title=entry.title,
            book_page_start=entry.book_page_start,
            file_start=file_start,
            file_end=min(file_end, len(reader.pages) - 1),
        )

    metadata = BookMetadata(
        title="",
        pdf_path=pdf_path,
        created_at=datetime.datetime.now(datetime.UTC).date(),
        paragraphs=paragraphs,
    )
    return metadata
