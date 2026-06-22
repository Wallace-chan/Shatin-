"""天气海报：Pollinations 无字底图 + Pillow 叠繁体数据。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

HK_TZ = ZoneInfo("Asia/Hong_Kong")

POSTER_W = 1080
POSTER_H = 1620
LEFT_PANEL_RATIO = 0.46


def poster_dimensions() -> Tuple[int, int]:
    import os

    raw = os.environ.get("POSTER_SIZE", f"{POSTER_W}x{POSTER_H}").strip().lower()
    if "x" in raw:
        a, b = raw.split("x", 1)
        try:
            return int(a), int(b)
        except ValueError:
            pass
    return POSTER_W, POSTER_H


def _load_cjk_font(size: int):
    from PIL import ImageFont

    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _format_poster_date(weather: Dict[str, Any]) -> str:
    raw = str(weather.get("record_time", ""))
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=HK_TZ)
            return f"{dt.year}年{dt.month}月{dt.day}日"
        except ValueError:
            continue
    now = datetime.now(HK_TZ)
    return f"{now.year}年{now.month}月{now.day}日"


def detect_festival_banner(overview: Optional[Dict[str, Any]]) -> Optional[str]:
    """从天文台展望等文本推断节日副标题。"""
    if not overview:
        return None
    blob = " ".join(
        str(overview.get(k, ""))
        for k in ("forecast_desc", "outlook", "general_situation", "forecast_period")
    )
    festivals = (
        ("端午", "端午節氣象專報"),
        ("中秋", "中秋節氣象專報"),
        ("重陽", "重陽節氣象專報"),
        ("新年", "農曆新年氣象專報"),
        ("春節", "農曆新年氣象專報"),
        ("聖誕", "聖誕節氣象專報"),
    )
    for key, label in festivals:
        if key in blob:
            return label
    return None


def _has_warning(overview: Optional[Dict[str, Any]], *keywords: str) -> bool:
    if not overview:
        return False
    for w in overview.get("warnings", []):
        label = w.get("label", "")
        if any(k in label for k in keywords):
            return True
    return False


def build_poster_weather_rows(
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    overview: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, str, str]]:
    """返回 (图标, 主文, 副文) 列表。"""
    temp = float(weather["air_temperature"])
    rh = int(weather["relative_humidity"])
    rain = float(weather["total_rainfall"])
    wind = int(weather["wind_speed"])
    gust = weather.get("wind_gust")
    direction = weather.get("wind_direction", "")

    if _has_warning(overview, "雷暴", "暴雨") or rain >= 5:
        cond, cond_sub = "陣雨或雷暴", "今日天氣"
        icon = "⛈️"
    elif rain > 0:
        cond, cond_sub = "有驟雨", "記得帶傘"
        icon = "🌧️"
    elif temp >= 30:
        cond, cond_sub = "天氣酷熱", "注意防暑"
        icon = "☀️"
    elif rh >= 85:
        cond, cond_sub = "潮濕悶熱", "今日天氣"
        icon = "💧"
    else:
        cond, cond_sub = "多雲間晴", "今日天氣"
        icon = "🌤️"

    rows: List[Tuple[str, str, str]] = [
        (icon, cond, cond_sub),
        ("🌡️", f"氣溫 {temp:.1f}°C", f"濕度 {rh}%"),
    ]

    if rain > 0:
        rows.append(("☔", f"過去1小時雨量 {rain:g} mm", "戶外宜帶雨具"))
    elif _has_warning(overview, "暴雨", "雷暴"):
        rows.append(("☔", "降雨機率偏高", "請留意警告信號"))
    else:
        rows.append(("☔", "過去1小時雨量 0 mm", "暫時無雨"))

    gust_txt = f"  陣風 {gust} km/h" if gust else ""
    rows.append(("💨", f"{direction}風 {wind} km/h", f"注意陣風{gust_txt}".strip()))

    warnings = overview.get("warnings", []) if overview else []
    if warnings:
        labels = "、".join(w["label"] for w in warnings[:2])
        rows.append(("⚠️", labels[:22], "生效警告"))
    else:
        headline = (analysis.get("headline") or "沙田即時天氣")[:18]
        rows.append(("📍", headline, "沙田自動氣象站"))

    return rows


def _draw_rounded_rect(draw, xy, radius: int, fill):
    x0, y0, x1, y1 = xy
    draw.rectangle((x0 + radius, y0, x1 - radius, y1), fill=fill)
    draw.rectangle((x0, y0 + radius, x1, y1 - radius), fill=fill)
    draw.pieslice((x0, y0, x0 + 2 * radius, y0 + 2 * radius), 180, 270, fill=fill)
    draw.pieslice((x1 - 2 * radius, y0, x1, y0 + 2 * radius), 270, 360, fill=fill)
    draw.pieslice((x0, y1 - 2 * radius, x0 + 2 * radius, y1), 90, 180, fill=fill)
    draw.pieslice((x1 - 2 * radius, y1 - 2 * radius, x1, y1), 0, 90, fill=fill)


def _paste_background(canvas, bg_path: Optional[Path], w: int, h: int) -> None:
    from PIL import Image, ImageDraw, ImageFilter

    left_w = int(w * LEFT_PANEL_RATIO)
    right_box = (left_w, 0, w, h - int(h * 0.09))

    if bg_path and bg_path.exists():
        with Image.open(bg_path).convert("RGBA") as bg:
            bg = bg.resize((w, h), Image.Resampling.LANCZOS)
            canvas.paste(bg, (0, 0))
    else:
        draw = ImageDraw.Draw(canvas)
        for y in range(h):
            t = y / max(h - 1, 1)
            r = int(180 + 40 * t)
            g = int(220 - 30 * t)
            b = int(255 - 80 * t)
            draw.line([(0, y), (w, y)], fill=(r, g, b))

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle((0, 0, left_w + 40, h), fill=(252, 250, 242, 210))
    odraw.rectangle((left_w, 0, w, h), fill=(255, 255, 255, 0))
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=0))
    canvas.paste(overlay, (0, 0), overlay)

    shade = Image.new("RGBA", (right_box[2] - right_box[0], right_box[3] - right_box[1]), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shade)
    sdraw.rectangle((0, 0, shade.width, shade.height), fill=(255, 255, 255, 35))
    canvas.paste(shade, (right_box[0], right_box[1]), shade)


def compose_weather_poster(
    bg_path: Optional[Path],
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    output_path: Path,
    overview: Optional[Dict[str, Any]] = None,
    caption: str = "請留意天文台最新天氣消息",
) -> Path:
    """将无字 AI 底图与天气数据合成竖版海报。"""
    from PIL import Image, ImageDraw

    w, h = poster_dimensions()
    img = Image.new("RGBA", (w, h), (252, 250, 242, 255))
    _paste_background(img, bg_path, w, h)
    draw = ImageDraw.Draw(img)

    title_font = _load_cjk_font(46)
    date_font = _load_cjk_font(30)
    fest_font = _load_cjk_font(28)
    row_title_font = _load_cjk_font(30)
    row_sub_font = _load_cjk_font(22)
    banner_font = _load_cjk_font(28)

    header_h = int(h * 0.11)
    _draw_rounded_rect(draw, (24, 28, w - 24, header_h), 18, (198, 230, 198))
    draw.text((48, 48), "香港沙田今日氣象", fill=(25, 70, 45), font=title_font)
    draw.text((48, 102), _format_poster_date(weather), fill=(50, 90, 60), font=date_font)

    festival = detect_festival_banner(overview)
    y = header_h + 16
    if festival:
        fest_h = 52
        _draw_rounded_rect(draw, (36, y, w - 36, y + fest_h), 14, (240, 228, 200))
        bbox = draw.textbbox((0, 0), festival, font=fest_font)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, y + 12), festival, fill=(120, 70, 30), font=fest_font)
        y += fest_h + 20

    rows = build_poster_weather_rows(weather, analysis, overview)
    left_margin = 40
    row_h = 108
    for i, (icon, main, sub) in enumerate(rows):
        ry = y + i * (row_h + 8)
        _draw_rounded_rect(draw, (28, ry, int(w * LEFT_PANEL_RATIO) + 10, ry + row_h), 16, (255, 255, 255, 230))
        draw.text((left_margin, ry + 18), icon, fill=(40, 40, 40), font=row_title_font)
        draw.text((left_margin + 44, ry + 16), main, fill=(30, 30, 30), font=row_title_font)
        draw.text((left_margin + 44, ry + 56), sub, fill=(90, 90, 90), font=row_sub_font)

    banner_h = max(80, int(h * 0.085))
    banner_y = h - banner_h
    banner = Image.new("RGBA", (w, banner_h), (20, 60, 120, 215))
    img.paste(banner, (0, banner_y), banner)
    draw = ImageDraw.Draw(img)

    bbox = draw.textbbox((0, 0), caption, font=banner_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((w - tw) // 2, banner_y + (banner_h - th) // 2), caption, fill=(255, 255, 255), font=banner_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(output_path, format="PNG", optimize=True)
    return output_path
