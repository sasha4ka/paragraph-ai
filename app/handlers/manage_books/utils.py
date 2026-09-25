import os
from pathlib import Path

import aiohttp

from app.books import BookObject
from app.exc import DownloadError, InvalidPath

books_dir = Path("books/").absolute()


async def download_file(filename: str, url: str) -> Path:
    if not books_dir.exists():
        books_dir.mkdir(parents=True, exist_ok=True)

    path = Path.joinpath(books_dir, filename).resolve()
    if path.parent != books_dir.resolve():
        raise InvalidPath()

    async with (
        aiohttp.ClientSession() as session,
        session.get(url) as response,
    ):
        if response.status == 200:
            with open(path, "wb") as f:  # noqa
                while True:
                    chunk = await response.content.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        else:
            raise DownloadError(f"Failed to download {url}")

    return path


def compile_books_list(books: list[BookObject]) -> list[str]:
    _processed_books: list[str] = []
    for i, book in enumerate(books):
        if book[2] == "processing":
            _processed_books.append(f"{i + 1} - {book[0]} - processing⏳")
        else:
            _processed_books.append(f"{i + 1} - {book[0]}")

    return _processed_books


def delete_book(path: str) -> bool:
    _path = Path(path).resolve()
    if _path.parent != books_dir.resolve() or not _path.is_file():
        raise InvalidPath()

    os.remove(_path)
    return True
