"""DeepSeek API 共用工具（供各平台文案生成脚本使用）。"""

import os
import sys

from openai import APIConnectionError, APIError, OpenAI, RateLimitError


def has_deepseek_api_key() -> bool:
    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip().strip('"').strip("'")
    return bool(key.startswith("sk-"))


def load_deepseek_api_key() -> str:
    api_key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip().strip('"').strip("'")
    if not api_key:
        raise ValueError(
            '未设置 DEEPSEEK_API_KEY。请执行：export DEEPSEEK_API_KEY="sk-你的真实密钥"'
        )
    try:
        api_key.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError(
            "DEEPSEEK_API_KEY 含有非 ASCII 字符。"
            "请到 https://platform.deepseek.com/api_keys 复制以 sk- 开头的密钥。"
        ) from None
    if not api_key.startswith("sk-"):
        preview = api_key[:12] + "..." if len(api_key) > 12 else api_key
        raise ValueError(
            f"DEEPSEEK_API_KEY 格式不对（应以 sk- 开头，当前: {preview}）。"
        )
    return api_key


def deepseek_client() -> OpenAI:
    return OpenAI(api_key=load_deepseek_api_key(), base_url="https://api.deepseek.com")


def format_deepseek_api_error(err: APIError) -> str:
    status = getattr(err, "status_code", None)
    body = str(err).lower()
    if status == 402 or "insufficient balance" in body:
        return (
            "账户余额不足（402 Insufficient Balance）。"
            "请到 https://platform.deepseek.com 充值后再试。"
        )
    if status == 401:
        return "API Key 无效或已过期，请到 DeepSeek 控制台重新创建密钥。"
    return str(err)


def chat_completion(prompt: str, max_tokens: int = 800, temperature: float = 0.65) -> str:
    client = deepseek_client()
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("DeepSeek 返回了空内容")
    return content.strip()


def configure_stdio_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
