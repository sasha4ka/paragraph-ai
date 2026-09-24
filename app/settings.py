from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    api_token: str
    openai_base_url: str | None = None
    openai_model: str = "openai/gpt-6-luna"
    openai_api_token: str | None = None


settings = Settings()  # type: ignore
