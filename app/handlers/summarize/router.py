import asyncio
import json
import logging
import re
import tempfile
from html import unescape
from pathlib import Path

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.enums import ParseMode
from maxapi.methods.types.sended_message import SendedMessage
from maxapi.types import CallbackButton, MessageCallback, MessageCreated
from maxapi.types.attachments.attachment import Attachment
from maxapi.types.attachments.upload import AttachmentUpload
from maxapi.types.input_media import InputMedia, InputMediaBuffer
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.books import BooksRepository
from app.bot import get_bot
from app.exc import GenerationError
from app.handlers.manage_books.utils import compile_books_list
from app.handlers.navigation import go_to_navigation
from app.logics.communication import Communication
from app.logics.layout.renderer import render_html
from app.logics.select_paragraph import (
    ParagraphSelectionError,
)
from app.logics.select_paragraph import (
    select_paragraphs as resolve_paragraphs,
)
from app.logics.summary.models import BakedBlock, SourceParagraph
from app.logics.summary.summary_generator import (
    generate_card_summary,
    generate_text_summary,
)
from app.logics.test_check import AnswerChecker
from app.logics.test_generator import GeneratedTest, QuestionGenerator, TestQuestion
from app.states import Navigation, Summarize

router = Router()

logger = logging.getLogger("summarizer")
MAX_CARD_IMAGES_PER_MESSAGE = 12


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
    await _start_summarize_workflow(event, context, mode="text")


@router.message_callback(
    F.callback.payload == "navigation:oral_report_cards", Navigation.navigation
)
async def start_card_summarize(event: MessageCallback, context: MemoryContext):
    await _start_summarize_workflow(event, context, mode="cards")


@router.message_callback(
    F.callback.payload == "navigation:knowledge_check", Navigation.navigation
)
async def start_quiz(event: MessageCallback, context: MemoryContext):
    await _start_summarize_workflow(event, context, mode="quiz")


