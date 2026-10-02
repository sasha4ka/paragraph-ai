import logging

logger = logging.getLogger("logics.feedback")


async def add_feedback(feedback: str, name: str | None, user_id: int) -> None:
    """
    Add feedback to the database.

    Args:
        feedback (str): The feedback text.
        name (str): The name of the user providing feedback.
        user_id (int): The ID of the user providing feedback.
    """
    logger.info(f"Adding feedback from user {user_id} {name}: {feedback}")
