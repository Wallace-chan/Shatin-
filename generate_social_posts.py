"""
沙田天气 · 社交三平台统一帖文

拉取沙田自动气象站实况 + 香港天文台全港概况（与官网同源开放数据），
生成适用于 小红书 / Instagram / Facebook 的同一篇带 hashtag 帖文。

数据源：
  - 沙田站：shatin_weather.py
  - 全港概况：hko_overview.py（对应 https://www.hko.gov.hk/en/index.html 展示内容）
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from openai import APIConnectionError, APIError, RateLimitError

from deepseek_utils import (
    chat_completion,
    configure_stdio_utf8,
    format_deepseek_api_error,
    has_deepseek_api_key,
)
from hko_overview import (
    format_overview_facts,
    get_hko_overview,
    print_overview,
    summarize_overview,
)
from shatin_weather import (
    analyze_weather,
    format_weather_facts,
    get_shatin_weather,
    print_weather,
    weather_fingerprint,
)

configure_stdio_utf8()

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
DATA_DIR = SCRIPT_DIR / "data"
STATE_FILE = DATA_DIR / "social_state.json"
HK_TZ = ZoneInfo("Asia/Hong_Kong")

PLATFORMS = ("xiaohongshu", "instagram", "facebook")
PLATFORM_LABELS = {
    "xiaohongshu": "小红书",
    "instagram": "Instagram",
    "facebook": "Facebook",
}

DEFAULT_HASHTAGS = (
    "#沙田天氣 #香港天氣 #香港天文台 #即時天氣 #分區天氣"
)


def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_hash": None}


def _save_state(state: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def _run_context(weather: Dict[str, Any], overview: Dict[str, Any]) -> str:
    now = datetime.now(HK_TZ)
    weekdays = "星期一星期二星期三星期四星期五星期六星期日"
    weekday = weekdays[now.weekday()]
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    fp = weather_fingerprint(weather)
    warning_count = len(overview.get("warnings", []))
    return f"""【本次發佈上下文】
- 香港時間：{now:%Y年%m月%d日}（{weekday}）{now:%H:%M}
- 運行編號：{run_id}
- 沙田觀測指紋：{fp}
- 生效警告數：{warning_count}
- 要求：開場點出今日；綜合全港與沙田；勿與往日完全相同的開場白"""


def _build_hashtag_line(
    overview: Dict[str, Any], shatin_analysis: Dict[str, Any]
) -> str:
    extra: List[str] = []
    for w in overview.get("warnings", []):
        label = w["label"]
        if "暴雨" in label:
            extra.append("#暴雨警告")
        elif "雷暴" in label:
            extra.append("#雷暴警告")
        elif "酷熱" in label:
            extra.append("#酷熱天氣")
    if shatin_analysis.get("tags") and any("降雨" in t or "雨量" in t for t in shatin_analysis["tags"]):
        extra.append("#有雨提醒")
    # 三平台通用标签
    base = list(DEFAULT_HASHTAGS.split())
    for tag in extra:
        if tag not in base:
            base.append(tag)
    base.extend(["#小紅書天氣", "#天氣日記"])
    # 去重保序
    seen = set()
    ordered = []
    for tag in base:
        if tag not in seen:
            seen.add(tag)
            ordered.append(tag)
    return " ".join(ordered[:10])


def _build_prompt(
    weather: Dict[str, Any],
    shatin_analysis: Dict[str, Any],
    overview: Dict[str, Any],
    overview_analysis: Dict[str, Any],
    hashtag_line: str,
) -> str:
    shatin_facts = format_weather_facts(weather)
    hk_facts = format_overview_facts(overview)
    ctx = _run_context(weather, overview)

    return f"""你係香港沙田區天氣內容編輯。根據天文台即時數據撰寫**一篇**社交帖文，
同時用於小紅書、Instagram、Facebook（三平台正文完全相同，含 hashtag）。

