"""
香港天文台全港天气概况 — HKO 开放数据（与官网首页/预报同源）

数据源：data.weather.gov.hk/weatherAPI/opendata/weather.php
  - rhrread：本港各区气温、湿度、天气图标、闪电等
  - flw：本地天气预报（概况、今晚明日、展望）
  - warnsum：生效中的警告信号摘要
"""

from __future__ import annotations

from typing import Any, Dict, List

import requests

from shatin_weather import REQUEST_TIMEOUT, _find_place, _retry

OPEN_DATA_URL = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php"

# 官网首页「HKO」实况以天文台总部为代表
HKO_HQ_PLACE = "香港天文台"

WARNING_TYPE_LABELS = {
    "WRAIN": "暴雨警告",
    "WRAINA": "黄色暴雨警告",
    "WRAINR": "红色暴雨警告",
    "WRAINB": "黑色暴雨警告",
    "WTS": "雷暴警告",
    "WFIRE": "火災危險警告",
    "WFIREY": "黃色火災危險警告",
    "WFIRER": "紅色火災危險警告",
    "TC": "熱帶氣旋警告",
    "WMSGNL": "強烈季候風信號",
    "WHOT": "酷熱天氣警告",
    "WCOLD": "寒冷天氣警告",
    "WTMW": "海嘯警告",
    "WFNTSA": "新界北部水浸特別報告",
}


