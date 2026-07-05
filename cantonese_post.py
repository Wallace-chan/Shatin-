"""口语化粤语帖文：沙田站 + 天文台全港概况 → 社交帖正文。"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from deepseek_utils import chat_completion, has_deepseek_api_key
from hko_overview import format_overview_facts, summarize_overview
from shatin_culture import append_culture_section, format_culture_facts, fetch_culture_context
from shatin_events import append_events_section, format_events_facts, fetch_shatin_events
from shatin_weather import analyze_weather, format_weather_facts, weather_fingerprint

HK_TZ = ZoneInfo("Asia/Hong_Kong")

DEFAULT_HASHTAGS = "#沙田天氣 #香港天氣 #粵語日常 #香港天文台 #即時天氣"

SAMPLE_COLOQUIAL = """各位沙田街坊，午安呀 ☀️

而家沙田大概 26 度，濕度有八成几，风唔算大。天文台话今晚同听日大致天晴，不过好焗，记得补水呀 💧

#沙田天氣 #香港天氣 #粵語日常"""


def time_greeting() -> str:
    hour = datetime.now(HK_TZ).hour
    if hour < 6:
        return "凌晨好呀"
    if hour < 12:
        return "早晨呀"
    if hour < 14:
        return "午安呀"
    if hour < 18:
        return "下午好呀"
    return "晚上好呀"


def _pick_opening(seed: str) -> str:
    options = (
        "各位沙田街坊，{greeting}",
        "沙田街坊留意呀，{greeting}",
        "喂街坊，{greeting}",
        "喺沙田嘅朋友，{greeting}",
    )
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(options)
    return options[idx].format(greeting=time_greeting())


def _colloquial_warning_line(overview_analysis: Dict[str, Any]) -> str:
    text = overview_analysis.get("warning_text", "")
    if not text or text == "目前無特別警告":
        return "暫時冇特別天氣警告。"
    if "酷熱" in text:
        return f"天文台掛咗{text}，真係好焗，唔好中暑呀。"
    if "暴雨" in text or "雷暴" in text:
        return f"天文台有{text}，出街記得帶遮，留意路面同雷電呀。"
    return f"天文台而家有{text}，出門記得睇多兩眼天氣。"


def _colloquial_forecast_line(overview: Dict[str, Any]) -> str:
    desc = (overview.get("forecast_desc") or "").strip()
    if not desc:
        return ""
    short = desc if len(desc) <= 55 else desc[:52] + "…"
    return f"全港預報大概係：{short}"


def _colloquial_shatin_weather_line(weather: Dict[str, Any]) -> str:
    t = weather["air_temperature"]
    rh = weather["relative_humidity"]
    rain = float(weather["total_rainfall"])
    wind = weather["wind_speed"]
    direction = weather["wind_direction"]
    gust = weather.get("wind_gust")
    wind_label = direction if str(direction).endswith("風") else f"{direction}風"

    if rain > 5:
        rain_bit = f"過去一個鐘落咗 {rain:g} mm 雨，路面濕滑"
    elif rain > 0:
        rain_bit = f"過去一個鐘有 {rain:g} mm 雨"
    else:
        rain_bit = "過去一個鐘雨唔多"

    gust_bit = f"，陣風去到 {gust} km/h" if gust is not None else ""
    return (
        f"沙田自動氣象站而家大概 {t}°C，濕度 {rh}%，"
        f"{rain_bit}，吹緊{wind_label} {wind} km/h{gust_bit}。"
    )


def _colloquial_advice(
    weather: Dict[str, Any],
    shatin_analysis: Dict[str, Any],
    overview_analysis: Dict[str, Any],
) -> str:
    tips: List[str] = []
    for a in overview_analysis.get("advice", []) + shatin_analysis.get("advice", []):
        colloquial = a.replace("戶外活動宜攜帶雨具", "出街帶定遮呀 ☔")
        colloquial = colloquial.replace(
            "悶熱天氣下應適量補充水分、注意防暑", "好焗，記得多飲水、唔好中暑 💧"
        )
        colloquial = colloquial.replace("注意防暑補水", "記得补水防暑呀")
        if colloquial not in tips:
            tips.append(colloquial)

    rain = float(weather["total_rainfall"])
    temp = float(weather["air_temperature"])
    rh = int(weather["relative_humidity"])

    if not tips:
        if rain > 0:
            tips.append("有雨就帶遮，小心地滑呀 ☔")
        elif temp >= 30 or rh >= 85:
            tips.append("天氣焗，行街記得飲水 💧")
        else:
            tips.append("出門舒服，不過都係睇住天文台最新消息呀。")

    return tips[0]


