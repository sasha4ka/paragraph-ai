from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import (
    CallbackButton,
    MessageCallback,
    MessageCreated,
)
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.handlers.start.router import start_menu
from app.states import Navigation

router = Router()


def navigation_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="🏠 Главное меню", payload="navigation:main_menu"))
    builder.add(
        CallbackButton(
            text="💬 Устный доклад (текст)", payload="navigation:oral_report"
        )
    )
    builder.add(
        CallbackButton(
            text="🖼️ Устный доклад (карточки)", payload="navigation:oral_report_cards"
        )
    )
    builder.add(
        CallbackButton(text="📚 Проверка знаний", payload="navigation:knowledge_check")
    )
    builder.adjust(1)
    return builder.as_markup()


@router.message_created(F.message.body.text == "Конспект")
async def handle_navigation(event: MessageCreated, context: MemoryContext):
    await context.set_state(Navigation.navigation)
    await event.message.answer(
        text="Доступно три режима работы с материалом. Выберите один из них:",
        attachments=[navigation_keyboard()],
    )


async def go_to_navigation(
    event: MessageCallback, context: MemoryContext, new_message: bool = False
):
    await context.set_state(Navigation.navigation)
    if new_message:
        await event.message.answer(
            text="Доступно три режима работы с материалом. Выберите один из них:",
            attachments=[navigation_keyboard()],
        )
    else:
        await event.message.edit(
            text="Доступно три режима работы с материалом. Выберите один из них:",
            attachments=[navigation_keyboard()],
        )


@router.message_callback(
    F.callback.payload == "navigation:main_menu", Navigation.navigation
)
async def handle_main_menu(event: MessageCallback, context: MemoryContext):
    await start_menu(message_id=event.message.body.mid, context=context)


# ------------------------------------
#  Placeholders for future workflows
# ------------------------------------


@router.message_callback(
    F.callback.payload == "navigation:knowledge_check", Navigation.navigation
)
async def handle_knowledge_check(event: MessageCallback, context: MemoryContext):
    await event.answer(notification="Функция в разработке. Скоро будет доступна!")
