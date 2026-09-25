import json
import logging
import os
from pathlib import Path
from typing import Literal, Self, cast

from pypdf import PdfReader

from app.logics.parser import parse_book
from app.models import BookMetadata

logger = logging.getLogger("Book Repository")
logger.setLevel(logging.INFO)


class Book:
    metadata: BookMetadata

    def __init__(self, metadata: BookMetadata) -> None:
        self.metadata = metadata

    async def get_text(self, section_ids: list[str]) -> str:
        pages: set[int] = set()
        for section_id in section_ids:
            section = self.metadata.paragraphs.get(section_id)
            if section is None:
                continue
            pages.update(range(section.file_start, section.file_end + 1))

        reader = PdfReader(self.metadata.pdf_path)
        return "".join(
            reader.pages[page_number].extract_text() or ""
            for page_number in sorted(pages)
        )


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
        files = os.listdir(self.metadata_dir)
        if not files:
            logger.info("Library is empty")
        for name in files:
            metadata_path = self.metadata_dir / name
            self.get_book(metadata_path)
            logger.info(f"loaded {metadata_path}")

    def get_book(self, book_path: str | Path) -> Book:
        book_path = Path(book_path)
        metadata_path = (
            book_path
            if book_path.suffix == ".json" and book_path.parent == self.metadata_dir
            else self.metadata_dir / f"{book_path.stem}.json"
        )

        with metadata_path.open(encoding="utf-8") as metadata_file:
            metadata = BookMetadata.model_validate(json.load(metadata_file))

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
        metadata_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

        book_name = metadata.title or "unknown book"
        self._books[metadata_path] = (book_name, metadata_path, "parsed")

        return Book(metadata)

    async def parse_then_add_book(
        self, path: Path | str, title: str = "unknown book"
    ) -> Book:
        book_path = Path(path)
        metadata_path = self.metadata_dir / f"{book_path.stem}.json"
        self._books[metadata_path] = (title, metadata_path, "processing")
        metadata = await parse_book(book_path)
        metadata.title = title
        return self.add_book(metadata)

    def delete_book(self, path: Path | str):
        metadata_path = Path(path)

        if metadata_path not in self._books:
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
