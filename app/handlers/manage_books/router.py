import asyncio
import logging
from pathlib import Path
from typing import Any, TypedDict

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import Command, MessageCallback, MessageCreated
from maxapi.types.attachments import File

from app.books import BookObject, BooksRepository
from app.bot import get_bot
from app.exc import DownloadError, InvalidPath
from app.handlers.manage_books.keyboards import cancel_keyboard, menu_keyboard
from app.handlers.manage_books.utils import (
    compile_books_list,
    download_file,
)
from app.states import ManageBooks

router = Router()
logger = logging.getLogger("manage_books")
logger.setLevel(logging.WARNING)


class ManageBooksData(TypedDict):
    menu_message_id: str
    menu_chat_id: int
    to_delete: list[str]


async def books_menu(context: MemoryContext, chat_id: int | None = None):
    await context.set_state(ManageBooks.main_menu)
    data = await context.get_data()

    if data.get("menu_message_id") is None:
        data: dict[str, Any] = {"menu_chat_id": 0, "menu_message_id": ""}
    data = ManageBooksData(**data)

    _books = compile_books_list(BooksRepository().list_books())

    if _books:
        text = f"Ваши учебники:\n{'\n'.join(_books)}"
    else:
        text = "Кажется у вас еще нет учебников...\nДобавьте их!"

    _markup = menu_keyboard(len(_books) == 0)

    if data["menu_message_id"] != 0 and chat_id is None:
        await get_bot().edit_message(
            message_id=data["menu_message_id"],
            text=text,
            attachments=[_markup],
        )
        return
    message = await get_bot().send_message(
        chat_id=chat_id,
        text=text,
        attachments=[_markup],
    )
    if message is None:
        return
    data["menu_message_id"] = message.message.body.mid
    data["menu_chat_id"] = message.message.recipient.chat_id
    await context.set_data(dict(data))


@router.message_callback(F.callback.payload == "menu:add", ManageBooks.main_menu)
async def select_book_name(event: MessageCallback, context: MemoryContext):
    await context.set_state(ManageBooks.select_book_name)
    message_id = ManageBooksData(**(await context.get_data()))["menu_message_id"]
    await get_bot().edit_message(
        message_id=message_id,
        text="Пожалуйста, укажите название учебника (предмет, класс, автор, год)",
        attachments=[cancel_keyboard()],
    )


@router.message_callback(F.callback.payload == "menu:delete", ManageBooks.main_menu)
async def select_book_for_delete(event: MessageCallback, context: MemoryContext):
    await context.set_state(ManageBooks.select_for_delete)
    message_id = ManageBooksData(**(await context.get_data()))["menu_message_id"]

    _books = BooksRepository().list_books()
    await context.update_data(books=_books)

    _compiled_books = compile_books_list(_books)
    if _books:
        text = f"Ваши учебники:\n{'\n'.join(_compiled_books)}\nВведите номер учебника, который хотите удалить"
    else:
        text = "Кажется у вас еще нет учебников..."

    await get_bot().edit_message(
        message_id=message_id,
        text=text,
        attachments=[cancel_keyboard()],
    )


@router.message_created(F.message.body.text, ManageBooks.select_book_name)
async def upload_book(event: MessageCallback, context: MemoryContext):
    await context.set_state(ManageBooks.upload_book)

    message = await event.message.answer(
        text="""\
Загрузите файл учебника
Доступные форматы: pdf
""",
        attachments=[cancel_keyboard()],
    )
    await context.update_data(
        menu_message_id=message.message.body.mid, book_name=event.message.body.text
    )


@router.message_created(ManageBooks.upload_book, F.message.body.attachments.len() == 1)
async def upload_book_file(event: MessageCreated, context: MemoryContext):
    if not isinstance(event.message.body.attachments[0], File):
        return
    file = event.message.body.attachments[0]

    message = await get_bot().send_message(
        chat_id=event.chat.chat_id,
        text="""\
Загрузка файла ⏳...""",
    )
    await context.update_data(menu_message_id=message.message.body.mid)

    data = await context.get_data()

    _original_filename = file.filename.split(".")
    _extension = _original_filename[-1]
    _filename = f"{data['book_name']}.{_extension}"

    async def _parse_book(path: Path):
        await BooksRepository().parse_then_add_book(path, title=data["book_name"])
        if await context.get_state() == ManageBooks.main_menu:
            await books_menu(context=context)

    try:
        path = await download_file(_filename, file.payload.url)
        asyncio.create_task(_parse_book(path))
        await books_menu(context)
        return

    except InvalidPath:
        user_id = event.message.sender.user_id
        logger.warning(f"User attempted to exploit file saving! {user_id=}")
    except DownloadError:
        logger.warning("Failed to download file", exc_info=True)

    await get_bot().edit_message(
        message_id=message.message.body.mid,
        text="Не удалось загрузить файл",
        attachments=[cancel_keyboard()],
    )


@router.message_created(F.message.body.text, ManageBooks.select_for_delete)
async def delete_selected_book(event: MessageCreated, context: MemoryContext):
    body = event.message.body
    if body is None:
        return

    text = body.text
    if text is None:
        return

    try:
        index = int(text)
    except ValueError:
        return

    data = await context.get_data()
    books: list[BookObject] = data["books"]

    if index < 1 or index > len(books):
        return

    path = books[index - 1][1]

    if BooksRepository().delete_book(path):
        await books_menu(context, chat_id=event.chat.chat_id)
        return

    await get_bot().edit_message(
        message_id=message.message.body.mid,
        text="Не удалось удалить книгу",
        attachments=[cancel_keyboard()],
    )


async def cancel(event: MessageCallback, context: MemoryContext) -> None:
    await books_menu(context)


router.message_callback.register(
    cancel, F.callback.payload == "cancel", ManageBooks.select_book_name
)
router.message_callback.register(
    cancel, F.callback.payload == "cancel", ManageBooks.upload_book
)
router.message_callback.register(
    cancel, F.callback.payload == "cancel", ManageBooks.select_for_delete
)


# ----------------
#    Commands
# ----------------


@router.message_created(Command("books"))
async def open_books_menu(message: MessageCreated, context: MemoryContext):
    await books_menu(context, chat_id=message.chat.chat_id)


router.message_created.register(open_books_menu, F.message.body.text == "Мои книги")
