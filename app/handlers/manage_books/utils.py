import os
from pathlib import Path

import aiohttp

from app.exc import DownloadError, InvalidPath

cache_dir = Path("cache/").absolute()


async def download_file(filename: str, url: str) -> Path:
    if not cache_dir.exists():
        os.mkdir(cache_dir)

    path = Path.joinpath(cache_dir, filename).resolve()
    if path.parent != cache_dir.resolve():
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


def list_books() -> list[str]:
    filenames = sorted(os.listdir(cache_dir))
    return ["".join(name.split(".")[:-1]) for name in filenames]


def delete_book(path: str) -> bool:
    _path = Path(path).resolve()
    if _path.parent != cache_dir.resolve() or not _path.is_file():
        return False

    os.remove(_path)
    return True
