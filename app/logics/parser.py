import asyncio
import datetime
import json
import logging
import re
from collections import Counter
from itertools import pairwise
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, model_validator
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.exc import InvalidTOC
from app.models import BookMetadata, BookParagraph
from app.openai import APIError, AsyncOpenAI, get_async_openai_client
from app.settings import settings

logger = logging.getLogger("book-parser")
logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)

_SECTION_NUMBER = re.compile(r"§[ \t]*(\d+)\b")
_NUMBERED_HEADING = re.compile(
    r"^[ \t]*§[ \t]*(\d+)\b[ \t]*\.?[ \t]+([^\n]+)", re.MULTILINE
)


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
    page_texts: list[str] = []
    for page_number in page_numbers:
        page_text = reader.pages[page_number].extract_text() or ""
        logger.debug(
            "TOC input PDF page %s/%s: extracted_chars=%s",
            page_number + 1,
            page_count,
            len(page_text),
        )
        page_texts.append(f"--- PDF page {page_number + 1} ---\n{page_text}")

    text = "\n".join(page_texts)
    logger.debug(
        "Prepared TOC input: pdf_pages=%s, selected_pages=%s, total_chars=%s",
        page_count,
        [page_number + 1 for page_number in page_numbers],
        len(text),
    )
    return text


def _normalize_text(value: str) -> str:
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip().casefold()


