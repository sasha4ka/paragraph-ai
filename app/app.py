from maxapi import Bot, Dispatcher

from app.books import BooksRepository
from app.bot import init_bot
from app.handlers.manage_books import router as manage_books_router
from app.handlers.start import router as start_router
from app.handlers.summarize import router as summarize_router
from app.logging_setup import setup
from app.settings import settings

dp = Dispatcher()
bot = Bot(settings.api_token)

setup()


async def main():
    BooksRepository().load_library()
    dp.include_routers(manage_books_router, start_router, summarize_router)
    init_bot(bot)

    await dp.start_polling(bot)
