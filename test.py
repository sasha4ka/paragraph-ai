import asyncio

from app.logics.parser import parse_book


async def main():
    print(
        await parse_book(
            "/home/sasha/Projects/paragraph-ai/books/История Всеобщая 10 класс В.Р. Мединский 2023 г..pdf"
        )
    )


asyncio.run(main())
