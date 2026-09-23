from maxapi.types import MessageButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder


def start_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(MessageButton(text="Мои книги"))
    return builder.as_markup()
