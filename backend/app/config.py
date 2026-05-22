"""集中管理后端配置，供主应用、数据库和模型模块读取。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """定义系统运行时会用到的配置项。"""

    openai_api_key: str = ""
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_provider: str = "mock"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 150
    llm_max_tokens: int = 2200
    llm_agent_timeout_seconds: int = 50
    llm_review_timeout_seconds: int = 285
    llm_image_detail: str = "high"
    llm_max_model_image_bytes: int = 15 * 1024 * 1024
    llm_image_max_side: int = 2048
    database_url: str = "sqlite:///./archcritic.db"
    upload_dir: str = "uploads"
    wiki_dir: str = "../../wiki-test/wiki"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    app_name: str = "ArchCritic API"
    app_version: str = "0.1.0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回缓存后的配置对象。"""
    return Settings()


settings = get_settings()
