import logging

from app.bot import get_bot
from app.settings import settings

logger = logging.getLogger("logics.feedback")


async def add_feedback(feedback: str, name: str | None, user_id: int) -> None:
    """
    Add feedback to the database.

    Args:
        feedback (str): The feedback text.
        name (str): The name of the user providing feedback.
        user_id (int): The ID of the user providing feedback.
    """
    logger.info(f"Adding feedback from user {user_id=} {name}: {feedback}")

    if settings.admin_chat_id:
        await get_bot().send_message(
            chat_id=settings.admin_chat_id,
            text=f"""\
Отзыв от {name or "анонимного пользователя"} {user_id=}
Текст: {feedback}\
""",
        )
