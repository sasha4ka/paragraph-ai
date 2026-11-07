import os
from pathlib import Path

import aiohttp

from app.books import BookObject
from app.exc import DownloadError, InvalidPath
from app.settings import settings

books_dir = Path("books/").absolute()


async def download_file(filename: str, url: str) -> Path:
    if not books_dir.exists():
        books_dir.mkdir(parents=True, exist_ok=True)

    path = Path.joinpath(books_dir, filename).resolve()
    if path.parent != books_dir.resolve():
        raise InvalidPath()

    size = 0
    created = False
    completed = False
    try:
        async with (
            aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session,
            session.get(url) as response,
        ):
            response.raise_for_status()
            with path.open("xb") as file:
                created = True
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > settings.max_file_size_mb * 1_000_000:
                        raise DownloadError("Attachment exceeds the file size limit")
                    file.write(chunk)
        completed = True
    except (aiohttp.ClientError, TimeoutError, OSError) as exc:
        raise DownloadError("Could not save PDF attachment") from exc
    finally:
        if created and not completed:
            path.unlink(missing_ok=True)

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
