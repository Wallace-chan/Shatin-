"""DeepSeek 兼容层：保留旧代码所需的函数名，默认不接 API，始终走本地模板。

GitHub 上其他 .py 仍可 `from deepseek_utils import ...`，无需逐个改文件。
未设置有效密钥时不会发起任何网络请求，不产生费用。
"""

from __future__ import annotations

import os
import sys


def configure_stdio_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")


def has_deepseek_api_key() -> bool:
    """返回 False → 各程序跳过 AI，直接用本地模板。"""
    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip().strip('"').strip("'")
    if not key.startswith("sk-"):
        return False
    # 即使 Secrets 里仍有旧密钥，也默认不接 API（Wallace 要求纯本地）
    return False


def load_deepseek_api_key() -> str:
    raise ValueError("DeepSeek API 已停用，程序使用本地模板生成帖文。")


def format_deepseek_api_error(err: BaseException) -> str:
    return str(err)


def chat_completion(prompt: str, max_tokens: int = 800, temperature: float = 0.65) -> str:
    raise RuntimeError("DeepSeek API 已停用，程序使用本地模板生成帖文。")
