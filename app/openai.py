from openai import AsyncOpenAI, OpenAI

from app.settings import settings


def get_openai_client() -> OpenAI:
    if not settings.openai_api_token:
        raise ValueError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=settings.openai_api_token, base_url=settings.openai_base_url)


def get_async_openai_client() -> AsyncOpenAI:
    if not settings.openai_api_token:
        raise ValueError("OPENAI_API_KEY is not set")
    return AsyncOpenAI(
        api_key=settings.openai_api_token, base_url=settings.openai_base_url
    )
