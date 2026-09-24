from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_token: str | None = None
    routerai_api_key: str | None = None
    model: str = "openai/gpt-6-luna"