def _title_candidates(title: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\s+-\s+", title) if part.strip()]
    return [" - ".join(parts[index:]) for index in range(len(parts))]


def find_heading_start(text: str, title: str) -> int | None:
    """Locate a section heading in extracted page text, including wrapped titles."""
    candidates = _title_candidates(title)
    leaf_title = candidates[-1] if candidates else title
    words = re.findall(r"\w+", leaf_title.casefold())
    if words:
        pattern = r"^[^\S\n]*(?:§[^\S\n]*)?" + r"[^\w]+".join(
            re.sub("[её]", "[её]", re.escape(word))
            for word in words
        ) + r"(?!\w)"
        match = re.search(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
        if match:
            return match.start()

    # Older metadata may contain a misspelled title from the model.
    number = _SECTION_NUMBER.search(title)
    if number:
        for match in _NUMBERED_HEADING.finditer(text):
            if match[1] == number[1]:
                return match.start()
    return None


def _extract_numbered_book(pdf_path: Path, reader: PdfReader) -> BookMetadata | None:
    """Use printed headings when the PDF contains a clear sequence of sections."""
    headings: list[tuple[int, int, str, str]] = []
    numbers_in_toc: set[int] = set()
    for file_page, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        matches = list(_NUMBERED_HEADING.finditer(text))
        if not matches:
            continue

        for match in matches:
            number, first_line = match.groups()
            first_line = first_line.strip()
            if re.search(r"(?:\.{2,}|…|⋯)", first_line):
                if re.search(r"\d+\s*$", first_line):
                    numbers_in_toc.add(int(number))
                continue
            if not first_line.isupper() or not first_line[0].isalpha():
                continue
            if int(number) != len(headings) + 1:
                continue

            title_lines = [first_line]
            for line in text[match.end():].splitlines()[1:4]:
                line = line.strip()
                if len(line) < 2 or not line.isupper() or line.startswith("§"):
                    break
                title_lines.append(line)

            page_label = re.search(r"(?m)^\s*(\d+)\s*$", "\n".join(text.splitlines()[:5]))
            printed_page = int(page_label[1]) if page_label else file_page + 1
            title = " ".join(" ".join(title_lines).split())
            headings.append((file_page, printed_page, number, f"§ {number}. {title}"))

    if len(headings) < 2:
        return None
    if numbers_in_toc - {int(entry[2]) for entry in headings}:
        return None
    if any(left[0] == right[0] for left, right in pairwise(headings)):
        # The current metadata format requires distinct section page numbers.
        return None

    printed_pages = [entry[1] for entry in headings]
    if any(left >= right for left, right in pairwise(printed_pages)):
        printed_pages = [entry[0] + 1 for entry in headings]
    return BookMetadata(
        pdf_path=pdf_path,
        created_at=datetime.datetime.now(datetime.UTC).date(),
        paragraphs={
            number: BookParagraph(
                title=title,
                book_page_start=printed_pages[index],
                file_start=file_page,
                file_end=headings[index + 1][0] if index + 1 < len(headings) else len(reader.pages) - 1,
            )
            for index, (file_page, _, number, title) in enumerate(headings)
        },
    )


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


def _find_title_page(reader: PdfReader, title: str) -> int:
    """Return the first matching page for backward compatibility."""
    matches = _find_title_pages(reader, title)
    if not matches:
        raise ValueError(f"Could not find paragraph title in PDF: {title}")
    return matches[0]


def _find_page_offset(
    reader: PdfReader,
    entries: list[tuple[str, TableOfContentsEntry]],
) -> int:
    anchors = [
        entry for entry in entries[:20] if len(_normalize_text(entry[1].title)) >= 20
    ][:10]
    logger.debug(
        "Finding PDF page offset: toc_entries=%s, anchors=%s",
        len(entries),
        [
            f"{number}: printed_page={entry.book_page_start}, title={entry.title!r}"
            for number, entry in anchors
        ],
    )
    if not anchors:
        logger.warning(
            "Cannot calculate PDF page offset: no sufficiently specific anchors"
        )
        raise ValueError(
            "Could not find sufficiently specific TOC entries for page offset"
        )

    matches_by_entry = [
        (entry, _find_title_pages(reader, entry[1].title)) for entry in anchors
    ]
    for entry, page_numbers in matches_by_entry:
        logger.debug(
            "TOC anchor match: id=%s, printed_page=%s, matching_pdf_pages=%s, title=%r",
            entry[0],
            entry[1].book_page_start,
            [page_number + 1 for page_number in page_numbers],
            entry[1].title,
        )
    matches_by_entry = [item for item in matches_by_entry if item[1]]
    if not matches_by_entry:
        logger.warning(
            "Cannot calculate PDF page offset: none of the TOC anchors matched"
        )
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
    logger.debug(
        "PDF page-offset candidates: scores=%s, selected_offset=%s, "
        "support=%s/%s, required_support=%s",
        sorted(scored_offsets, reverse=True),
        offset,
        support,
        len(matches_by_entry),
        required_support,
    )
    if support < required_support:
        logger.warning(
            "Inconsistent PDF page offset: best candidate has support %s/%s; need %s",
            support,
            len(matches_by_entry),
            required_support,
        )
        raise ValueError(
            "Could not determine a consistent page offset: "
            f"{support}/{len(matches_by_entry)} anchors agree"
        )

    logger.info(
        "Resolved PDF page offset: offset=%s (PDF page index = printed page + offset)",
        offset,
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


def _read_pdf_structure(pdf_path: Path) -> BookMetadata | str:
    try:
        reader = PdfReader(pdf_path)
        if not reader.pages:
            raise InvalidTOC(f"PDF contains no pages: {pdf_path}")
        return _extract_numbered_book(pdf_path, reader) or _extract_toc_text(reader)
    except (PyPdfError, OSError) as exc:
        raise InvalidTOC(f"Could not read PDF: {pdf_path}") from exc


def _build_book_metadata(pdf_path: Path, toc: TableOfContents) -> BookMetadata:
    reader = PdfReader(pdf_path)
    if not reader.pages:
        raise ValueError(f"PDF contains no pages: {pdf_path}")

    ordered_paragraphs = sorted(
        toc.paragraphs.items(), key=lambda item: item[1].book_page_start
    )
    logger.debug(
        "Building metadata for %s: pdf_pages=%s, toc_entries=%s",
        pdf_path,
        len(reader.pages),
        len(ordered_paragraphs),
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
        logger.debug(
            "Mapped TOC entry id=%s title=%r printed_page=%s to PDF pages %s-%s",
            number,
            entry.title,
            entry.book_page_start,
            file_start + 1,
            min(file_end, len(reader.pages) - 1) + 1,
        )

    logger.info("Built book metadata: paragraphs=%s, pdf=%s", len(paragraphs), pdf_path)
    return BookMetadata(
        title="",
        pdf_path=pdf_path,
        created_at=datetime.datetime.now(datetime.UTC).date(),
        paragraphs=paragraphs,
    )


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
    logger.debug(
        "TOC model response received: model=%s, choices=%s, usage=%s",
        settings.parsing_model,
        len(response.choices),
        getattr(response, "usage", None),
    )
    if not response.choices:
        raise InvalidTOC("LLM returned no choices while extracting table of contents")

    content = response.choices[0].message.content
    if not content:
        raise InvalidTOC("LLM returned an empty table of contents")

    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise InvalidTOC("LLM returned an invalid table of contents format")

    try:
        toc = TableOfContents.model_validate(_normalize_toc_payload(payload))
    except ValidationError as exc:
        logger.warning("Model TOC failed schema validation: %s", exc)
        raise InvalidTOC from exc

    logger.info("Model returned %s TOC entries", len(toc.paragraphs))
    for paragraph_id, entry in sorted(
        toc.paragraphs.items(), key=lambda item: item[1].book_page_start
    )[:20]:
        logger.debug(
            "Model TOC entry: id=%s, printed_page=%s, title=%r",
            paragraph_id,
            entry.book_page_start,
            entry.title,
        )
    if len(toc.paragraphs) > 20:
        logger.debug(
            "Omitting %s additional TOC entries from debug log",
            len(toc.paragraphs) - 20,
        )
    return toc


async def parse_book(
    path: str | Path, client: AsyncOpenAI | None = None, attempts: int = 3
) -> BookMetadata:
    pdf_path = Path(path)
    if attempts <= 0:
        raise ValueError("attempts must be greater than zero")

    structure = await asyncio.to_thread(_read_pdf_structure, pdf_path)
    if isinstance(structure, BookMetadata):
        return structure
    if client is None:
        try:
            async with get_async_openai_client() as owned_client:
                return await _parse_with_model(pdf_path, structure, owned_client, attempts)
        except ValueError as exc:
            raise InvalidTOC("RouterAI is not configured for book parsing") from exc
    return await _parse_with_model(pdf_path, structure, client, attempts)


async def _parse_with_model(
    pdf_path: Path, toc_text: str, client: AsyncOpenAI, attempts: int
) -> BookMetadata:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            logger.info(
                "Parsing book TOC: attempt=%s/%s, pdf=%s, input_chars=%s",
                attempt,
                attempts,
                pdf_path,
                len(toc_text),
            )
            toc = await _parse_table_of_contents(toc_text, client)

            if not toc.paragraphs:
                raise InvalidTOC()

            return await asyncio.to_thread(_build_book_metadata, pdf_path, toc)
        except APIError as exc:
            logger.exception(
                "LLM API error while parsing TOC: attempt=%s/%s, pdf=%s",
                attempt,
                attempts,
                pdf_path,
            )
            raise InvalidTOC(f"RouterAI failed while parsing TOC: {pdf_path}") from exc
        except (InvalidTOC, PyPdfError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "Failed to parse TOC: attempt=%s/%s, pdf=%s, error_type=%s, error=%s",
                attempt,
                attempts,
                pdf_path,
                type(exc).__name__,
                exc,
                exc_info=True,
            )

    logger.error("failed to parse TOC after %s attempts: %s", attempts, pdf_path)
    raise InvalidTOC(f"Failed to parse TOC: {pdf_path}") from last_error
