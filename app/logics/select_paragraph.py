import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    get_async_openai_client,
)
from app.settings import settings

logger = logging.getLogger("paragraph_resolver")


class ParagraphSelection(BaseModel):
    paragraph_ids: list[str] = Field(min_length=1)


class ParagraphSelectionError(ValueError):
    """The user's paragraph selection could not be resolved."""


async def select_paragraphs(
    user_text: str,
    paragraphs: Mapping[str, str] | Sequence[tuple[str, Any]],
    client: AsyncOpenAI | None = None,
) -> list[str]:
    catalog = dict(paragraphs)
    if not user_text.strip():
        raise ParagraphSelectionError("Введите название хотя бы одного параграфа.")
    if not catalog:
        raise ParagraphSelectionError("В выбранной книге нет параграфов.")

    query = user_text.strip()
    number = re.fullmatch(r"(?:§\s*|параграф\s+)?(\d+)\.?", query, re.IGNORECASE)
    if number:
        matches = []
        for paragraph_id, title in catalog.items():
            heading_number = re.search(r"§\s*(\d+)\b", str(title))
            if heading_number and int(heading_number[1]) == int(number[1]):
                matches.append(paragraph_id)
        if len(matches) == 1:
            return matches
    exact = [
        paragraph_id
        for paragraph_id, title in catalog.items()
        if query.casefold() == str(title).strip().casefold()
    ]
    if len(exact) == 1:
        return exact

    catalog_text = "\n".join(
        f"{paragraph_id}: {title}" for paragraph_id, title in catalog.items()
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Выбери параграфы учебника по человеческому запросу пользователя. "
                "Верни только ID параграфов из каталога. Можно выбрать несколько. "
                "Не придумывай ID и не выбирай похожий параграф, если соответствия нет."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Каталог параграфов:\n{catalog_text}\n\n"
                f"Запрос пользователя:\n{user_text}"
            ),
        },
    ]

    try:
        options = {
            "model": settings.default_model,
            "messages": messages,
            "response_format": ParagraphSelection,
        }
        if client is None:
            async with get_async_openai_client() as owned_client:
                response = await owned_client.chat.completions.parse(**options)
        else:
            response = await client.chat.completions.parse(**options)
    except (
        APIConnectionError,
        APIError,
        APITimeoutError,
        TypeError,
        ValueError,
    ) as exc:
        logger.exception("failed to resolve")
        raise ParagraphSelectionError() from exc

    if not response.choices:
        raise ParagraphSelectionError("Модель не вернула выбранные параграфы.")
    parsed = response.choices[0].message.parsed
    if parsed is None:
        content = response.choices[0].message.content
        if not content:
            raise ParagraphSelectionError("Модель не вернула выбранные параграфы.")
        try:
            parsed = ParagraphSelection.model_validate(json.loads(content))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ParagraphSelectionError(
                "Не удалось распознать выбранные параграфы."
            ) from exc

    selected_ids = list(dict.fromkeys(parsed.paragraph_ids))
    unknown_ids = [
        paragraph_id for paragraph_id in selected_ids if paragraph_id not in catalog
    ]
    if unknown_ids:
        raise ParagraphSelectionError(
            "Модель выбрала отсутствующие параграфы: " + ", ".join(unknown_ids)
        )
    return selected_ids
