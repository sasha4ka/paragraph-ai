import asyncio
import logging

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.methods.types.sended_message import SendedMessage
from maxapi.types import CallbackButton, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.books import BooksRepository
from app.bot import get_bot
from app.handlers.manage_books.utils import compile_books_list
from app.logics.select_paragraph import (
    ParagraphSelectionError,
)
from app.logics.select_paragraph import (
    select_paragraphs as resolve_paragraphs,
)
from app.logics.summary_generator import AbstractGenerationError, ParagraphAbstractor
from app.states import Summarize

router = Router()

logger = logging.getLogger("summarize router")


def exit_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="Выйти", payload="Summarize.chat_mode:exit"))
    return builder.as_markup()


def cancel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="Отмена", payload="cancel"))
    return builder.as_markup()


@router.message_created(F.message.body.text == "Конспект")
async def start_summarize(event: MessageCreated, context: MemoryContext):
    await context.set_state(Summarize.select_book)

    books = BooksRepository().list_books()
    await context.update_data(books=books)
    if not books:
        await event.message.answer(text="У вас пока нет загруженных учебников.")
        return

    text = f"Выберите книгу:\n{'\n'.join(compile_books_list(books))}"

    await event.message.answer(text=text, attachments=[cancel_keyboard()])


@router.message_created(F.message.body.text, Summarize.select_book)
async def select_book(event: MessageCreated, context: MemoryContext):
    data = await context.get_data()
    books = data.get("books", [])
    body = event.message.body
    if body is None or body.text is None:
        return
    try:
        index = int(body.text) - 1
    except ValueError:
        await event.message.answer(text="Введите номер книги.")
        return

    if index < 0 or index >= len(books) or books[index][2] == "processing":
        await event.message.answer(text="Такой книги нет или она ещё обрабатывается.")
        return

    book = BooksRepository().get_book(books[index][1])
    paragraphs = list(book.metadata.paragraphs.items())
    await context.update_data(book_path=books[index][1], paragraphs=paragraphs)
    await context.set_state(Summarize.select_paragraphs)

    await event.message.answer(
        text=(
            "Введите название одного или нескольких параграфов. "
            "Если выбираете несколько, разделите названия запятыми."
        ),
        attachments=[cancel_keyboard()],
    )


@router.message_created(F.message.body.text, Summarize.select_paragraphs)
async def select_paragraphs(event: MessageCreated, context: MemoryContext):
    data = await context.get_data()
    paragraphs = dict(data.get("paragraphs", []))
    body = event.message.body
    if body is None or body.text is None:
        return
    paragraph_titles = {
        paragraph_id: paragraph.title for paragraph_id, paragraph in paragraphs.items()
    }
    try:
        selected_ids = await resolve_paragraphs(body.text, paragraph_titles)
    except ParagraphSelectionError as exc:
        await event.message.answer(text=str(exc))
        return

    await context.set_state(Summarize.chat_mode)
    processing_message = await event.message.answer(text="Готовлю конспект ⏳")
    book = BooksRepository().get_book(data["book_path"])
    paragraph_text = await book.get_text(selected_ids)

    try:
        summary_blocks = await ParagraphAbstractor().summarize_async(paragraph_text)
    except AbstractGenerationError:
        await _delete_processing_message(processing_message)
        await context.set_state(Summarize.select_paragraphs)
        await event.message.answer(text="Не удалось подготовить конспект.")
        user_id = event.message.sender.user_id
        logger.exception(f"Error generating summary {user_id=}")
        return

    if len(summary_blocks) > 10:
        await event.message.answer(text="Не удалось подготовить конспект.")
        user_id = event.message.sender.user_id
        logger.error(f"Too big summary. can not send to max api {user_id=}")
        return

    await _delete_processing_message(processing_message)
    for block in summary_blocks:
        block = _truncate_summary(block)
        await event.message.answer(text=block)
        await asyncio.sleep(0.5)


def _truncate_summary(summary: str) -> str:
    if len(summary) <= 3900:
        return summary
    return summary[:3900] + "..."


async def _delete_processing_message(message: SendedMessage | None) -> None:
    if message is None or message.message is None or message.message.body is None:
        return
    await get_bot().delete_message(message.message.body.mid)
