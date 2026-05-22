"""上传本地图纸到百炼临时 OSS，供多模态模型通过 URL 读取。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from uuid import uuid4

import httpx


@dataclass
class DashScopeUploadResult:
    """百炼临时文件上传结果。"""

    url: str
    expires_at: datetime


class DashScopeUploadError(RuntimeError):
    """百炼临时文件上传失败时抛出的明确异常。"""


class DashScopeFileClient:
    """负责获取上传策略并把本地文件上传到百炼临时存储。"""

    def __init__(self, api_key: str, model: str, timeout_seconds: int = 90) -> None:
        """保存百炼 API Key、模型名和请求超时。"""
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def upload_file(self, file_path: Path, mime_type: str) -> DashScopeUploadResult:
        """上传本地文件并返回模型可访问的 oss:// URL。"""
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                    policy = self._get_policy(client)
                    object_key = self._build_object_key(policy["upload_dir"], file_path.name)
                    self._post_file(client, policy, object_key, file_path, mime_type)
                return DashScopeUploadResult(
                    url=f"oss://{object_key}",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=47),
                )
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(attempt)

        raise DashScopeUploadError(
            f"图纸上传到百炼临时存储失败，已重试 3 次：{last_error}"
        ) from last_error

    def _get_policy(self, client: httpx.Client) -> dict:
        """获取百炼临时 OSS 上传策略。"""
        response = client.get(
            "https://dashscope.aliyuncs.com/api/v1/uploads",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            params={"action": "getPolicy", "model": self.model},
        )
        response.raise_for_status()
        return response.json()["data"]

    def _post_file(
        self,
        client: httpx.Client,
        policy: dict,
        object_key: str,
        file_path: Path,
        mime_type: str,
    ) -> None:
        """按上传策略把文件 POST 到临时 OSS。"""
        with file_path.open("rb") as file_handle:
            files = {
                "OSSAccessKeyId": (None, policy["oss_access_key_id"]),
                "Signature": (None, policy["signature"]),
                "policy": (None, policy["policy"]),
                "x-oss-object-acl": (None, policy["x_oss_object_acl"]),
                "x-oss-forbid-overwrite": (None, policy["x_oss_forbid_overwrite"]),
                "key": (None, object_key),
                "success_action_status": (None, "200"),
                "file": (file_path.name, file_handle, mime_type),
            }
            response = client.post(policy["upload_host"], files=files)
        response.raise_for_status()

    def _build_object_key(self, upload_dir: str, filename: str) -> str:
        """生成不冲突的临时文件路径。"""
        suffix = Path(filename).suffix
        return f"{upload_dir}/{uuid4().hex}{suffix}"
