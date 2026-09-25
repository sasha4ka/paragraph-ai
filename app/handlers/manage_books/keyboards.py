from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder


def menu_keyboard(only_add: bool = False):
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="Добавить", payload="menu:add"))
    if not only_add:
        builder.add(CallbackButton(text="Удалить", payload="menu:delete"))
    return builder.as_markup()


def cancel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="Отмена", payload="cancel"))
    return builder.as_markup()
