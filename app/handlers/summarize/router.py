import asyncio
import logging

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.enums import ParseMode
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
from app.logics.summary.models import SourceParagraph, SynthesisResult
from app.logics.summary.progress import SummaryProgress
from app.logics.summary.summary_generator import generate_summary_with_events
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
    processing_message = await event.message.answer(text="Готовлю конспект ⏳")
    try:
        selected_ids = await resolve_paragraphs(body.text, paragraph_titles)
    except ParagraphSelectionError as exc:
        await _delete_processing_message(processing_message)
        await event.message.answer(text=str(exc))
        return

    await context.set_state(Summarize.chat_mode)
    book = BooksRepository().get_book(data["book_path"])

    try:
        await _edit_processing_message(processing_message, "Читаю выбранные параграфы…")
        source_paragraphs = await asyncio.gather(
            *(book.get_text([paragraph_id]) for paragraph_id in selected_ids)
        )
        source_items = [
            SourceParagraph(
                title=paragraphs[paragraph_id].title,
                text=paragraph_text,
                paragraph_id=_event_paragraph_id(paragraph_id, index),
            )
            for index, (paragraph_id, paragraph_text) in enumerate(
                zip(selected_ids, source_paragraphs, strict=True)
            )
        ]
        progress = SummaryProgress(source_items)
        summary: SynthesisResult | None = None
        last_progress_status = ""
        async for summary_event in generate_summary_with_events(source_items):
            progress.handle_event(summary_event)
            progress_status = progress.get_status()
            if progress_status != last_progress_status:
                await _edit_processing_message(processing_message, progress_status)
                last_progress_status = progress_status
            if summary_event.result is not None:
                summary = summary_event.result
        if summary is None:
            raise RuntimeError("Summary generator did not return a final result")
    except Exception:
        await _delete_processing_message(processing_message)
        await context.set_state(Summarize.select_paragraphs)
        await event.message.answer(text="Не удалось подготовить конспект.")
        user_id = event.message.sender.user_id
        logger.exception(f"Error generating summary {user_id=}")
        return

    summary_blocks = [
        (title, block)
        for title, block in (
            ("Конспект", summary.summary_block),
            ("Важные сведения", summary.information_block),
        )
        if block.strip()
    ]

    await _delete_processing_message(processing_message)
    for title, block in summary_blocks:
        message = f"{title}\n\n{block}"
        for chunk in _split_message(message):
            await event.message.answer(text=chunk, format=ParseMode.MARKDOWN)
        await asyncio.sleep(0.5)


def _split_message(text: str, limit: int = 3900) -> list[str]:
    """Split generated text under MAX's message limit without dropping content."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            chunks.append(line[:limit].rstrip())
            line = line[limit:]

        if current and len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = ""
        current += line

    if current:
        chunks.append(current.rstrip())
    return chunks


async def _delete_processing_message(message: SendedMessage | None) -> None:
    if message is None or message.message is None or message.message.body is None:
        return
    await get_bot().delete_message(message.message.body.mid)


async def _edit_processing_message(message: SendedMessage | None, text: str) -> None:
    if message is None or message.message is None or message.message.body is None:
        return
    try:
        await get_bot().edit_message(
            message_id=message.message.body.mid,
            text=text,
        )
    except Exception:
        logger.warning("Failed to update summary progress message", exc_info=True)


def _event_paragraph_id(paragraph_id: str, index: int) -> int:
    try:
        return int(paragraph_id)
    except ValueError:
        return index + 1
