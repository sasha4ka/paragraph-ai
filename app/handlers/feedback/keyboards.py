from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder


def cancel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="Отмена", payload="cancel"))
    return builder.as_markup()


def leave_name_default_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(
        CallbackButton(text="Отправить без имени", payload="leave_name_default")
    )
    return builder.as_markup()


def go_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="Назад", payload="go_back"))
    return builder.as_markup()
