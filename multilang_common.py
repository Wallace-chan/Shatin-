"""多语言帖文共用：沙田站 + 天文台全港数据格式化。"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from zoneinfo import ZoneInfo

from shatin_weather import weather_fingerprint

LangCode = Literal["zh", "en", "ur"]
HK_TZ = ZoneInfo("Asia/Hong_Kong")

CULTURAL_POLICY = """
【Content ethics — mandatory】
- Formal, neutral tone like a public weather service; no gossip or politics
- Respect Chinese, Islamic, and Hong Kong multicultural communities
- No discrimination, stereotypes, or unverified disaster claims
- Use only the supplied observations and forecasts
"""

_WIND_EN = {
    "北": "N", "南": "S", "東": "E", "东": "E", "西": "W",
    "東北": "NE", "东北": "NE", "東南": "SE", "东南": "SE",
    "西北": "NW", "西南": "SW", "偏東": "E", "偏西": "W",
}
_WIND_UR = {
    "北": "شمال", "南": "جنوب", "東": "مشرق", "东": "مشرق", "西": "مغرب",
    "東南": "جنوب مشرق", "东南": "جنوب مشرق", "西南": "جنوب مغرب", "西北": "شمال مغرب",
}


def wind_label(direction: str, lang: LangCode) -> str:
    if lang == "zh":
        return direction
    if lang == "en":
        return _WIND_EN.get(direction, direction)
    return _WIND_UR.get(direction, _WIND_EN.get(direction, direction))


def run_context(weather: Dict[str, Any], lang: LangCode) -> str:
    now = datetime.now(HK_TZ)
    labels = {"zh": "普通话", "en": "English", "ur": "اردو (Urdu)"}
    weekdays_zh = "一二三四五六日"
    wd = weekdays_zh[now.weekday()]
    return f"""【发布上下文】
- 语言：{labels[lang]}
- 香港时间：{now:%Y年%m月%d日} 星期{wd} {now:%H:%M}
- 运行编号：{os.environ.get('GITHUB_RUN_ID', 'local')}
- 沙田观测指纹：{weather_fingerprint(weather)}
- 须体现当前观测；开场勿与往日稿雷同"""


def format_shatin_facts(weather: Dict[str, Any], lang: LangCode) -> str:
    t = weather["air_temperature"]
    rh = weather["relative_humidity"]
    rain = weather["total_rainfall"]
    ws = weather["wind_speed"]
    wd_raw = weather["wind_direction"]
    wd = wind_label(wd_raw, lang)
    gust = weather.get("wind_gust", "—")
    rt = weather.get("record_time", "")

    if lang == "zh":
        wd_zh = wd_raw if str(wd_raw).endswith("风") else f"{wd_raw}风"
        return f"""【沙田自动气象站 · {rt}】
- 气温：{t}°C
- 相对湿度：{rh}%
- 过去一小时雨量：{rain} mm
- 风向风速：{wd_zh} {ws} km/h，阵风 {gust} km/h"""
    if lang == "ur":
        return f"""【شا ٹن خودکار موسمی اسٹیشن · {rt}】
- درجہ حرارت: {t}°C
- نمی: {rh}%
- گزشتہ ایک گھنٹے کی بارش: {rain} mm
- ہوا: {wd} {ws} km/h، جھونکا {gust} km/h"""
    return f"""【Sha Tin AWS · {rt}】