def _fetch_json(params: dict) -> dict:
    def _do() -> dict:
        response = requests.get(
            OPEN_DATA_URL, params=params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    return _retry(_do)


def _warning_label(code: str, entry: dict) -> str:
    name = entry.get("name") or WARNING_TYPE_LABELS.get(code, code)
    color = entry.get("type") or ""
    # 仅附加颜色等级（如「黃色」），不附加内部代码（如 WTS）
    if color and color not in name and not str(color).startswith("W"):
        return f"{name}（{color}）"
    return name


def get_hko_overview(lang: str = "tc") -> Dict[str, Any]:
    """拉取与 HKO 官网同步的全港天气概况、预报及生效警告。"""
    rhrread = _fetch_json({"dataType": "rhrread", "lang": lang})
    flw = _fetch_json({"dataType": "flw", "lang": lang})
    warnsum = _fetch_json({"dataType": "warnsum", "lang": lang})

    hq_temp = _find_place(rhrread.get("temperature", {}).get("data", []), HKO_HQ_PLACE)
    hq_humidity = _find_place(rhrread.get("humidity", {}).get("data", []), HKO_HQ_PLACE)

    warnings: List[Dict[str, str]] = []
    for code, entry in (warnsum or {}).items():
        if not isinstance(entry, dict):
            continue
        warnings.append(
            {
                "code": code,
                "label": _warning_label(code, entry),
                "action": entry.get("actionCode", ""),
                "update_time": entry.get("updateTime") or entry.get("issueTime", ""),
            }
        )

    lightning_places = [
        item["place"]
        for item in rhrread.get("lightning", {}).get("data", [])
        if str(item.get("occur", "")).lower() == "true"
    ]

    overview: Dict[str, Any] = {
        "lang": lang,
        "source_url": "https://www.hko.gov.hk/tc/index.html",
        "api_source": OPEN_DATA_URL,
        "update_time": rhrread.get("updateTime"),
        "hko_hq": {
            "place": HKO_HQ_PLACE,
            "temperature": hq_temp.get("value") if hq_temp else None,
            "temperature_unit": (hq_temp or {}).get("unit", "C"),
            "humidity": hq_humidity.get("value") if hq_humidity else None,
            "humidity_unit": (hq_humidity or {}).get("unit", "percent"),
            "humidity_record_time": rhrread.get("humidity", {}).get("recordTime"),
        },
        "weather_icon": rhrread.get("icon"),
        "general_situation": flw.get("generalSituation", ""),
        "forecast_period": flw.get("forecastPeriod", ""),
        "forecast_desc": flw.get("forecastDesc", ""),
        "outlook": flw.get("outlook", ""),
        "flw_update_time": flw.get("updateTime"),
        "warnings": warnings,
        "lightning_areas": lightning_places,
        "lightning_period": {
            "start": rhrread.get("lightning", {}).get("startTime"),
            "end": rhrread.get("lightning", {}).get("endTime"),
        },
    }
    return overview


def format_overview_facts(overview: Dict[str, Any]) -> str:
    hq = overview["hko_hq"]
    lines = [
        f"全港概况（香港天文台开放数据，更新 {overview.get('update_time', '—')}）：",
        f"- 天文台总部气温：{hq.get('temperature', '—')}°{hq.get('temperature_unit', 'C')}",
        f"- 天文台总部相对湿度：{hq.get('humidity', '—')}%",
    ]
    if overview.get("general_situation"):
        lines.append(f"- 天气概况：{overview['general_situation']}")
    if overview.get("forecast_desc"):
        period = overview.get("forecast_period") or "本地预报"
        lines.append(f"- {period}：{overview['forecast_desc']}")
    if overview.get("outlook"):
        lines.append(f"- 展望：{overview['outlook']}")
    if overview.get("warnings"):
        labels = "、".join(w["label"] for w in overview["warnings"])
        lines.append(f"- 生效警告：{labels}")
    else:
        lines.append("- 生效警告：無")
    if overview.get("lightning_areas"):
        lines.append(
            "- 閃電監測區域："
            + "、".join(overview["lightning_areas"][:6])
            + (" 等" if len(overview["lightning_areas"]) > 6 else "")
        )
    return "\n".join(lines)


def summarize_overview(overview: Dict[str, Any]) -> Dict[str, Any]:
    """生成简短摘要，供帖文模板 / AI 使用。"""
    tags: List[str] = []
    advice: List[str] = []

    for w in overview.get("warnings", []):
        label = w["label"]
        if "暴雨" in label:
            tags.append("有暴雨警告")
            advice.append("出街記得帶遮，留意路面水浸")
        if "雷暴" in label:
            tags.append("有雷暴警告")
            advice.append("雷暴期間請遠離高處、樹木同水面")
        if "酷熱" in label:
            tags.append("酷熱天氣警告")
            advice.append("注意防暑補水")

    if overview.get("lightning_areas"):
        tags.append("有閃電監測")

    desc = overview.get("forecast_desc", "")
    if "驟雨" in desc or "大雨" in desc or "暴雨" in desc:
        tags.append("有雨")
    if "炎熱" in desc or "酷熱" in desc:
        tags.append("炎熱")

    warning_text = (
        "、".join(w["label"] for w in overview.get("warnings", []))
        or "目前無特別警告"
    )
    briefing = (
        f"本港方面，天文台總部約 {overview['hko_hq'].get('temperature', '—')}°C、"
        f"濕度 {overview['hko_hq'].get('humidity', '—')}%。"
        f"生效警告：{warning_text}。"
    )
    if overview.get("forecast_desc"):
        briefing += f" {overview['forecast_desc']}"
    if overview.get("outlook"):
        briefing += f" 展望：{overview['outlook']}"

    return {
        "tags": tags,
        "advice": advice,
        "warning_text": warning_text,
        "briefing": briefing,
    }


def print_overview(overview: Dict[str, Any]) -> None:
    hq = overview["hko_hq"]
    print("\n" + "=" * 44)
    print("🌏 香港天文台 · 全港天气概况")
    print("=" * 44)
    print(
        f"🌡️  天文台总部: {hq.get('temperature', '—')}°C  "
        f"💧 湿度: {hq.get('humidity', '—')}%"
    )
    if overview.get("general_situation"):
        print(f"📋  概况: {overview['general_situation']}")
    if overview.get("forecast_desc"):
        print(f"📅  {overview.get('forecast_period', '预报')}: {overview['forecast_desc']}")
    if overview.get("outlook"):
        print(f"🔭  展望: {overview['outlook']}")
    if overview.get("warnings"):
        print("⚠️  生效警告:")
        for w in overview["warnings"]:
            print(f"    · {w['label']}")
    else:
        print("⚠️  生效警告: 无")
    if overview.get("lightning_areas"):
        print(f"⚡  闪电区域: {', '.join(overview['lightning_areas'][:8])}")
    print(f"🕒  数据更新: {overview.get('update_time', '—')}")
    print("=" * 44 + "\n")
