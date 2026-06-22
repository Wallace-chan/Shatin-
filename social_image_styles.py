"""社交帖配图风格：沙田 3D 卡通 + 国画 + 天气海报底图。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# style_id -> (繁体标签, 输出文件名后缀)
SOCIAL_IMAGE_STYLES: Dict[str, Tuple[str, str]] = {
    "cartoon": ("沙田3D卡通", "cartoon"),
    "chinese_shatin": ("沙田水墨意境", "chinese_shatin"),
    "poster": ("沙田天氣海報", "poster"),
}

DEFAULT_SOCIAL_STYLES = ("cartoon", "chinese_shatin", "poster")

# 兼容旧环境变量名
_STYLE_ALIASES = {
    "wu_guanzhong": "chinese_shatin",
    "feng_zikai": "chinese_shatin",
    "qi_baishi": "chinese_shatin",
}

_CHINESE_INK_ESSENCE = (
    "Chinese painting: calligraphic ink LINES first; poetic mood (意境); "
    "SIMPLE clean layout with large empty rice-paper space (留白); "
    "bright fresh harmonious colors (明快) — soft sky blue, pale lemon yellow, "
    "light jade green, gentle coral-pink (NOT harsh red); minimal strokes, uncluttered"
)

_NO_INSCRIPTION = (
    "CRITICAL: absolutely NO text, NO Chinese characters, NO calligraphy, "
    "NO red seal stamps, NO artist seals, NO signatures painted in the artwork"
)

# 国画：宁可无题字，绝不加印章
_INK_INSCRIPTION_RULE = (
    "CRITICAL — 绝不加印章: absolutely ZERO seals in the painted image — "
    "no red seal, no chop stamp, no name seal, no square seal, no round seal, "
    "no 印章, no 朱印, no artist stamp anywhere. "
    "Strongly prefer vast blank paper with NO 题字 and NO calligraphy at all (宁可无题字). "
    "Only as absolute last resort: ONE tiny corner phrase in Traditional Chinese "
    "about Sha Tin Hong Kong (沙田/城門河/馬鞍山/沙田風物) — never dominant. "
    "FORBIDDEN: vertical text columns, couplets, random poems, English, artist names, 落款"
)

_INK_NO_SEAL_REPEAT = (
    "Repeat — painting must have NO seals and NO red stamp marks: "
    "zero 印章 in artwork, prefer zero calligraphy"
)

POLLINATIONS_NEGATIVE_POSTER = (
    "text, letters, numbers, words, calligraphy, chinese characters, hanzi, "
    "infographic, chart, UI, interface, menu, label, caption, watermark, "
    "logo, signature, poster layout, typography, weather data, "
    "cluttered details, photorealistic faces"
)

POLLINATIONS_NEGATIVE_INK = (
    "seal, red seal, stamp, chop mark, name seal, artist seal, square seal, round seal, "
    "vermillion seal, red ink stamp, 印章, 朱印, collector seal, reign mark, wax seal, "
    "vertical calligraphy column, couplet, poem text, inscription block, long calligraphy, "
    "text column, writing brush characters, hanzi block, signature, 落款, "
    "english text, latin letters, random poem, unrelated place name, foreign text, "
    "artist name, watermark, harsh red, cluttered details, photorealistic, text overlay"
)

# 沙田建筑（国画简笔，每次必选其一）
_SHATIN_ARCHITECTURE_INK_OPTIONS = (
    "Sha Tin New Town public housing tower — tall white-grey block with window dots, clearly visible",
    "Sha Tin Town Hall — distinct cubic municipal roofline in minimal ink strokes",
    "Ten Thousand Buddhas Monastery pagoda peak on hillside — small tiered roof silhouette",
    "Tsang Tai Uk Hakka walled village — grey brick wall with traditional roof eaves",
    "Shatin MTR elevated viaduct by the river — light grey linear bridge structure",
    "New Town Plaza mall block — modern curved facade suggested by a few clean lines",
)


def parse_social_style_list(env_value: Optional[str] = None) -> List[str]:
    import os

    raw = (env_value if env_value is not None else os.environ.get("SOCIAL_IMAGE_STYLES", ""))
    raw = raw.strip()
    if not raw or raw.lower() in ("all", "default"):
        return list(DEFAULT_SOCIAL_STYLES)
    styles: List[str] = []
    for token in raw.split(","):
        s = token.strip()
        if not s:
            continue
        s = _STYLE_ALIASES.get(s, s)
        if s in SOCIAL_IMAGE_STYLES and s not in styles:
            styles.append(s)
    return styles or list(DEFAULT_SOCIAL_STYLES)


def _weather_context(
    weather: Dict[str, Any], overview: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    temp = float(weather["air_temperature"])
    rain = float(weather["total_rainfall"])
    rh = int(weather["relative_humidity"])
    rainy = rain > 0
    storm = False
    if overview:
        for w in overview.get("warnings", []):
            label = w.get("label", "")
            if "暴雨" in label or "雷暴" in label:
                storm = True
                rainy = True
    return {
        "rainy": rainy,
        "storm": storm,
        "hot": temp >= 30,
        "humid": rh >= 85,
        "temp": temp,
        "rain": rain,
    }


def _shatin_landscape_cartoon(ctx: Dict[str, Any]) -> str:
    """沙田地标与风景（卡通用）。"""
    base = (
        "Sha Tin Hong Kong: Shing Mun River promenade with cycling path, "
        "Ma On Shan mountain ridge behind, distant Lion Rock silhouette, "
        "subtle Shatin New Town residential towers in soft bokeh, lush subtropical greenery"
    )
    if ctx["rainy"]:
        return f"{base}, rainy mist over river, wet pavement reflections"
    if ctx["hot"]:
        return f"{base}, bright humid summer haze, clear sky"
    return f"{base}, gentle clouds over green hills"


def _shatin_inscription_hint(ctx: Dict[str, Any]) -> str:
    """若画面需要题字，指定沙田相关繁体短语。"""
    if ctx["rainy"]:
        options = ("沙田煙雨", "城門春雨", "沙田雨意")
    elif ctx["hot"]:
        options = ("馬鞍山晴", "沙田夏日", "城門河畔")
    else:
        options = ("城門河畔", "沙田風物", "沙田新市鎮")
    idx = int(ctx["temp"] * 5 + ctx["rain"] * 2) % len(options)
    phrase = options[idx]
    return (
        f"Last-resort only (prefer none): if any tiny corner 题字 appears, "
        f"use ONLY 「{phrase}」 — Traditional Chinese, Sha Tin related, "
        f"smallest possible brushwork; still NO 印章"
    )


def _shatin_architecture_ink(ctx: Dict[str, Any]) -> str:
    """每次国画至少包含一个可辨认的沙田建筑元素。"""
    idx = int(ctx["temp"] * 7 + ctx["rain"] * 3) % len(_SHATIN_ARCHITECTURE_INK_OPTIONS)
    building = _SHATIN_ARCHITECTURE_INK_OPTIONS[idx]
    return (
        f"MANDATORY man-made Sha Tin landmark (must be clearly visible, not optional): "
        f"{building}"
    )


def _shatin_landscape_ink(ctx: Dict[str, Any]) -> str:
    """沙田自然景观 + 必选建筑（国画用，简笔暗示）。"""
    hills = "Ma On Shan peaks as two rhythmic ink hill lines"
    river = "Shing Mun River as one horizontal flowing line with soft blue wash"
    arch = _shatin_architecture_ink(ctx)
    if ctx["rainy"]:
        return (
            f"Natural scenery: {hills}, {river}, light rain lines, misty riverbank 意境. "
            f"{arch}"
        )
    if ctx["hot"]:
        return (
            f"Natural scenery: {hills}, {river}, pale yellow heat haze, open summer 意境. "
            f"{arch}"
        )
    return f"Natural scenery: {hills}, {river}, calm riverside 意境. {arch}"


def build_style_prompt_en(
    style_id: str,
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    overview: Optional[Dict[str, Any]] = None,
) -> str:
    ctx = _weather_context(weather, overview)
    if style_id == "cartoon":
        return _prompt_cartoon(ctx)
    if style_id == "chinese_shatin":
        return _prompt_chinese_shatin(ctx)
    if style_id == "poster":
        return _prompt_poster_bg(ctx, overview)
    raise ValueError(f"未知风格: {style_id}")


def _prompt_cartoon(ctx: Dict[str, Any]) -> str:
    shatin = _shatin_landscape_cartoon(ctx)
    if ctx["rainy"]:
        scene = (
            "boy with fluffy cyan-blue curly hair holds a translucent umbrella "
            "over a tiny round blue raindrop mascot, standing on Shing Mun River promenade"
        )
    elif ctx["hot"]:
        scene = (
            "boy and blue mascot sharing iced drink under a banyan tree "
            "beside Shatin riverside park"
        )
    else:
        scene = (
            "boy and blue mascot cycling along Shatin riverside path, "
            "enjoying breeze from Ma On Shan"
        )

    return (
        "Award-winning 3D animated film still, Pixar Disney quality, sharp focus, "
        "8k ultra high resolution, crisp clean render, "
        "cute stylized child with vivid cyan curly hair, white tee, navy shorts, "
        f"{scene}, {shatin}, bright cheerful colors, wholesome family-friendly, "
        f"{_NO_INSCRIPTION}, no watermark, masterpiece"
    )


def _festival_scene_hint(overview: Optional[Dict[str, Any]]) -> str:
    if not overview:
        return ""
    blob = " ".join(
        str(overview.get(k, ""))
        for k in ("forecast_desc", "outlook", "general_situation")
    )
    if "端午" in blob:
        return (
            "Dragon Boat Festival theme: dragon boats on Shing Mun River, "
            "cute zongzi rice-dumpling mascots, festive red decorations, "
            "dragon dance arch over water"
        )
    if "中秋" in blob:
        return "Mid-Autumn theme: full moon over Ma On Shan, lanterns by the river"
    return ""


def _prompt_poster_bg(ctx: Dict[str, Any], overview: Optional[Dict[str, Any]]) -> str:
    """海报右侧插画底图：无字、留左侧空间。"""
    shatin = _shatin_landscape_cartoon(ctx)
    festival = _festival_scene_hint(overview)
    if ctx["rainy"]:
        mood = "soft rain, misty river, wet reflections, cozy atmosphere"
    elif ctx["hot"]:
        mood = "bright summer sunshine, clear humid haze"
    else:
        mood = "pleasant breezy day, fluffy clouds"

    fest = f"{festival}, " if festival else ""
    return (
        "Vertical poster background illustration ONLY for the right side, "
        "cheerful Hong Kong Sha Tin weather scene, soft watercolor cartoon style, "
        "clean bright colors, simple lines, uncluttered, "
        f"{fest}{shatin}, {mood}, "
        "composition: main scenery on the right two-thirds, "
        "soft pale empty sky gradient on the left third for text overlay later, "
        f"{_NO_INSCRIPTION}, no numbers, no infographic, no UI elements, masterpiece"
    )


def _prompt_chinese_shatin(ctx: Dict[str, Any]) -> str:
    """丰子恺生活笔意 + 吴冠中点线面，沙田风景。"""
    shatin = _shatin_landscape_ink(ctx)
    if ctx["rainy"]:
        life = (
            "one or two tiny figures with pale umbrellas on riverside path — "
            "only a few gentle ink lines, daily-life warmth"
        )
    elif ctx["hot"]:
        life = "one small figure resting under a tree by the river — minimal lines"
    else:
        life = (
            "a parent and child walking along Shing Mun River bank — "
            "elegant simple brush lines"
        )

    inscription = _shatin_inscription_hint(ctx)

    return (
        f"{_INK_INSCRIPTION_RULE}. "
        f"Chinese ink painting blending Feng Zikai daily-life charm and Wu Guanzhong "
        f"abstract lines-and-dots. {_CHINESE_INK_ESSENCE}. "
        f"Sha Tin Hong Kong scenery — nature plus at least one local building: {shatin}. "
        f"{life}. "
        "Wu-style rhythmic black lines and scattered dots; Feng-style humane simplicity. "
        "65 percent empty off-white paper. Bright soft color washes only. "
        f"Clean uncluttered gallery piece. {inscription}. "
        f"{_INK_NO_SEAL_REPEAT}"
    )


def deepseek_refine_instruction(style_id: str) -> str:
    labels = {
        "cartoon": (
            "3D Pixar cartoon in Sha Tin Hong Kong: Shing Mun River, Ma On Shan, "
            "boy and blue mascot, bright clean colors"
        ),
        "chinese_shatin": (
            "Sha Tin Chinese ink: Feng Zikai + Wu Guanzhong blend, simple lines, "
            "Shing Mun River and Ma On Shan, at least one Sha Tin building landmark, "
            "bright soft colors, vast 留白, clean; prefer NO 题字, absolutely NO 印章"
        ),
        "poster": (
            "Sha Tin poster background only: watercolor cartoon, festival if any, "
            "right-side scenery, left pale empty area, NO text NO numbers"
        ),
    }
    hint = labels.get(style_id, "Sha Tin weather illustration")
    if style_id == "poster":
        return (
            f"Rewrite this image prompt in English only (max 100 words). "
            f"Keep: {hint}. NO text, NO numbers, NO letters in image. Output prompt only."
        )
    return (
        f"Rewrite this image prompt in English only (max 120 words). "
        f"Keep style: {hint}. Weather mood from input. "
        f"Must show Sha Tin nature AND at least one recognizable Sha Tin building. "
        f"Simple lines, 意境, clean layout. "
        f"Prefer blank paper with no calligraphy; absolutely NO seals, NO 印章. "
        f"If any text, only one tiny Sha Tin phrase. Output prompt only."
    )
