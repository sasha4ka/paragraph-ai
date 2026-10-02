import logging

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import Command, MessageCallback, MessageCreated

from app.bot import get_bot
from app.handlers.feedback.keyboards import (
    cancel_keyboard,
    go_back_keyboard,
    leave_name_default_keyboard,
)
from app.handlers.start.router import start_menu
from app.logics.feedback import add_feedback
from app.states import Feedback

router = Router()
logger = logging.getLogger("handlers.feedback")


async def open_feedback_form(message: MessageCreated, context: MemoryContext) -> None:
    reply = await message.message.answer(
        "Есть новые идеи по улучшению Paragraph AI?\nПожалуйста, поделитесь ими с нами! Мы ценим ваши отзывы и всегда ищем способы сделать наш продукт лучше\n\nКак бы вы хотели изменить Paragraph AI?",
        attachments=[cancel_keyboard()],
    )
    await context.set_state(Feedback.enter_feedback)
    await context.update_data(
        message_id=reply.message.body.mid, chat_id=message.chat.chat_id
    )


router.message_created.register(open_feedback_form, F.message.body.text == "Отзыв")
router.message_created.register(open_feedback_form, Command("feedback"))


@router.message_callback(F.callback.payload == "cancel", Feedback.enter_feedback)
async def cancel_feedback(message: MessageCreated, context: MemoryContext) -> None:
    data = await context.get_data()
    await start_menu(message_id=data["message_id"], context=context)


@router.message_created(Feedback.enter_feedback)
async def enter_feedback(message: MessageCreated, context: MemoryContext) -> None:
    feedback = message.message.body.text
    if not feedback:
        return
    reply = await message.message.answer(
        "Теперь вы можете указать ваше имя (необязательно), чтобы мы могли связаться с вами",
        attachments=[leave_name_default_keyboard()],
    )
    await context.set_state(Feedback.enter_a_name)
    await context.update_data(feedback=feedback, message_id=reply.message.body.mid)


@router.message_callback(
    Feedback.enter_a_name, F.callback.payload == "leave_name_default"
)
async def leave_name_default(event: MessageCallback, context: MemoryContext) -> None:
    await context.update_data(name=None)
    data = await context.get_data()
    await handle_feedback(
        message_id=data["message_id"],
        context=context,
        user_id=event.from_user.user_id,
    )


@router.message_created(Feedback.enter_a_name)
async def enter_a_name(message: MessageCreated, context: MemoryContext) -> None:
    name = message.message.body.text
    if not name:
        return
    await context.update_data(name=name)
    await handle_feedback(
        chat_id=message.chat.chat_id,
        context=context,
        user_id=message.message.sender.user_id,
    )


async def handle_feedback(
    *,
    chat_id: int | None = None,
    message_id: str | None = None,
    context: MemoryContext,
    user_id: int,
) -> None:
    data = await context.get_data()
    feedback = data.get("feedback", "")
    name = data.get("name")
    await add_feedback(feedback, name, user_id)

    text = f"Спасибо за ваш отзыв, {name or 'Пользователь'}! Мы ценим ваше мнение и обязательно учтем его в будущих обновлениях Paragraph AI."

    if chat_id is None and message_id is not None:
        reply = await get_bot().edit_message(
            message_id=message_id,
            text=text,
            attachments=[go_back_keyboard()],
        )
    elif chat_id is not None and message_id is None:
        reply = await get_bot().send_message(
            chat_id=chat_id,
            text=text,
            attachments=[go_back_keyboard()],
        )
    else:
        raise ValueError("Either chat_id or message_id must be provided, but not both.")

    await context.set_state(Feedback.thanks)
    await context.update_data(message_id=message_id or reply.message.body.mid)
    logger.info(
        f"Feedback handled for user {user_id=} with name {name} and feedback: {feedback}"
    )


@router.message_callback(Feedback.thanks, F.callback.payload == "go_back")
async def go_to_main_menu(event: MessageCallback, context: MemoryContext):
    data = await context.get_data()
    await start_menu(message_id=data["message_id"], context=context)
