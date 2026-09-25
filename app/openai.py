from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAI,
)

from app.settings import settings

__all__ = [
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "AsyncOpenAI",
    "OpenAI",
    "get_async_openai_client",
    "get_openai_client",
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
