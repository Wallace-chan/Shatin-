"""اردو帖文（三平台通用，一篇）。"""

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
    wind_label,
)
from shatin_events import append_events_section, format_events_facts, fetch_shatin_events

HK_TZ = ZoneInfo("Asia/Hong_Kong")
LANG = "ur"


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
7. اگر نیچے شا ٹن سرگرمیاں درج ہیں تو موسم کے بعد 【شا ٹن سرگرمیاں】 بلاک شامل کریں
{events_block}"""
    return f"""آپ ہانگ کانگ رصدگاہ کے مواصلاتی مصنف ہیں۔ **اردو** میں **ایک** سوشل میڈیا پوسٹ لکھیں
(小红书 / Instagram / Facebook — ایک ہی متن)۔

{run_context(weather, LANG)}

{format_overview_block(overview, LANG)}

{format_shatin_facts(weather, LANG)}

【تجزیہ · شا ٹن】{shatin_analysis['briefing']}
【تجزیہ · علاقہ】{overview_analysis['briefing']}

【ہدایات】
1. تقریباً 100–180 الفاظ (ہیش ٹیگ کے بغیر)；سرکاری، واضح لہجہ
2. ڈھانچہ: عنوان (emoji + شا ٹن موسم + تاریخ) → علاقائی خلاصہ → شا ٹن اعداد → ایک عملی نصیحت
3. آخری سطر hashtag: {hashtag_line}
4. ماخذ: {source_line(LANG)}
5. صرف دیے گئے اعداد استعمال کریں
6. صرف شائع ہونے والا متن لکھیں{events_rule}

{CULTURAL_POLICY}"""


def validate_post(content: str, hashtag_line: str) -> str:
    text = (content or "").strip()
    if len(text) < 50:
        raise ValueError(f"Post too short ({len(text)} chars)")
    if "#شاٹنموسم" not in text:
        raise ValueError("Must include #شاٹنموسم")
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
    date_str = now.strftime("%d %B %Y")
    t, rh = weather["air_temperature"], weather["relative_humidity"]
    rain, ws = weather["total_rainfall"], weather["wind_speed"]
    wd = wind_label(weather["wind_direction"], LANG)
    gust = weather.get("wind_gust", "—")
    hq = overview["hko_hq"]

    emoji = "🌧️" if float(rain) > 0 or overview.get("warnings") else "🌤️"
    warning = overview_analysis["warning_text"]
    warning_line = (
        f"⚠️ انتباہ: {warning}"
        if warning != "目前無特別警告"
        else "فی الحال کوئی خاص موسمی انتباہ نہیں۔"
    )
    forecast = (overview.get("forecast_desc") or "")[:60]

    advice = pick_advice(weather, shatin_analysis, overview_analysis, LANG, overview)

    body = (
        f"{emoji} شا ٹن موسم · {date_str}\n\n"
        f"【علاقہ】HKO HQ {hq.get('temperature', '—')}°C، نمی {hq.get('humidity', '—')}%\n"
        f"{warning_line}\n"
        f"{forecast}\n\n"
        f"【شا ٹن】خودکار موسمی اسٹیشن\n"
        f"حرارت {t}°C | نمی {rh}% | بارش (1 گھنٹہ) {rain} mm\n"
        f"ہوا {wd} {ws} km/h | جھونکا {gust} km/h\n\n"
        f"【نصیحت】{advice}\n\n"
        f"{source_line(LANG)}\n\n"
        f"{hashtag_line}"
    )
    if events:
        body = append_events_section(body, events, LANG)
    return validate_post(body, hashtag_line)


def generate_urdu_post(
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
                    "\n【Retry】مختلف آغاز استعمال کریں؛ باضابطہ اردو رکھیں۔"
                    if attempt == 1
                    else ""
                )
                text = validate_post(
                    chat_completion(prompt + extra, max_tokens=560, temperature=0.8),
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
