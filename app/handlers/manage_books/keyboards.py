from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder


def menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="Добавить", payload="menu:add"))
    builder.add(CallbackButton(text="Удалить", payload="menu:delete"))
    return builder.as_markup()


def upload_book_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="Отмена", payload="cancel"))
    return builder.as_markup()