{ctx}

{hk_facts}

{shatin_facts}

【沙田分析】
{shatin_analysis['briefing']}

【全港分析】
{overview_analysis['briefing']}

【格式要求】
1. **繁體中文書寫、粵語口語**（用「而家」「記得」「帶遮」等），親切但資訊準確，約 120–200 字（不含 hashtag）
2. 結構建議：
   - 標題行含 emoji（如 🌧️ 或 🌤️）+「沙田即時天氣｜日期」
   - 【本港】簡述天文台總部氣溫/濕度、生效警告、今晚明日天氣要點（1–2 句）
   - 【沙田】沙田自動氣象站具體數字（氣溫、濕度、雨量、風向風速）
   - 【提示】1 句實用建議（有雨/雷暴/悶熱時須對應提醒）
3. 末行 hashtag（必須原樣包含，可微調順序但不可刪除核心標籤）：
{hashtag_line}
4. 只根據上述數據；勿編造未給出嘅預報
5. 只輸出可直接發佈嘅正文，不要「好的」「以下是」"""


def _validate(content: str, hashtag_line: str) -> str:
    text = (content or "").strip()
    if len(text) < 80:
        raise ValueError(f"帖文过短（{len(text)} 字）")
    if "#沙田天氣" not in text and "#沙田天气" not in text:
        raise ValueError("須包含 #沙田天氣")
    if "#香港天文台" not in text:
        raise ValueError("須包含 #香港天文台")
    # 若 AI 漏了部分标签，在文末补上
    for tag in hashtag_line.split():
        if tag.startswith("#") and tag not in text:
            text = text.rstrip() + "\n\n" + " ".join(
                t for t in hashtag_line.split() if t not in text
            )
            break
    return text


def _template_content(
    weather: Dict[str, Any],
    shatin_analysis: Dict[str, Any],
    overview: Dict[str, Any],
    overview_analysis: Dict[str, Any],
    hashtag_line: str,
) -> str:
    now = datetime.now(HK_TZ)
    date_str = now.strftime("%Y年%m月%d日")
    t, rh = weather["air_temperature"], weather["relative_humidity"]
    rain, wind = weather["total_rainfall"], weather["wind_speed"]
    direction = weather["wind_direction"]
    gust = weather.get("wind_gust", "—")

    hq = overview["hko_hq"]
    warning_line = overview_analysis["warning_text"]
    if warning_line != "目前無特別警告":
        warning_line = f"⚠️ {warning_line}"

    emoji = "🌧️" if overview.get("warnings") or float(rain) > 0 else "🌤️"
    forecast_short = (overview.get("forecast_desc") or "")[:60]
    if len(overview.get("forecast_desc") or "") > 60:
        forecast_short += "…"

    advice_parts = shatin_analysis.get("advice", []) + overview_analysis.get("advice", [])
    advice = advice_parts[0] if advice_parts else (
        "天氣悶熱，記得飲水 💧" if float(t) >= 28 else "出門留意天氣變化"
    )

    body = (
        f"{emoji} 沙田即時天氣｜{date_str}\n\n"
        f"【本港】天文台 {hq.get('temperature', '—')}°C｜濕度 {hq.get('humidity', '—')}%\n"
        f"{warning_line}\n"
        f"{forecast_short}\n\n"
        f"【沙田】自動氣象站實況\n"
        f"氣溫 {t}°C｜濕度 {rh}%｜過去一個鐘雨量 {rain} mm\n"
        f"{direction}風 {wind} km/h｜陣風 {gust} km/h\n\n"
        f"【提示】{advice}\n\n"
        f"{hashtag_line}"
    )
    return _validate(body, hashtag_line)


def generate_unified_post(
    weather: Dict[str, Any],
    shatin_analysis: Dict[str, Any],
    overview: Dict[str, Any],
    overview_analysis: Dict[str, Any],
    state: Dict[str, Any],
) -> str:
    hashtag_line = _build_hashtag_line(overview, shatin_analysis)
    prompt = _build_prompt(
        weather, shatin_analysis, overview, overview_analysis, hashtag_line
    )

    if has_deepseek_api_key():
        for attempt in range(2):
            try:
                text = _validate(
                    chat_completion(
                        prompt
                        + (
                            "\n【重試】請換開場同句式，勿與常見範本相同。"
                            if attempt == 1
                            else ""
                        ),
                        max_tokens=550,
                        temperature=0.82 + (0.1 * attempt),
                    ),
                    hashtag_line,
                )
                return text
            except (ValueError, APIError, APIConnectionError, RateLimitError) as e:
                if attempt == 1:
                    if isinstance(e, APIError):
                        print(
                            f"⚠️ DeepSeek: {format_deepseek_api_error(e)}，改用模板",
                            file=sys.stderr,
                        )
                    else:
                        print(f"⚠️ {e}，改用模板", file=sys.stderr)
                    break
    return _template_content(
        weather, shatin_analysis, overview, overview_analysis, hashtag_line
    )


def _save_outputs(content: str, stamp: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "unified": OUTPUT_DIR / f"post_{stamp}_social_unified.txt",
    }
    for platform in PLATFORMS:
        paths[platform] = OUTPUT_DIR / f"post_{stamp}_{platform}.txt"

    for key, path in paths.items():
        path.write_text(content, encoding="utf-8")
        label = PLATFORM_LABELS.get(key, "统一帖文")
        if key == "unified":
            label = "三平台统一帖文"
        print(f"✅ 已保存: output/{path.name}  ({label})")


def main() -> int:
    print("正在拉取天气数据…")
    print("  · 沙田自动气象站（分区 CSV + rhrread）")
    print("  · 全港概况（rhrread + flw + warnsum，同源 HKO 官网）\n")

    try:
        weather = get_shatin_weather()
        overview = get_hko_overview(lang="tc")
    except Exception as e:
        print(f"❌ 天气数据获取失败: {e}", file=sys.stderr)
        return 1

    print_weather(weather)
    print_overview(overview)

    shatin_analysis = analyze_weather(weather)
    overview_analysis = summarize_overview(overview)
    print(f"📊 沙田：{shatin_analysis['briefing']}\n")
    print(f"📊 全港：{overview_analysis['briefing']}\n")

    if not has_deepseek_api_key():
        print("⚠️  未设置 DEEPSEEK_API_KEY，使用本地模板生成\n")

    state = _load_state()
    stamp = datetime.now(HK_TZ).strftime("%Y-%m-%d_%H%M")

    print("🤖 正在生成 小红书 / Instagram / Facebook 统一帖文…")
    content = generate_unified_post(
        weather, shatin_analysis, overview, overview_analysis, state
    )

    h = _content_hash(content)
    if state.get("last_hash") == h:
        print("⚠️  与上次生成内容 hash 相同", file=sys.stderr)

    _save_outputs(content, stamp)
    state["last_hash"] = h
    _save_state(state)

    manifest = {
        "generated_at_hkt": datetime.now(HK_TZ).isoformat(),
        "platforms": list(PLATFORMS),
        "unified": True,
        "weather_fingerprint": weather_fingerprint(weather),
        "warnings": [w["label"] for w in overview.get("warnings", [])],
        "stamp": stamp,
        "hko_source": "https://www.hko.gov.hk/tc/index.html",
    }
    (OUTPUT_DIR / "latest_social_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\n--- 统一帖文（{PLATFORM_LABELS['xiaohongshu']} / "
          f"{PLATFORM_LABELS['instagram']} / {PLATFORM_LABELS['facebook']}）---\n")
    print(content)
    print(f"\n🎉 已生成 1 篇统一帖文，并保存为 {len(PLATFORMS) + 1} 个文件（内容相同）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
