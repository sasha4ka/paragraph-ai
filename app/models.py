import datetime
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class BookEntry(BaseModel):
    title: str
    book_page_start: int = Field(ge=1)
    file_start: int = Field(default=0, ge=0)
    file_end: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_file_range(self) -> "BookEntry":
        if self.file_end < self.file_start:
            raise ValueError("file_end must be greater than or equal to file_start")
        return self


class BookParagraph(BookEntry):
    pass


class BookMetadata(BaseModel):
    title: str | None = None
    pdf_path: Path
    created_at: datetime.date
    paragraphs: dict[str, BookParagraph] = Field(default_factory=dict)

    @staticmethod
    def _validate_unique_starts(entries: dict[str, BookEntry], category: str) -> None:
        starts = [entry.book_page_start for entry in entries.values()]
        duplicates = sorted({start for start in starts if starts.count(start) > 1})
        if duplicates:
            raise ValueError(
                f"Duplicate book_page_start values in {category}: {duplicates}"
            )

    @model_validator(mode="after")
    def validate_unique_starts(self) -> "BookMetadata":
        self._validate_unique_starts(self.paragraphs, "paragraphs")
        return self
