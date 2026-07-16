"""提交评图共享配置，统一模型来源、阶段状态和上传限制。"""

from fastapi import HTTPException

from app.config import get_settings

REAL_LLM_PROVIDERS = {"openai", "dashscope", "gemini"}
ALLOWED_DRAWING_TYPES = {
    "site",
    "plan",
    "plan-2",
    "plan-3",
    "plan-4",
    "plan-5",
    "plan-6",
    "plan-7",
    "section",
    "elevation",
    "analysis",
    "render",
}
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
ALLOWED_DRAWING_FILE_TYPES = {
    **ALLOWED_IMAGE_TYPES,
    "application/pdf": ".pdf",
}
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}
CANCELLED_SUBMISSIONS: set[int] = set()
MODEL_PRESETS = {
    "mock": "demo",
    "openai": "gpt-4o-mini",
    "dashscope": "qwen3.6-plus",
    "gemini": "gemini-2.5-flash",
}


class EvaluationCancelled(Exception):
    """表示用户主动暂停本次评图。"""


def ensure_evaluation_active(submission_id: int) -> None:
    """在模型调用之间检查用户是否已请求暂停。"""
    if submission_id in CANCELLED_SUBMISSIONS:
        raise EvaluationCancelled()


def resolve_llm_provider(provider: str | None) -> str:
    """解析本次评图使用的模型来源，默认读取环境配置。"""
    settings = get_settings()
    resolved = (provider or settings.llm_provider).strip().lower()
    aliases = {"qwen": "dashscope", "qianwen": "dashscope", "bailian": "dashscope"}
    resolved = aliases.get(resolved, resolved)
    if resolved not in {"mock", *REAL_LLM_PROVIDERS}:
        raise HTTPException(status_code=400, detail=f"暂不支持的模型来源：{resolved}。")
    return resolved


def resolve_llm_model(provider: str, model: str | None) -> str:
    """解析本次评图使用的模型名称。"""
    cleaned_model = (model or "").strip()
    if cleaned_model:
        return cleaned_model
    settings = get_settings()
    if provider == settings.llm_provider.lower() and settings.llm_model:
        return settings.llm_model
    return MODEL_PRESETS.get(provider, settings.llm_model)