def build_hashtag_line(
    overview: Dict[str, Any], shatin_analysis: Dict[str, Any]
) -> str:
    extra: List[str] = []
    for w in overview.get("warnings", []):
        label = w["label"]
        if "暴雨" in label and "#暴雨警告" not in extra:
            extra.append("#暴雨警告")
        elif "雷暴" in label and "#雷暴警告" not in extra:
            extra.append("#雷暴警告")
        elif "酷熱" in label and "#酷熱天氣" not in extra:
            extra.append("#酷熱天氣")
    rain = float(shatin_analysis.get("_rain_mm", 0))
    if rain > 0:
        extra.append("#有雨提醒")
    tags = DEFAULT_HASHTAGS.split()
    for tag in extra:
        if tag not in tags:
            tags.append(tag)
    return " ".join(tags[:10])


def _run_context(weather: Dict[str, Any], overview: Dict[str, Any]) -> str:
    now = datetime.now(HK_TZ)
    weekdays = "星期一星期二星期三星期四星期五星期六星期日"
    weekday = weekdays[now.weekday()]
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    return f"""【本次發佈上下文】
- 香港時間：{now:%Y年%m月%d日}（{weekday}）{now:%H:%M}
- 運行編號：{run_id}
- 沙田觀測指紋：{weather_fingerprint(weather)}
- 生效警告數：{len(overview.get('warnings', []))}
- 要求：口語自然；開場有變化；唔好日日同一句"""


def build_colloquial_prompt(
    weather: Dict[str, Any],
    shatin_analysis: Dict[str, Any],
    overview: Dict[str, Any],
    overview_analysis: Dict[str, Any],
    hashtag_line: str,
    events: Optional[Dict[str, Any]] = None,
    culture: Optional[Dict[str, Any]] = None,
) -> str:
    events_block = format_events_facts(events, "tc") if events else ""
    culture_block = format_culture_facts(culture, "tc") if culture else ""
    events_hint = ""
    if events_block:
        events_hint = f"""
{events_block}

8. 若上面有沙田活動資料，用 1–2 句口語順帶提及（唔好用【沙田活動】標題；可講「想行文化博物館」等），勿編造未列出嘅節目"""
    culture_hint = ""
    if culture_block:
        culture_hint = f"""
{culture_block}

9. 若上面有沙田文史／月令資料，可自然穿插 1 句（如當月古書月令、余光中筆下山水意象），唔好用【沙田文史】標題；詳細板塊會另附"""
    return f"""你係香港沙田區天氣博主，用**粵語口語**寫一篇社交帖（小紅書 / Instagram / Facebook 共用）。

{ _run_context(weather, overview) }

{format_overview_facts(overview)}

{format_weather_facts(weather)}

【沙田分析】{shatin_analysis['briefing']}
【全港分析】{overview_analysis['briefing']}
{events_block}

【語氣參考（唔好照抄數字）】
{SAMPLE_COLOQUIAL}

【寫法要求】
1. **繁體字 + 粵語口語**：用「而家」「咁」「記得」「帶遮」「好焗」「街坊」等，唔好用書面語套話
2. **唔好用**【本港】【沙田】【提示】呢啲標題分段；改為自然聊天段落，2–4 段即可
3. 必須講清：沙田站氣溫、濕度、雨量、風向風速；再加一句全港預報或警告（如有）
4. 約 100–180 字（唔計 hashtag）；可加 2–3 個 emoji
5. 數字只可以用上面提供嘅，唔好亂估
6. 末行原樣包含 hashtag：{hashtag_line}
7. 只輸出可直接發佈正文，唔好「好的」「以下係」{events_hint}{culture_hint}"""


