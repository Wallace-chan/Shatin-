"""
沙田自动气象站实时天气 — 香港天文台 (HKO) 开放数据（共用模块）

数据源（均为 data.weather.gov.hk 官方开放数据）：
  - 气温、湿度：分区 1 分钟 CSV（沙田站）
  - 风速、风向、阵风：分区 10 分钟风况 CSV（沙田站）
  - 雨量：rhrread JSON（沙田区过去一小时雨量）
"""

import csv
import io
import json
import time
from typing import Any, Callable, Dict, List, Optional

import requests

STATION = "沙田"
STATION_LABEL = "沙田自动气象站"
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY_SEC = 1.0

RHRREAD_URL = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php"
REGIONAL_BASE = (
    "https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/"
)
REGIONAL_TEMPERATURE_URL = REGIONAL_BASE + "latest_1min_temperature_uc.csv"
REGIONAL_HUMIDITY_URL = REGIONAL_BASE + "latest_1min_humidity_uc.csv"
REGIONAL_WIND_URL = REGIONAL_BASE + "latest_10min_wind_uc.csv"

REQUIRED_FIELDS = (
    "air_temperature",
    "relative_humidity",
    "wind_speed",
    "wind_direction",
    "total_rainfall",
)


def _retry(fetch_fn: Callable[[], Any]) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = fetch_fn()
            if result is not None:
                return result
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            last_error = e
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SEC)
    if last_error:
        raise last_error
    return None


def _fetch_json(url: str, params: Optional[dict] = None) -> dict:
    def _do() -> dict:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()

    return _retry(_do)


def _fetch_regional_row(url: str, station: str) -> dict:
    def _do() -> Optional[dict]:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        text = response.content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        next(reader, None)
        for row in reader:
            if len(row) >= 2 and row[1] == station:
                return {
                    "record_time": row[0],
                    "station": row[1],
                    "values": row[2:],
                }
        return None

    row = _retry(_do)
    if row is None:
        raise ValueError(f"CSV 中未找到气象站「{station}」: {url}")
    return row


def _find_place(data_list: List[dict], place: str) -> Optional[dict]:
    for item in data_list:
        if item.get("place") == place:
            return item
    return None


def _format_csv_time(raw: str) -> str:
    if len(raw) == 12 and raw.isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]} {raw[8:10]}:{raw[10:12]}"
    return raw


def _parse_float(value: str) -> float:
    return float(value.strip())


def _parse_int(value: str) -> int:
    return int(value.strip())


def get_shatin_weather() -> Dict[str, Any]:
    """获取沙田自动气象站实时数据；必填字段缺失时抛出 ValueError。"""
    weather: Dict[str, Any] = {
        "station": STATION_LABEL,
        "place": STATION,
        "air_temperature": None,
        "relative_humidity": None,
        "total_rainfall": None,
        "rainfall_note": "过去一小时雨量 (rhrread)",
        "wind_speed": None,
        "wind_direction": None,
        "wind_gust": None,
        "record_times": {},
        "data_sources": {},
    }

    temp_row = _fetch_regional_row(REGIONAL_TEMPERATURE_URL, STATION)
    if temp_row["values"]:
        weather["air_temperature"] = _parse_float(temp_row["values"][0])
        weather["data_sources"]["air_temperature"] = REGIONAL_TEMPERATURE_URL
        weather["record_times"]["air_temperature"] = _format_csv_time(
            temp_row["record_time"]
        )

    humidity_row = _fetch_regional_row(REGIONAL_HUMIDITY_URL, STATION)
    if humidity_row["values"]:
        weather["relative_humidity"] = _parse_int(humidity_row["values"][0])
        weather["data_sources"]["relative_humidity"] = REGIONAL_HUMIDITY_URL
        weather["record_times"]["relative_humidity"] = _format_csv_time(
            humidity_row["record_time"]
        )

    wind_row = _fetch_regional_row(REGIONAL_WIND_URL, STATION)
    values = wind_row["values"]
    if len(values) >= 1 and values[0]:
        weather["wind_direction"] = values[0]
    if len(values) >= 2 and values[1]:
        weather["wind_speed"] = _parse_int(values[1])
    if len(values) >= 3 and values[2]:
        weather["wind_gust"] = _parse_int(values[2])
    weather["data_sources"]["wind"] = REGIONAL_WIND_URL
    weather["record_times"]["wind"] = _format_csv_time(wind_row["record_time"])

    rhrread = _fetch_json(RHRREAD_URL, {"dataType": "rhrread", "lang": "tc"})
    rain_item = _find_place(rhrread.get("rainfall", {}).get("data", []), STATION)
    if rain_item is not None:
        weather["total_rainfall"] = rain_item.get("max")
        weather["data_sources"]["total_rainfall"] = (
            RHRREAD_URL + "?dataType=rhrread"
        )
        weather["record_times"]["total_rainfall"] = rhrread.get("updateTime")

    missing = [f for f in REQUIRED_FIELDS if weather.get(f) is None]
    if missing:
        raise ValueError(f"沙田气象数据不完整，缺失字段: {', '.join(missing)}")

    weather["record_time"] = (
        weather["record_times"].get("wind")
        or weather["record_times"].get("air_temperature")
        or weather["record_times"].get("total_rainfall")
    )
    return weather


