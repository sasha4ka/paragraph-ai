import asyncio
import logging

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.enums import ParseMode
from maxapi.methods.types.sended_message import SendedMessage
from maxapi.types import CallbackButton, MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.books import BooksRepository
from app.bot import get_bot
from app.exc import GenerationError
from app.handlers.manage_books.utils import compile_books_list
from app.handlers.navigation import go_to_navigation
from app.logics.select_paragraph import (
    ParagraphSelectionError,
)
from app.logics.select_paragraph import (
    select_paragraphs as resolve_paragraphs,
)
from app.logics.summary.models import BakedBlock, SourceParagraph
from app.logics.summary.summary_generator import generate_summary
from app.states import Navigation, Summarize

router = Router()

logger = logging.getLogger("summarizer")


def exit_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="Выйти", payload="Summarize.chat_mode:exit"))
    return builder.as_markup()


def cancel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="Отмена", payload="cancel"))
    return builder.as_markup()


@router.message_callback(
    F.callback.payload == "navigation:oral_report", Navigation.navigation
)
async def start_summarize(event: MessageCallback, context: MemoryContext):
    books = BooksRepository().list_books()
    if not books:
        await event.answer(
            notification="У вас пока нет загруженных учебников.", notify=True
        )
        return

    await context.update_data(books=books)
    await context.set_state(Summarize.select_book)

    text = f"Выберите книгу:\n{'\n'.join(compile_books_list(books))}"

    await event.message.edit(text=text, attachments=[cancel_keyboard()])


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
        text="Введите название одного параграфа.",
        attachments=[cancel_keyboard()],
    )


@router.message_created(F.message.body.text, Summarize.select_paragraphs)
async def select_paragraphs(event: MessageCreated, context: MemoryContext):
    mid = event.message.body.mid
    uid = event.from_user.user_id

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
        logger.info(f"resolving paragraphs {mid=} {uid=}")
        selected_ids = await resolve_paragraphs(body.text, paragraph_titles)
    except ParagraphSelectionError:
        logger.exception("error resolving paragraph")
        await _delete_processing_message(processing_message)
        await event.message.answer(
            text="Ошибка выбора параграфа. Попробуйте снова позже"
        )
        return

    await context.set_state(Summarize.chat_mode)
    book = BooksRepository().get_book(data["book_path"])

    if len(selected_ids) != 1:
        await _delete_processing_message(processing_message)
        await context.set_state(Summarize.select_paragraphs)
        await event.message.answer(text="Выберите только один параграф для конспекта.")
        return

    try:
        paragraph_id = selected_ids[0]
        paragraph_text = await book.get_text([paragraph_id])
        source_item = SourceParagraph(
            title=paragraphs[paragraph_id].title,
            text=paragraph_text,
            paragraph_id=_event_paragraph_id(paragraph_id, 0),
        )
        logger.info(
            f"summarizing {book.metadata.title} {source_item.title} {mid=} {uid=}"
        )
        result: list[BakedBlock] | None = None
        async for generation_event in generate_summary(source_item):
            match generation_event.status:
                case "cleaning":
                    logger.info(f"cleaning text {mid=} {uid=}")
                    await processing_message.message.edit(
                        text="Очистка текста сообщения... ✨"
                    )
                case "planing":
                    logger.info(f"making plan {mid=} {uid=}")
                    await processing_message.message.edit(
                        text="Подготовка плана доклада... ✨"
                    )
                case "extracting":
                    logger.info(f"extracting facts {mid=} {uid=}")
                    await processing_message.message.edit(
                        text="Выделение информации... ✨"
                    )
                case "baking":
                    logger.info(f"baking text blocks {mid=} {uid=}")
                    await processing_message.message.edit(text="Добавляем магии... ✨")
                case "done":
                    result = generation_event.result

        if result is None:
            raise GenerationError("Summary didn't generated")

    except Exception:
        await _delete_processing_message(processing_message)
        await context.set_state(Summarize.select_paragraphs)
        await event.message.answer(text="Не удалось подготовить конспект.")
        user_id = event.message.sender.user_id
        logger.exception(f"Error generating summary {user_id=}")
        return

    await _delete_processing_message(processing_message)
    for i, block in enumerate(result):
        chunks = _split_message(block.text)
        for j, chunk in enumerate(chunks):
            if i == len(result) - 1 and j == len(chunks) - 1:
                await event.message.answer(
                    text=chunk, format=ParseMode.HTML, attachments=[exit_keyboard()]
                )
            else:
                await event.message.answer(text=chunk, format=ParseMode.HTML)
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


def _event_paragraph_id(paragraph_id: str, index: int) -> int:
    try:
        return int(paragraph_id)
    except ValueError:
        return index + 1


@router.message_callback(
    F.callback.payload == "Summarize.chat_mode:exit", Summarize.chat_mode
)
async def exit_chat_mode(event: MessageCallback, context: MemoryContext):
    await go_to_navigation(event, context, new_message=True)


@router.message_callback(F.callback.payload == "cancel", Summarize.select_book)
async def cancel_selection(event: MessageCallback, context: MemoryContext):
    await go_to_navigation(event, context)


@router.message_callback(F.callback.payload == "cancel", Summarize.select_paragraphs)
async def cancel_selection_1(event: MessageCallback, context: MemoryContext):
    await go_to_navigation(event, context)
