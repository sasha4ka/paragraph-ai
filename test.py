import asyncio

from app.logics.parser import parse_book


async def main():
    print(await parse_book("books/Геометрия 10 класс.pdf"))


asyncio.run(main())
