"""集中管理后端配置，供主应用、数据库和模型模块读取。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """定义系统运行时会用到的配置项。"""

    openai_api_key: str = ""
    llm_provider: str = "mock"
    llm_model: str = "gpt-4o-mini"
    database_url: str = "sqlite:///./archcritic.db"
    cors_origins: str = "http://localhost:5173"
    app_name: str = "ArchCritic API"
    app_version: str = "0.1.0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回缓存后的配置对象。"""
    return Settings()


settings = get_settings()
