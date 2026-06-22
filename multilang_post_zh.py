"""普通话帖文（三平台通用，一篇）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from deepseek_utils import chat_completion, has_deepseek_api_key
from multilang_common import (
    CULTURAL_POLICY,
    default_hashtags,
    format_overview_block,
    format_shatin_facts,
    pick_advice,
    run_context,
    source_line,
)
from shatin_events import append_events_section, format_events_facts, fetch_shatin_events

HK_TZ = ZoneInfo("Asia/Hong_Kong")
LANG = "zh"


def build_prompt(
    weather: Dict[str, Any],
    shatin_analysis: Dict[str, Any],
    overview: Dict[str, Any],
    overview_analysis: Dict[str, Any],
    hashtag_line: str,
    events: Optional[Dict[str, Any]] = None,
) -> str:
    events_block = format_events_facts(events, LANG) if events else ""
    events_rule = ""
    if events_block:
        events_rule = f"""
8. 若上方有沙田活动资料，在天气内容后增加【沙田活动】板块（1–3 条），勿编造未列出的节目
{events_block}"""
    return f"""你是香港天文台对外传播撰稿人。请用**普通话（简体字）**撰写一篇社交帖文，
适用于小红书、Instagram、Facebook（三平台正文相同）。

{run_context(weather, LANG)}

{format_overview_block(overview, LANG)}

{format_shatin_facts(weather, LANG)}

【沙田分析】{shatin_analysis['briefing']}
【全港分析】{overview_analysis['briefing']}

【格式要求】
1. 约 100–180 字（不含 hashtag）；语气正式、清晰，类似气象部门发布
2. 结构建议：标题行（含 emoji + 沙田即时天气 + 日期）→ 全港概况要点 → 沙田站具体数字 → 一句实用提示
3. 必须使用简体字
4. 末行 hashtag（须包含）：{hashtag_line}
5. 倒数第二行注明：{source_line(LANG)}
6. 只根据上述数据；勿编造预警
7. 只输出可直接发布的正文{events_rule}

{CULTURAL_POLICY}"""


def validate_post(content: str, hashtag_line: str) -> str:
    text = (content or "").strip()
    if len(text) < 60:
        raise ValueError(f"帖文过短（{len(text)} 字）")
    if "#沙田天气" not in text:
        raise ValueError("须包含 #沙田天气")
    for tag in hashtag_line.split():
        if tag.startswith("#") and tag not in text:
            text = text.rstrip() + "\n\n" + " ".join(
                t for t in hashtag_line.split() if t not in text
            )
            break
    return text


def template_post(
    weather: Dict[str, Any],
    shatin_analysis: Dict[str, Any],
    overview: Dict[str, Any],
    overview_analysis: Dict[str, Any],
    hashtag_line: str,
    events: Optional[Dict[str, Any]] = None,
) -> str:
    now = datetime.now(HK_TZ)
    date_str = now.strftime("%Y年%m月%d日")
    t, rh = weather["air_temperature"], weather["relative_humidity"]
    rain, ws = weather["total_rainfall"], weather["wind_speed"]
    wd = weather["wind_direction"]
    wd_zh = wd if str(wd).endswith("风") else f"{wd}风"
    gust = weather.get("wind_gust", "—")
    hq = overview["hko_hq"]

    emoji = "🌧️" if float(rain) > 0 or overview.get("warnings") else "🌤️"
    warning = overview_analysis["warning_text"]
    warning_line = (
        f"⚠️ {warning}" if warning != "目前無特別警告" else "目前无特别天气警告。"
    )
    forecast = (overview.get("forecast_desc") or "")[:55]
    if len(overview.get("forecast_desc") or "") > 55:
        forecast += "…"

    advice = pick_advice(weather, shatin_analysis, overview_analysis, LANG, overview)

    body = (
        f"{emoji} 沙田即时天气｜{date_str}\n\n"
        f"【全港】天文台总部 {hq.get('temperature', '—')}°C，湿度 {hq.get('humidity', '—')}%\n"
        f"{warning_line}\n"
        f"{forecast}\n\n"
        f"【沙田】自动气象站实况\n"
        f"气温 {t}°C｜湿度 {rh}%｜过去一小时雨量 {rain} mm\n"
        f"{wd_zh} {ws} km/h｜阵风 {gust} km/h\n\n"
        f"【提示】{advice}\n\n"
        f"{source_line(LANG)}\n\n"
        f"{hashtag_line}"
    )
    if events:
        body = append_events_section(body, events, LANG)
    return validate_post(body, hashtag_line)


def generate_mandarin_post(
    weather: Dict[str, Any],
    overview: Dict[str, Any],
    shatin_analysis: Optional[Dict[str, Any]] = None,
    overview_analysis: Optional[Dict[str, Any]] = None,
    events: Optional[Dict[str, Any]] = None,
) -> str:
    from hko_overview import summarize_overview
    from shatin_weather import analyze_weather

    shatin_analysis = shatin_analysis or analyze_weather(weather)
    overview_analysis = overview_analysis or summarize_overview(overview)
    events = events if events is not None else fetch_shatin_events()
    hashtag_line = default_hashtags(LANG, overview)
    prompt = build_prompt(
        weather, shatin_analysis, overview, overview_analysis, hashtag_line, events
    )

    if has_deepseek_api_key():
        from openai import APIConnectionError, APIError, RateLimitError

        for attempt in range(2):
            try:
                extra = (
                    "\n【重试】请更换开场句式，保持简体普通话。"
                    if attempt == 1
                    else ""
                )
                text = validate_post(
                    chat_completion(prompt + extra, max_tokens=520, temperature=0.8),
                    hashtag_line,
                )
                if events:
                    text = append_events_section(text, events, LANG)
                return text
            except (ValueError, APIError, APIConnectionError, RateLimitError):
                if attempt == 1:
                    break

    return template_post(
        weather, shatin_analysis, overview, overview_analysis, hashtag_line, events
    )
