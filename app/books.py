import json
from pathlib import Path
from typing import Self, cast

from pypdf import PdfReader

from app.models import BookMetadata


class Book:
    metadata: BookMetadata

    def __init__(self, metadata: BookMetadata) -> None:
        self.metadata = metadata

    async def get_text(self, section_ids: list[str]) -> str:
        pages: set[int] = set()
        for section_id in section_ids:
            section = next(
                (item for item in self.metadata.sections if item.id == section_id),
                None,
            )
            if section is None:
                continue
            pages.update(range(section.file_start, section.file_end + 1))

        reader = PdfReader(self.metadata.pdf_path)
        return "".join(
            reader.pages[page_number].extract_text() or ""
            for page_number in sorted(pages)
        )


class BooksRepository:
    _instance: "BooksRepository | None" = None

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

    def get_book(self, book_path: str | Path) -> Book:
        book_path = Path(book_path)
        metadata_path = (
            book_path
            if book_path.suffix == ".json" and book_path.parent == self.metadata_dir
            else self.metadata_dir / f"{book_path.stem}.json"
        )

        with metadata_path.open(encoding="utf-8") as metadata_file:
            metadata = BookMetadata.model_validate(json.load(metadata_file))

        return Book(metadata)

    def add_book(self, metadata: BookMetadata) -> Book:
        book_path = self._resolve_book_path(metadata.pdf_path)
        if not book_path.is_file():
            raise FileNotFoundError(f"Book file does not exist: {book_path}")

        metadata_path = self.metadata_dir / f"{book_path.stem}.json"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

        return Book(metadata)

    def _resolve_book_path(self, book_path: Path) -> Path:
        if book_path.is_absolute():
            return book_path

        if book_path.is_file():
            return book_path

        return self.books_dir / book_path
