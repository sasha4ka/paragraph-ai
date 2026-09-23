from typing import TypedDict

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import Command, MessageCallback, MessageCreated
from maxapi.types.attachments import File

from app.bot import get_bot
from app.handlers.manage_books.keyboards import menu_keyboard, upload_book_keyboard
from app.states import ManageBooks

router = Router()


class ManageBooksData(TypedDict):
    menu_message_id: str
    menu_chat_id: int

    books: list[str]


async def books_menu(context: MemoryContext, chat_id: int | None = None):
    await context.set_state(ManageBooks.main_menu)
    data = await context.get_data()
    if data.get("menu_message_id") is None:
        data = ManageBooksData(menu_chat_id=0, menu_message_id="", books=[])

    if data["books"]:
        text = f"""\
Ваши учебники:
{"\n".join(["- " + name for name in data["books"]])}
"""
    else:
        text = """\
Кажется у вас еще нет учебников...
Добавьте их!"""

    if data["menu_message_id"] != 0 and chat_id is None:
        await get_bot().edit_message(
            message_id=data["menu_message_id"], text=text, attachments=[menu_keyboard()]
        )
        return
    message = await get_bot().send_message(
        chat_id=chat_id,
        text=text,
        attachments=[menu_keyboard()],
    )
    if message is None:
        return
    data["menu_message_id"] = message.message.body.mid
    data["menu_chat_id"] = message.message.recipient.chat_id
    await context.set_data(dict(data))


@router.message_callback(F.callback.payload == "menu:add", ManageBooks.main_menu)
async def upload_book(event: MessageCallback, context: MemoryContext):
    await context.set_state(ManageBooks.upload_book)
    data = await context.get_data()
    data = ManageBooksData(**data)

    await get_bot().edit_message(
        message_id=data["menu_message_id"],
        text="""\
Загрузите файл учебника
Доступные форматы: pdf
""",
        attachments=[upload_book_keyboard()],
    )


@router.message_callback(F.callback.payload == "cancel", ManageBooks.upload_book)
async def cancel_uploading(event: MessageCallback, context: MemoryContext):
    await books_menu(context)


@router.message_created(ManageBooks.upload_book)
async def upload_book_file(event: MessageCreated, context: MemoryContext):
    if event.message.body is None:
        return
    if event.message.body.attachments is None:
        return
    if len(event.message.body.attachments) != 1:
        return
    if not isinstance(event.message.body.attachments[0], File):
        return

    file_attachment = event.message.body.attachments[0]
    data = await context.get_data()
    data = ManageBooksData(**data)

    data["books"].append(file_attachment.filename)
    await context.set_data(dict(data))
    await books_menu(context, chat_id=event.chat.chat_id)


# ----------------
#    Commands
# ----------------


@router.message_created(Command("books"))
async def open_books_menu(message: MessageCreated, context: MemoryContext):
    await books_menu(context, chat_id=message.chat.chat_id)


router.message_created.register(open_books_menu, F.message.body.text == "Мои книги")
