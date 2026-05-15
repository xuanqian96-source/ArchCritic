"""诊断百炼多模态调用耗时，用于区分图片传输、流式输出和 JSON 约束的影响。"""

import argparse
import base64
import time
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI

from app.config import get_settings


def build_client(timeout: int) -> OpenAI:
    """创建不打印密钥的百炼 OpenAI 兼容客户端。"""
    settings = get_settings()
    return OpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        http_client=httpx.Client(timeout=timeout, trust_env=False),
        max_retries=0,
    )


def image_data_url(path: Path, mime_type: str) -> str:
    """把本地图纸转成官方示例使用的 data URL。"""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def image_part(data_url: str, detail: str | None) -> dict[str, Any]:
    """生成图片输入字段，可切换是否包含 detail。"""
    payload: dict[str, Any] = {"url": data_url}
    if detail:
        payload["detail"] = detail
    return {"type": "image_url", "image_url": payload}


def run_normal_case(
    client: OpenAI,
    model: str,
    name: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 500,
    response_format: dict[str, str] | None = None,
) -> None:
    """执行一次非流式调用并打印耗时摘要。"""
    start = time.monotonic()
    try:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0,
            "extra_body": {"enable_thinking": False},
        }
        if response_format:
            kwargs["response_format"] = response_format
        response = client.chat.completions.create(**kwargs)
        elapsed = time.monotonic() - start
        text = (response.choices[0].message.content or "").replace("\n", " ")[:140]
        usage = getattr(response, "usage", None)
        token_text = ""
        if usage:
            token_text = (
                f" input={getattr(usage, 'prompt_tokens', '?')}"
                f" output={getattr(usage, 'completion_tokens', '?')}"
            )
        print(f"{name}: ok {elapsed:.1f}s{token_text} | {text}", flush=True)
    except Exception as exc:
        elapsed = time.monotonic() - start
        print(f"{name}: fail {elapsed:.1f}s | {str(exc).replace(chr(10), ' ')[:180]}", flush=True)


def run_stream_case(
    client: OpenAI,
    model: str,
    name: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 500,
) -> None:
    """执行一次流式调用，分别记录首字时间和总耗时。"""
    start = time.monotonic()
    first_token_at: float | None = None
    output_parts: list[str] = []
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0,
            stream=True,
            extra_body={"enable_thinking": False},
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                if first_token_at is None:
                    first_token_at = time.monotonic()
                output_parts.append(delta)
        elapsed = time.monotonic() - start
        first = (first_token_at - start) if first_token_at else elapsed
        text = "".join(output_parts).replace("\n", " ")[:140]
        print(f"{name}: ok first={first:.1f}s total={elapsed:.1f}s | {text}", flush=True)
    except Exception as exc:
        elapsed = time.monotonic() - start
        print(f"{name}: fail {elapsed:.1f}s | {str(exc).replace(chr(10), ' ')[:180]}", flush=True)


def main() -> None:
    """运行固定诊断用例。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="本地图纸路径")
    parser.add_argument("--mime", default="image/png", help="图片 MIME 类型")
    parser.add_argument("--timeout", type=int, default=90, help="单次请求超时秒数")
    args = parser.parse_args()

    settings = get_settings()
    image_path = Path(args.image)
    data_url = image_data_url(image_path, args.mime)
    client = build_client(args.timeout)

    print(f"model={settings.llm_model}", flush=True)
    print(f"image={image_path.name} bytes={image_path.stat().st_size}", flush=True)

    text_messages = [
        {"role": "user", "content": "请只用一句中文回答：建筑平面评图需要看哪些信息？"}
    ]
    run_normal_case(client, settings.llm_model, "text_only", text_messages, 120)

    simple_prompt = "请描述这张建筑图纸的主要内容，控制在 300 字以内。"
    json_prompt = (
        '请读取这张建筑图纸，只输出 JSON：{"drawing_type":"","spaces":[],"summary":""}。'
    )

    for detail in [None, "low", "high"]:
        suffix = "no_detail" if detail is None else f"detail_{detail}"
        image_messages = [
            {
                "role": "user",
                "content": [image_part(data_url, detail), {"type": "text", "text": simple_prompt}],
            }
        ]
        run_normal_case(client, settings.llm_model, f"image_simple_{suffix}", image_messages)

    stream_messages = [
        {
            "role": "user",
            "content": [image_part(data_url, None), {"type": "text", "text": simple_prompt}],
        }
    ]
    run_stream_case(client, settings.llm_model, "image_simple_stream_no_detail", stream_messages)

    json_messages = [
        {
            "role": "user",
            "content": [image_part(data_url, None), {"type": "text", "text": json_prompt}],
        }
    ]
    run_normal_case(client, settings.llm_model, "image_json_text_no_detail", json_messages, 500)
    run_normal_case(
        client,
        settings.llm_model,
        "image_json_response_format_no_detail",
        json_messages,
        500,
        {"type": "json_object"},
    )


if __name__ == "__main__":
    main()
