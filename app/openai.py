from typing import Any, cast

from langchain_openai import ChatOpenAI
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAI,
)
from pydantic import BaseModel, ValidationError

from app.settings import settings

__all__ = [
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "AsyncOpenAI",
    "OpenAI",
    "get_async_openai_client",
    "get_openai_client",
    "invoke_structured",
    "structured_output",
]


def get_openai_client(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float = 90.0,
) -> OpenAI:
    token = api_key or settings.openai_api_token
    if not token:
        raise ValueError("OPENAI_API_TOKEN is not set")
    return OpenAI(
        api_key=token,
        base_url=base_url or settings.openai_base_url,
        timeout=timeout,
    )


def get_async_openai_client(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float = 90.0,
) -> AsyncOpenAI:
    token = api_key or settings.openai_api_token
    if not token:
        raise ValueError("OPENAI_API_TOKEN is not set")
    return AsyncOpenAI(
        api_key=token,
        base_url=base_url or settings.openai_base_url,
        timeout=timeout,
    )


async def invoke_structured[T: BaseModel](
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    attempts: int = 3,
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    api_key = settings.openai_api_token
    if not api_key:
        raise ValueError("OPENAI_API_TOKEN is not set")

    model = ChatOpenAI(
        model=settings.default_model,
        api_key=lambda: api_key,
        base_url=settings.openai_base_url,
        temperature=0,
        timeout=90,
    )
    structured_model = cast(Any, model).with_structured_output(
        schema, method="function_calling"
    )

    last_error: ValidationError | None = None
    for attempt in range(attempts):
        try:
            response = await structured_model.ainvoke(
                [("system", system_prompt), ("human", user_prompt)]
            )
            return schema.model_validate(response)
        except ValidationError as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("Structured output validation failed without a model error")


async def structured_output[T: BaseModel](
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    attempts: int = 3,
) -> T:
    return await invoke_structured(
        schema, system_prompt, user_prompt, attempts=attempts
    )


async def invoke_model(system_prompt: str, user_prompt: str) -> str:
    api_key = settings.openai_api_token
    if not api_key:
        raise ValueError("OPENAI_API_TOKEN is not set")

    model = ChatOpenAI(
        model=settings.default_model,
        api_key=lambda: api_key,
        base_url=settings.openai_base_url,
        temperature=0,
        timeout=90,
    )
    response = await model.ainvoke([("system", system_prompt), ("human", user_prompt)])
    return cast(str, response.content)
