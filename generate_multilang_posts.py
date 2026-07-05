"""
沙田天气 · 多语言帖文（普通话 / English / Urdu）

数据抓取：
  - 沙田自动气象站：shatin_weather.py
  - 天文台全港概况：hko_overview.py

每种语言单独模块撰写，各输出一个文件（三平台通用）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Tuple
from zoneinfo import ZoneInfo

from deepseek_utils import configure_stdio_utf8, has_deepseek_api_key
from hko_overview import get_hko_overview, print_overview, summarize_overview
from multilang_post_en import generate_english_post
from multilang_post_ur import generate_urdu_post
from multilang_post_zh import generate_mandarin_post
from shatin_culture import fetch_culture_context
from shatin_events import fetch_shatin_events
from shatin_weather import analyze_weather, get_shatin_weather, print_weather, weather_fingerprint

configure_stdio_utf8()

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
DATA_DIR = SCRIPT_DIR / "data"
STATE_FILE = DATA_DIR / "multilang_state.json"
HK_TZ = ZoneInfo("Asia/Hong_Kong")

LANG_SPECS: Tuple[Tuple[str, str, Callable[..., str]], ...] = (
    ("zh", "普通话", generate_mandarin_post),
    ("en", "English", generate_english_post),
    ("ur", "اردو", generate_urdu_post),
)


def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_hashes": {}}


def _save_state(state: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def _fetch_overview_for_lang(code: str) -> Dict[str, Any]:
    """普通话用简体概况，英/乌尔都语用英文概况。"""
    if code == "zh":
        try:
            return get_hko_overview(lang="sc")
        except Exception:
            return get_hko_overview(lang="tc")
    return get_hko_overview(lang="en")


def main() -> int:
    print("正在拉取天气数据（多语言帖文）…")
    print("  · 沙田自动气象站（分区 CSV + rhrread）")
    print("  · 全港概况（rhrread + flw + warnsum）")
    print("  · 沙田活动（文化博物馆 / 沙田大会堂 / 康文署节目表）\n")

    try:
        weather = get_shatin_weather()
        overview_display = get_hko_overview(lang="tc")
    except Exception as e:
        print(f"❌ 天气数据获取失败: {e}", file=sys.stderr)
        return 1

    print_weather(weather)
    print_overview(overview_display)
    shatin_analysis = analyze_weather(weather)
    print(f"📊 沙田：{shatin_analysis['briefing']}\n")

    if not has_deepseek_api_key():
        print("⚠️  未设置 DEEPSEEK_API_KEY，使用各语言本地模板\n")

    events = fetch_shatin_events()
    if not events.get("skipped"):
        n = sum(len(events.get(k) or []) for k in ("today", "week", "month", "notices"))
        print(f"📅 沙田活动：抓取到 {n} 条官方信息\n")

    culture = fetch_culture_context(weather, overview_display)
    if not culture.get("skipped"):
        print(f"📜 沙田文史：已载入 {len(culture.get('snippets') or [])} 条当月素材\n")

    state = _load_state()
    stamp = datetime.now(HK_TZ).strftime("%Y-%m-%d_%H%M")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    saved: Dict[str, str] = {}

    for code, label, generator in LANG_SPECS:
        print(f"🤖 正在生成 {label} 帖文…")
        try:
            overview = _fetch_overview_for_lang(code)
            overview_analysis = summarize_overview(overview)
            content = generator(
                weather, overview, shatin_analysis, overview_analysis, events, culture
            )
            path = OUTPUT_DIR / f"post_{stamp}_{code}.txt"
            path.write_text(content, encoding="utf-8")
            state.setdefault("last_hashes", {})[code] = _content_hash(content)
            saved[code] = path.name
            print(f"✅ 已保存: output/{path.name}\n")
            print(f"--- {label} ---\n{content}\n")
        except Exception as e:
            print(f"❌ {label}: {e}", file=sys.stderr)

    _save_state(state)

    manifest = {
        "generated_at_hkt": datetime.now(HK_TZ).isoformat(),
        "languages": [c for c, _, _ in LANG_SPECS],
        "files": saved,
        "weather_fingerprint": weather_fingerprint(weather),
        "stamp": stamp,
    }
    (OUTPUT_DIR / "latest_multilang_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if not saved:
        return 1
    print(f"🎉 已生成 {len(saved)} 篇多语言帖文（每种语言 1 个文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