def analyze_weather(weather: Dict[str, Any]) -> Dict[str, Any]:
    """根据观测值生成简要分析，供文案/发言稿提示使用。"""
    temp = float(weather["air_temperature"])
    rh = int(weather["relative_humidity"])
    rain = float(weather["total_rainfall"])
    wind = int(weather["wind_speed"])
    gust = weather.get("wind_gust")

    tags: List[str] = []
    if temp >= 32:
        tags.append("酷熱")
    elif temp >= 28:
        tags.append("偏暖")
    elif temp <= 18:
        tags.append("清涼")
    else:
        tags.append("氣溫適中")

    if rh >= 85:
        tags.append("非常潮濕")
    elif rh >= 70:
        tags.append("潮濕")
    elif rh <= 50:
        tags.append("較乾燥")

    if rain >= 20:
        tags.append("過去一小時雨量顯著")
    elif rain > 0:
        tags.append("過去一小時有降雨")
    else:
        tags.append("過去一小時雨量甚微")

    if wind >= 25:
        tags.append("風勢清勁")
    elif wind >= 15:
        tags.append("微風至和緩")
    else:
        tags.append("風力輕微")

    advice: List[str] = []
    if rain > 0:
        advice.append("戶外活動宜攜帶雨具")
    if temp >= 28 and rh >= 75:
        advice.append("悶熱天氣下應適量補充水分、注意防暑")
    if gust is not None and int(gust) >= 35:
        advice.append(f"陣風曾達 {gust} 公里/小時，戶外作業及高空活動須格外留意")

    headline = "、".join(tags[:4])
    briefing = (
        f"沙田自動氣象站於 {weather.get('record_time', '最新')} 的觀測顯示，"
        f"氣溫 {temp:.1f}°C、相對濕度 {rh}%、"
        f"過去一小時雨量 {rain} 毫米；"
        f"{weather['wind_direction']}風，平均風速 {wind} 公里/小時"
    )
    if gust is not None:
        briefing += f"，最高陣風 {gust} 公里/小時"
    briefing += f"。整體屬「{headline}」。"
    if advice:
        briefing += "建議：" + "；".join(advice) + "。"

    return {
        "headline": headline,
        "tags": tags,
        "advice": advice,
        "briefing": briefing,
    }


def weather_fingerprint(weather: Dict[str, Any]) -> str:
    """观测数据指纹，用于提示 AI 区分不同日期/时次的文案。"""
    return (
        f"T{weather['air_temperature']}_RH{weather['relative_humidity']}"
        f"_R{weather['total_rainfall']}_W{weather['wind_speed']}"
        f"{weather['wind_direction']}_G{weather.get('wind_gust', '')}"
    )


def format_weather_facts(weather: Dict[str, Any]) -> str:
    record_time = weather.get("record_time") or "未知"
    return f"""天氣資料（香港天文台 · 沙田自動氣象站，觀測時間 {record_time}）：
- 氣溫：{weather['air_temperature']}°C
- 相對濕度：{weather['relative_humidity']}%
- 過去一小時雨量：{weather['total_rainfall']} mm
- 風速：{weather['wind_speed']} 公里/小時
- 風向：{weather['wind_direction']}
- 最高陣風：{weather.get('wind_gust', '無記錄')} 公里/小時"""


def print_weather(weather: Dict[str, Any]) -> None:
    print("\n" + "=" * 44)
    print(f"📍 {weather['station']} 实时天气")
    print("=" * 44)
    print(f"🌡️  气温: {weather['air_temperature']} °C")
    print(f"💧  相对湿度: {weather['relative_humidity']} %")
    print(
        f"☔  {weather['rainfall_note']}: "
        f"{weather['total_rainfall']} mm"
    )
    print(f"💨  风速: {weather['wind_speed']} 公里/小时")
    print(f"🧭  风向: {weather['wind_direction']}")
    if weather.get("wind_gust") is not None:
        print(f"🌬️  最高阵风: {weather['wind_gust']} 公里/小时")
    if weather.get("record_time"):
        print(f"🕒  数据时间: {weather['record_time']}")
    print("=" * 44 + "\n")
