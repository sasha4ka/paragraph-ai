import json
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

    llm = client or get_async_openai_client()
    try:
        response = await llm.chat.completions.parse(
            model=settings.openai_model,
            messages=messages,
            response_format=ParagraphSelection,
        )
    except (
        APIConnectionError,
        APIError,
        APITimeoutError,
        TypeError,
        ValueError,
    ) as exc:
        raise ParagraphSelectionError(
            "Не удалось распознать выбранные параграфы."
        ) from exc

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
    unknown_ids = [paragraph_id for paragraph_id in selected_ids if paragraph_id not in catalog]
    if unknown_ids:
        raise ParagraphSelectionError(
            "Модель выбрала отсутствующие параграфы: " + ", ".join(unknown_ids)
        )
    return selected_ids