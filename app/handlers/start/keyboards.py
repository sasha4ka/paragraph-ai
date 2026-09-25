from maxapi.types import MessageButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder


def start_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(MessageButton(text="Мои книги"))
    builder.add(MessageButton(text="Конспект"))
    return builder.as_markup()
