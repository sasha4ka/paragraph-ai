from maxapi import Bot, Dispatcher

from app.bot import init_bot
from app.handlers.manage_books import router as manage_books_router
from app.handlers.start import router as start_router
from app.settings import settings

dp = Dispatcher()
bot = Bot(settings.api_token)


async def main():
    dp.include_routers(manage_books_router, start_router)
    init_bot(bot)

    await dp.start_polling(bot)