- Temperature: {t}°C
- Relative humidity: {rh}%
- Rainfall (past hour): {rain} mm
- Wind: {wd} at {ws} km/h, gust {gust} km/h"""


def format_overview_block(overview: Dict[str, Any], lang: LangCode) -> str:
    hq = overview["hko_hq"]
    warnings = "、".join(w["label"] for w in overview.get("warnings", [])) or (
        "无" if lang == "zh" else "None"
    )
    if lang == "ur":
        warnings = "、".join(w["label"] for w in overview.get("warnings", [])) or "کوئی نہیں"

    lines: List[str] = []
    if lang == "zh":
        lines = [
            f"【香港天文台全港概况 · 更新 {overview.get('update_time', '—')}】",
            f"- 天文台总部：{hq.get('temperature', '—')}°C，湿度 {hq.get('humidity', '—')}%",
            f"- 生效警告：{warnings}",
        ]
        if overview.get("forecast_desc"):
            lines.append(f"- 预报：{overview['forecast_desc']}")
        if overview.get("outlook"):
            lines.append(f"- 展望：{overview['outlook']}")
    elif lang == "ur":
        lines = [
            f"【HKO علاقائی خلاصہ · {overview.get('update_time', '—')}】",
            f"- HQ: {hq.get('temperature', '—')}°C، نمی {hq.get('humidity', '—')}%",
            f"- انتباہات: {warnings}",
        ]
        if overview.get("forecast_desc"):
            lines.append(f"- پیشن گوئی: {overview['forecast_desc']}")
    else:
        lines = [
            f"【HKO territory overview · {overview.get('update_time', '—')}】",
            f"- HKO HQ: {hq.get('temperature', '—')}°C, humidity {hq.get('humidity', '—')}%",
            f"- Active warnings: {warnings}",
        ]
        if overview.get("forecast_desc"):
            lines.append(f"- Forecast: {overview['forecast_desc']}")
        if overview.get("outlook"):
            lines.append(f"- Outlook: {overview['outlook']}")
    return "\n".join(lines)


def default_hashtags(lang: LangCode, overview: Dict[str, Any]) -> str:
    if lang == "zh":
        tags = ["#沙田天气", "#香港天文台", "#天气预报", "#即时天气"]
        for w in overview.get("warnings", []):
            if "暴雨" in w["label"]:
                tags.append("#暴雨警告")
            elif "酷热" in w["label"]:
                tags.append("#酷热天气")
        return " ".join(dict.fromkeys(tags))
    if lang == "ur":
        return "#شاٹنموسم #ہنگکانگموسم #موسم #فوریموسم"
    return "#ShaTinWeather #HKObservatory #WeatherHK #HongKongWeather"


def source_line(lang: LangCode) -> str:
    if lang == "zh":
        return "数据来源：香港天文台开放数据 · 沙田自动气象站"
    if lang == "ur":
        return "ماخذ: Hong Kong Observatory open data · Sha Tin AWS"
    return "Source: Hong Kong Observatory open data · Sha Tin AWS"


def pick_advice(
    weather: Dict[str, Any],
    shatin_analysis: Dict[str, Any],
    overview_analysis: Dict[str, Any],
    lang: LangCode,
    overview: Optional[Dict[str, Any]] = None,
) -> str:
    rain = float(weather["total_rainfall"])
    temp = float(weather["air_temperature"])
    rh = int(weather["relative_humidity"])

    if lang == "zh":
        for a in overview_analysis.get("advice", []) + shatin_analysis.get("advice", []):
            return a.replace("戶外活動宜攜帶雨具", "外出请携带雨具").replace(
                "悶熱天氣下應適量補充水分、注意防暑", "闷热天气请补水防暑"
            )
        if rain > 0:
            return "有雨，外出请带伞。"
        if temp >= 30 or rh >= 85:
            return "天气闷热，请注意补水防暑。"
        return "外出请关注天文台最新天气消息。"

    if lang == "ur":
        if rain > 0:
            return "بارش ہو رہی ہے؛ چھتری ساتھ رکھیں۔"
        if temp >= 30:
            return "گرمی زیادہ ہے؛ پانی پیتے رہیں۔"
        if overview and any("酷熱" in w.get("label", "") for w in overview.get("warnings", [])):
            return "شدید گرمی کی انتباہ؛ احتیاط کریں۔"
        return "تازہ ترین موسمی معلومات کے لیے رصدگاہ کی ہدایات پر عمل کریں۔"

    if rain > 0:
        return "Rain reported — carry an umbrella if heading out."
    if temp >= 30 or rh >= 85:
        return "Hot and humid — stay hydrated."
    return "Please follow the latest HKO updates."
