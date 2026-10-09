import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI
from maxapi import Bot, Dispatcher
from maxapi.webhook.fastapi import FastAPIMaxWebhook

from app.books import BooksRepository
from app.bot import init_bot
from app.handlers.feedback import router as feedback_router
from app.handlers.manage_books import router as manage_books_router
from app.handlers.start import router as start_router
from app.handlers.summarize import router as summarize_router
from app.logging_setup import setup
from app.settings import settings

dp = Dispatcher()
bot = Bot(settings.api_token)
WEBHOOK_PATH = "/webhook"

setup()


dp.include_routers(manage_books_router, start_router, summarize_router, feedback_router)
init_bot(bot)

webhook = FastAPIMaxWebhook(dp, bot, secret=settings.webhook_secret)


@asynccontextmanager
async def lifespan(application: FastAPI):
    if not settings.webhook_url:
        raise RuntimeError(
            "WEBHOOK_URL must be set when DEBUG is false; "
            "it must include the /webhook path."
        )
    parsed_webhook_url = urlsplit(settings.webhook_url)
    if (
        parsed_webhook_url.scheme != "https"
        or not parsed_webhook_url.netloc
        or parsed_webhook_url.path != WEBHOOK_PATH
    ):
        raise RuntimeError(
            f"WEBHOOK_URL must be an absolute HTTPS URL ending in {WEBHOOK_PATH}."
        )

    BooksRepository().load_library()
    try:
        async with webhook.lifespan(application):
            await bot.subscribe_webhook(
                settings.webhook_url,
                secret=settings.webhook_secret,
            )
            yield
    finally:
        await bot.close_session()


app = FastAPI(lifespan=lifespan)
webhook.setup(app, path=WEBHOOK_PATH)


async def run_polling() -> None:
    BooksRepository().load_library()
    try:
        # MAX ignores polling while webhook subscriptions exist.
        await bot.delete_webhook()
        await dp.start_polling(bot)
    finally:
        await bot.close_session()


def main() -> None:
    if settings.debug:
        asyncio.run(run_polling())
        return

    uvicorn.run("app.app:app", host="0.0.0.0", port=8000)
