import argparse
import asyncio

from app.logics.parser import parse_book

if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Проверить извлечение оглавления из PDF")
    cli.add_argument("pdf", help="Путь к PDF учебника")
    metadata = asyncio.run(parse_book(cli.parse_args().pdf))
    print(metadata.model_dump_json(indent=2))
