import logging

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import (
    BotStarted,
    BotStopped,
    Command,
    MessageCreated,
)

from app.bot import get_bot
from app.handlers.start.keyboards import start_keyboard

router = Router()
logger = logging.getLogger("start_router")


async def start_menu(
    *,
    event: MessageCreated | BotStarted | None = None,
    message_id: str | None = None,
    context: MemoryContext | None = None,
):
    text = """\
    👋 Привет! Я твой ИИ-помощник в учёбе.

    Загружай учебники, и я:
    📖 Выделю главное из любого параграфа
    🧠 Задам вопросы для проверки знаний
    🎯 Быстро подготовлю тебя к контрольной

    Жми «Мои книги» ниже, чтобы начать! 👇
    """
    if isinstance(event, MessageCreated | BotStarted):
        await get_bot().send_message(
            chat_id=event.chat.chat_id,
            text=text,
            attachments=[start_keyboard()],
        )
        logger.info(f"start menu sent {event.from_user.user_id=}")
    elif event is None:
        if message_id is None:
            raise ValueError("message_id is required for MessageCallback events")

        if context is not None:
            await context.clear()

        await get_bot().edit_message(
            message_id=message_id,
            text=text,
            attachments=[start_keyboard()],
        )
        logger.info(f"start menu sent via edit_message {message_id=}")


async def handle_start(event: BotStarted | MessageCreated, context: MemoryContext):
    await start_menu(event=event, context=context)


router.bot_started.register(handle_start)
router.message_created.register(handle_start, Command("start"))
router.message_created.register(handle_start, F.message.body.text == "Главное меню")


@router.bot_stopped
async def stop_bot(event: BotStopped):
    uid = event.from_user.user_id
    logger.info(f"bot stopped {uid=}")
