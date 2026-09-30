import logging

from maxapi import Router
from maxapi.types import BotStarted, BotStopped, Command, MessageCreated

from app.bot import get_bot
from app.handlers.start.keyboards import start_keyboard

router = Router()
logger = logging.getLogger("start_router")


@router.message_created(Command("start"))
async def start_command(event: MessageCreated | BotStarted):
    uid = event.from_user.user_id
    chat_id = event.chat.chat_id
    logger.info(f"bot started {uid=uid}")
    await get_bot().send_message(
        chat_id=chat_id,
        text="""\
👋 Привет! Я твой ИИ-помощник в учёбе.

Загружай учебники, и я:
📖 Выделю главное из любого параграфа
🧠 Задам вопросы для проверки знаний
🎯 Быстро подготовлю тебя к контрольной

Жми «Мои книги» ниже, чтобы начать! 👇
""",
        attachments=[start_keyboard()],
    )


router.bot_started.register(start_command)


@router.bot_stopped
async def stop_bot(event: BotStopped):
    uid = event.from_user.user_id
    logger.info(f"bot stopped {uid=}")
