from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_token: str | None = None
    openai_base_url: str = "https://routerai.ru/api/v1"
    default_model: str = "openai/gpt-6-luna"
    parsing_model: str = "deepseek/deepseek-v4.1-flash"
    openai_api_token: str | None = None


settings = Settings()  # type: ignore
