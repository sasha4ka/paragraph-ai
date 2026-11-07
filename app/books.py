import asyncio
import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal, Self, cast

from pypdf import PdfReader

from app.exc import InvalidTOC
from app.logics.parser import find_heading_start, parse_book
from app.models import BookMetadata

logger = logging.getLogger("Book Repository")
logger.setLevel(logging.INFO)


class Book:
    metadata: BookMetadata

    def __init__(self, metadata: BookMetadata) -> None:
        self.metadata = metadata

    async def get_text(self, section_ids: list[str]) -> str:
        return await asyncio.to_thread(self._get_text, set(section_ids))

    def _get_text(self, section_ids: set[str]) -> str:
        reader = PdfReader(self.metadata.pdf_path)
        sections = sorted(
            self.metadata.paragraphs.items(),
            key=lambda item: (item[1].file_start, item[1].book_page_start),
        )
        page_texts: dict[int, str] = {}
        excerpts = []
        for index, (section_id, section) in enumerate(sections):
            if section_id not in section_ids:
                continue
            following = sections[index + 1][1] if index + 1 < len(sections) else None
            for page_index in range(section.file_start, section.file_end + 1):
                if page_index not in page_texts:
                    page_texts[page_index] = reader.pages[page_index].extract_text() or ""
                text = page_texts[page_index]
                start = 0
                if page_index == section.file_start:
                    start = find_heading_start(text, section.title) or 0
                end = None
                if following and page_index == following.file_start:
                    end = find_heading_start(text, following.title)
                excerpt = text[start:end].strip()
                if excerpt:
                    excerpts.append(excerpt)
        return "\n".join(excerpts)


type BookObject = tuple[str, Path, Literal["parsed", "processing"]]


class BooksRepository:
    _instance: "BooksRepository | None" = None
    _books: dict[Path, BookObject]

    def __new__(cls, books_dir: str | Path = "books") -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize(books_dir)
        return cast(Self, cls._instance)

    def __init__(self, books_dir: str | Path = "books") -> None:
        pass

    def _initialize(self, books_dir: str | Path) -> None:
        self.books_dir = Path(books_dir)
        self.metadata_dir = self.books_dir / "metadata"
        self._books = {}

    def load_library(self):
        logger.info("Loading library:")
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(self.metadata_dir.glob("*.json"))
        if not files:
            logger.info("Library is empty")
        for metadata_path in files:
            try:
                self.get_book(metadata_path)
            except (OSError, ValueError):
                logger.warning("Could not load %s", metadata_path, exc_info=True)
            else:
                logger.info("Loaded %s", metadata_path)

    def get_book(self, book_path: str | Path) -> Book:
        book_path = Path(book_path)
        metadata_path = (
            book_path
            if book_path.suffix == ".json" and book_path.parent == self.metadata_dir
            else self.metadata_dir / f"{book_path.stem}.json"
        )

        with metadata_path.open(encoding="utf-8") as metadata_file:
            metadata = BookMetadata.model_validate(json.load(metadata_file))
        if not metadata.pdf_path.is_file():
            relocated = self.books_dir / metadata.pdf_path.name
            if not relocated.is_file():
                raise FileNotFoundError(f"PDF not found: {metadata.pdf_path}")
            metadata.pdf_path = relocated

        self._books[metadata_path] = (
            metadata.title or "unknown book",
            metadata_path,
            "parsed",
        )

        return Book(metadata)

    def add_book(self, metadata: BookMetadata) -> Book:
        book_path = self._resolve_book_path(metadata.pdf_path)
        if not book_path.is_file():
            raise FileNotFoundError(f"Book file does not exist: {book_path}")

        metadata_path = self.metadata_dir / f"{book_path.stem}.json"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.metadata_dir, delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(metadata.model_dump_json(indent=2))
            temporary_path.replace(metadata_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        book_name = metadata.title or "unknown book"
        self._books[metadata_path] = (book_name, metadata_path, "parsed")

        return Book(metadata)

    async def parse_then_add_book(
        self, path: Path | str, title: str = "unknown book"
    ) -> Book:
        book_path = Path(path)
        metadata_path = self.metadata_dir / f"{book_path.stem}.json"
        if metadata_path in self._books or metadata_path.exists():
            raise InvalidTOC(f"Book already exists: {book_path.name}")
        self._books[metadata_path] = (title, metadata_path, "processing")

        try:
            metadata = await parse_book(book_path)
            metadata.title = title
            return self.add_book(metadata)
        except (InvalidTOC, OSError, asyncio.CancelledError):
            self._books.pop(metadata_path, None)
            if book_path.resolve().parent == self.books_dir.resolve():
                book_path.unlink(missing_ok=True)
            raise

    def delete_book(self, path: Path | str):
        metadata_path = Path(path)

        stored = self._books.get(metadata_path)
        if stored is None or stored[2] == "processing":
            return False

        book = self.get_book(metadata_path)

        os.remove(book.metadata.pdf_path)
        os.remove(metadata_path)
        self._books.pop(metadata_path)

        return True

    def list_books(self) -> list[BookObject]:
        return list(self._books.values())

    def _resolve_book_path(self, book_path: Path) -> Path:
        if book_path.is_absolute():
            return book_path

        if book_path.is_file():
            return book_path

        return self.books_dir / book_path