def validate_colloquial_post(content: str, hashtag_line: str) -> str:
    text = (content or "").strip()
    if len(text) < 60:
        raise ValueError(f"帖文过短（{len(text)} 字）")
    if "#沙田天氣" not in text and "#沙田天气" not in text:
        raise ValueError("須包含 #沙田天氣")
    if "【本港】" in text and "【沙田】" in text:
        raise ValueError("口語帖唔好用【本港】【沙田】標題格式，請改為自然段落")
    for tag in hashtag_line.split():
        if tag.startswith("#") and tag not in text:
            text = text.rstrip() + "\n\n" + " ".join(
                t for t in hashtag_line.split() if t not in text
            )
            break
    return text


def _weather_emoji(weather: Dict[str, Any], overview: Dict[str, Any]) -> str:
    if float(weather["total_rainfall"]) > 0:
        return "🌧️"
    for w in overview.get("warnings", []):
        label = w["label"]
        if "暴雨" in label or "雷暴" in label:
            return "🌧️"
        if "酷熱" in label:
            return "☀️"
    return "🌤️"


def template_colloquial_post(
    weather: Dict[str, Any],
    shatin_analysis: Dict[str, Any],
    overview: Dict[str, Any],
    overview_analysis: Dict[str, Any],
    hashtag_line: str,
    events: Optional[Dict[str, Any]] = None,
    culture: Optional[Dict[str, Any]] = None,
) -> str:
    """无 API Key 时的口语粤语模板。"""
    now = datetime.now(HK_TZ)
    date_str = now.strftime("%Y年%m月%d日")
    seed = weather_fingerprint(weather) + now.strftime("%Y%m%d%H")
    opening = _pick_opening(seed)

    emoji = _weather_emoji(weather, overview)
    hq = overview["hko_hq"]
    hq_line = (
        f"天文台總部大概 {hq.get('temperature', '—')}°C，"
        f"濕度 {hq.get('humidity', '—')}% 左右。"
    )

    body = (
        f"{opening} {emoji}\n\n"
        f"{_colloquial_shatin_weather_line(weather)}\n\n"
        f"{hq_line}{_colloquial_warning_line(overview_analysis)}"
    )
    forecast = _colloquial_forecast_line(overview)
    if forecast:
        body += f"\n{forecast}"

    advice = _colloquial_advice(weather, shatin_analysis, overview_analysis)
    body += f"\n\n{advice}\n\n{hashtag_line}"
    if events:
        body = append_events_section(body, events, "tc")
    if culture:
        body = append_culture_section(body, culture, "tc")
    return validate_colloquial_post(body, hashtag_line)


def generate_colloquial_post(
    weather: Dict[str, Any],
    overview: Dict[str, Any],
    shatin_analysis: Optional[Dict[str, Any]] = None,
    overview_analysis: Optional[Dict[str, Any]] = None,
    events: Optional[Dict[str, Any]] = None,
    culture: Optional[Dict[str, Any]] = None,
) -> str:
    """生成一篇口语化粤语社交帖文。"""
    shatin_analysis = shatin_analysis or analyze_weather(weather)
    shatin_analysis = {**shatin_analysis, "_rain_mm": float(weather["total_rainfall"])}
    overview_analysis = overview_analysis or summarize_overview(overview)
    events = events if events is not None else fetch_shatin_events()
    culture = culture if culture is not None else fetch_culture_context(weather, overview)
    hashtag_line = build_hashtag_line(overview, shatin_analysis)
    prompt = build_colloquial_prompt(
        weather, shatin_analysis, overview, overview_analysis, hashtag_line, events, culture
    )

    if has_deepseek_api_key():
        from openai import APIConnectionError, APIError, RateLimitError

        for attempt in range(2):
            try:
                extra = (
                    "\n【重試】請換開場同句式，保持粵語口語，唔好用【本港】【沙田】標題。"
                    if attempt == 1
                    else ""
                )
                text = validate_colloquial_post(
                    chat_completion(
                        prompt + extra,
                        max_tokens=520,
                        temperature=0.85 + (0.1 * attempt),
                    ),
                    hashtag_line,
                )
                if events:
                    text = append_events_section(text, events, "tc")
                if culture:
                    text = append_culture_section(text, culture, "tc")
                return text
            except (ValueError, APIError, APIConnectionError, RateLimitError):
                if attempt == 1:
                    break

    text = template_colloquial_post(
        weather, shatin_analysis, overview, overview_analysis, hashtag_line, events, culture
    )
    return text