async def _start_summarize_workflow(
    event: MessageCallback, context: MemoryContext, mode: str
):
    books = BooksRepository().list_books()
    if not books:
        await event.answer(
            notification="У вас пока нет загруженных учебников.", notify=True
        )
        return

    await context.update_data(books=books, summary_mode=mode)
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

    try:
        book = BooksRepository().get_book(books[index][1])
    except (OSError, ValueError):
        await context.update_data(books=BooksRepository().list_books())
        await event.message.answer(text="Эта книга недоступна. Выберите другую.")
        return
    paragraphs = list(book.metadata.paragraphs.items())
    await context.update_data(book_path=books[index][1], paragraphs=paragraphs)
    await context.set_state(Summarize.select_paragraphs)

    await event.message.answer(
        text="Введите номер или название одного параграфа.",
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
    mode = data.get("summary_mode", "text")
    await context.set_state(Summarize.processing)
    processing_message = await event.message.answer(
        text="Готовлю вопросы ⏳" if mode == "quiz" else "Готовлю конспект ⏳"
    )
    try:
        logger.info(f"resolving paragraphs {mid=} {uid=}")
        selected_ids = await resolve_paragraphs(body.text, paragraph_titles)
    except ParagraphSelectionError:
        logger.exception("error resolving paragraph")
        await _delete_processing_message(processing_message)
        await context.set_state(Summarize.select_paragraphs)
        await event.message.answer(
            text="Не удалось выбрать параграф. Уточните номер или название.",
            attachments=[cancel_keyboard()],
        )
        return

    if len(selected_ids) != 1:
        await _delete_processing_message(processing_message)
        await context.set_state(Summarize.select_paragraphs)
        await event.message.answer(
            text="Выберите только один параграф.", attachments=[cancel_keyboard()]
        )
        return

    try:
        book = BooksRepository().get_book(data["book_path"])
        paragraph_id = selected_ids[0]
        paragraph_text = await book.get_text([paragraph_id])
        if not paragraph_text.strip():
            raise GenerationError("Selected paragraph has no extractable text")
        if mode == "quiz":
            test = await QuestionGenerator().generate_async(paragraph_text)
            await _delete_processing_message(processing_message)
            processing_message = None
            await _send_quiz_question(event, test["questions"][0])
            await context.update_data(quiz_test=test, quiz_answers={})
            await context.set_state(Summarize.quiz_answer)
            return
        source_item = SourceParagraph(
            title=paragraphs[paragraph_id].title,
            text=paragraph_text,
            paragraph_id=_event_paragraph_id(paragraph_id, 0),
        )
        logger.info(
            f"summarizing {book.metadata.title} {source_item.title} {mid=} {uid=}"
        )
        generate = generate_card_summary if mode == "cards" else generate_text_summary
        result: list[BakedBlock] | None = None
        async for generation_event in generate(source_item):
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

        if not result:
            raise GenerationError("Summary returned no blocks")
        await _delete_processing_message(processing_message)
        processing_message = None
        await context.set_state(Summarize.chat_mode)
        if mode == "cards":
            await _send_card_blocks(event, result)
        else:
            await _send_text_blocks(event, result)

    except Exception:
        await _delete_processing_message(processing_message)
        await context.set_state(Summarize.select_paragraphs)
        await event.message.answer(
            text="Не удалось подготовить вопросы." if mode == "quiz" else "Не удалось подготовить конспект.",
            attachments=[cancel_keyboard()],
        )
        logger.exception("Error generating material for user %s", uid)


async def _send_text_blocks(event: MessageCreated, result: list[BakedBlock]) -> None:
    for i, block in enumerate(result):
        format_mode = ParseMode.HTML
        text = block.text
        if len(text) > 3900:
            format_mode = None
            text = unescape(re.sub(r"</?[a-zA-Z][^>]*>", "", text))
        chunks = _split_message(text)
        for j, chunk in enumerate(chunks):
            if i == len(result) - 1 and j == len(chunks) - 1:
                await event.message.answer(
                    text=chunk, format=format_mode, attachments=[exit_keyboard()]
                )
            else:
                await event.message.answer(text=chunk, format=format_mode)
        await asyncio.sleep(0.5)


async def _send_quiz_question(event: MessageCreated, question: TestQuestion) -> None:
    text = f"{question['id']}. {question['question']}"
    if "options" in question:
        text += "\n\n" + "\n".join(
            f"{index}. {option}" for index, option in enumerate(question["options"], 1)
        )
        text += "\n\nОтветьте числом от 1 до 4."
    else:
        text += "\n\nНапишите развёрнутый ответ."
    for chunk in _split_message(text):
        await event.message.answer(text=chunk, attachments=[cancel_keyboard()])


@router.message_created(F.message.body.text, Summarize.quiz_answer)
async def answer_quiz_question(event: MessageCreated, context: MemoryContext):
    data = await context.get_data()
    test: GeneratedTest = data["quiz_test"]
    answers = dict(data["quiz_answers"])
    if len(answers) < len(test["questions"]):
        question = test["questions"][len(answers)]
        answer = event.message.body.text.strip()
        if "options" in question and answer not in {"1", "2", "3", "4"}:
            await event.message.answer(text="Введите номер варианта от 1 до 4.")
            return
        if not answer:
            await event.message.answer(text="Введите ответ на вопрос.")
            return
        answers[question["id"]] = int(answer) - 1 if "options" in question else answer
        await context.update_data(quiz_answers=answers)
        if len(answers) < len(test["questions"]):
            await _send_quiz_question(event, test["questions"][len(answers)])
            return

    await context.set_state(Summarize.quiz_check)
    try:
        report = await AnswerChecker(test, answers).check_async()
    except (ValueError, RuntimeError):
        logger.exception("Error checking quiz answers")
        await context.set_state(Summarize.quiz_answer)
        await event.message.answer(
            text="Проверка не удалась. Отправьте «Повторить», чтобы проверить сохранённые ответы.",
            attachments=[cancel_keyboard()],
        )
        return

    result = f"{report['total_score']:g} из {report['max_score']} баллов."
    mistakes = [
        f"{item['id']}. {item['feedback']}"
        for item in report["results"]
        if item["score"] < item["max_score"]
    ]
    details = "\n\n".join(mistakes) if mistakes else "Все ответы верны."
    for chunk in _split_message(f"Результат\n\n{result}\n\n{details}"):
        await event.message.answer(text=chunk)
    await context.update_data(
        quiz_chat=[{
            "role": "assistant",
            "content": json.dumps(
                {"test": test, "answers": answers, "report": report}, ensure_ascii=False
            ),
        }],
    )
    await context.set_state(Summarize.quiz_review)
    await event.message.answer(
        text="Можно задать вопрос по результату.", attachments=[exit_keyboard()]
    )


@router.message_created(F.message.body.text, Summarize.quiz_review)
async def review_quiz(event: MessageCreated, context: MemoryContext):
    question = event.message.body.text.strip()
    if not question:
        return
    history = (await context.get_data())["quiz_chat"]
    messages = [*history, {"role": "user", "content": question}]
    await context.set_state(Summarize.quiz_check)
    try:
        answer = await Communication(messages).respond_async()
        await context.update_data(quiz_chat=[*messages, {"role": "assistant", "content": answer}])
    except (ValueError, RuntimeError):
        logger.exception("Error reviewing quiz")
        answer = "Не удалось разобрать ответ. Попробуйте ещё раз."
    finally:
        await context.set_state(Summarize.quiz_review)
    for chunk in _split_message(answer):
        await event.message.answer(text=chunk, attachments=[exit_keyboard()])


async def _send_card_blocks(event: MessageCreated, blocks: list[BakedBlock]) -> None:
    if not blocks:
        raise GenerationError("Card workflow returned no cards")

    with tempfile.TemporaryDirectory(prefix="paragraph-cards-") as temp_dir:
        for batch_start in range(0, len(blocks), MAX_CARD_IMAGES_PER_MESSAGE):
            batch = blocks[
                batch_start : batch_start + MAX_CARD_IMAGES_PER_MESSAGE
            ]
            attachments: list[
                Attachment | InputMedia | InputMediaBuffer | AttachmentUpload
            ] = []
            for offset, block in enumerate(batch):
                image_index = batch_start + offset
                image_path = Path(temp_dir) / f"card-{image_index + 1}.png"
                await render_html(block.text, image_path)
                attachments.append(InputMedia(str(image_path)))

            await event.message.answer(
                attachments=attachments,
            )
            if batch_start + len(batch) < len(blocks):
                await asyncio.sleep(0.5)

    await event.message.answer(attachments=[exit_keyboard()])


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
    try:
        await get_bot().delete_message(message.message.body.mid)
    except Exception:
        logger.warning("Could not remove progress message", exc_info=True)


def _event_paragraph_id(paragraph_id: str, index: int) -> int:
    try:
        return int(paragraph_id)
    except ValueError:
        return index + 1


@router.message_callback(
    F.callback.payload == "Summarize.chat_mode:exit", Summarize.chat_mode
)
@router.message_callback(
    F.callback.payload == "Summarize.chat_mode:exit", Summarize.quiz_review
)
async def exit_chat_mode(event: MessageCallback, context: MemoryContext):
    await go_to_navigation(event, context, new_message=True)


@router.message_callback(F.callback.payload == "cancel", Summarize.select_book)
async def cancel_selection(event: MessageCallback, context: MemoryContext):
    await go_to_navigation(event, context)


@router.message_callback(F.callback.payload == "cancel", Summarize.select_paragraphs)
@router.message_callback(F.callback.payload == "cancel", Summarize.quiz_answer)
async def cancel_selection_1(event: MessageCallback, context: MemoryContext):
    await go_to_navigation(event, context)
