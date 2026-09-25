from maxapi import Router
from maxapi.types import BotStarted, Command, MessageCreated

from app.bot import get_bot
from app.handlers.start.keyboards import start_keyboard

router = Router()


@router.message_created(Command("start"))
async def start_command(event: MessageCreated | BotStarted):
    await get_bot().send_message(
        chat_id=event.chat.chat_id,
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
