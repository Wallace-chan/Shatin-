"""天气帖文配图：提示词构建 + 多后端出图。"""

import os
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from deepseek_utils import chat_completion, has_deepseek_api_key
from social_image_styles import (
    SOCIAL_IMAGE_STYLES,
    POLLINATIONS_NEGATIVE_INK,
    POLLINATIONS_NEGATIVE_POSTER,
    build_style_prompt_en,
    deepseek_refine_instruction,
    parse_social_style_list,
)
from poster_compose import compose_weather_poster, poster_dimensions

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"


def _has_active_rain_warning(overview: Optional[Dict[str, Any]]) -> bool:
    if not overview:
        return False
    for w in overview.get("warnings", []):
        if "暴雨" in w.get("label", "") or "雷暴" in w.get("label", ""):
            return True
    return False


def build_social_cartoon_prompt_en(
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    overview: Optional[Dict[str, Any]] = None,
) -> str:
    """向后兼容：等同 cartoon 风格。"""
    return build_style_prompt_en("cartoon", weather, analysis, overview)


def _openai_styles_enabled() -> set:
    raw = os.environ.get("OPENAI_IMAGE_STYLES", "").strip()
    if not raw:
        return set()
    return {s.strip() for s in raw.split(",") if s.strip()}


def _pollinations_model() -> str:
    return os.environ.get("IMAGE_MODEL", "flux").strip() or "flux"


def _social_image_dimensions() -> Tuple[int, int]:
    """社交配图尺寸；默认 1536 提升清晰度。"""
    raw = os.environ.get("IMAGE_SIZE", "1536").strip().lower()
    if "x" in raw:
        parts = raw.split("x", 1)
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    try:
        side = int(raw)
        return side, side
    except ValueError:
        return 1536, 1536


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


def build_social_caption_tc(
    weather: Dict[str, Any],
    overview: Optional[Dict[str, Any]] = None,
) -> str:
    """配图底部繁体中文标语。"""
    rain = float(weather["total_rainfall"])
    temp = float(weather["air_temperature"])
    if _has_active_rain_warning(overview) or rain > 0:
        return "請留意天文台最新天氣消息"
    if temp >= 30:
        return "天氣炎熱，記得補水防暑"
    if int(weather["relative_humidity"]) >= 85:
        return "天氣潮濕悶熱，注意身體"
    return "沙田即時天氣｜請留意天文台消息"


def overlay_social_caption(
    image_path: Path,
    caption: str,
    output_path: Optional[Path] = None,
    theme: str = "modern",
) -> Path:
    """在配图底部叠加半透明横幅与繁体中文标语。"""
    from PIL import Image, ImageDraw

    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    banner_h = max(72, h // 8)
    if theme == "ink":
        bar_color = (248, 242, 230, 215)
        text_color = (45, 42, 38, 255)
    else:
        bar_color = (20, 60, 120, 200)
        text_color = (255, 255, 255, 255)

    overlay = Image.new("RGBA", (w, banner_h), bar_color)
    img.paste(overlay, (0, h - banner_h), overlay)

    draw = ImageDraw.Draw(img)
    font = _load_cjk_font(max(28, banner_h // 3))
    bbox = draw.textbbox((0, 0), caption, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (w - tw) // 2
    y = h - banner_h + (banner_h - th) // 2
    draw.text((x, y), caption, fill=text_color, font=font)

    out = output_path or image_path
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, format="PNG", optimize=True)
    return out


def render_social_cartoon_card(
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    output_path: Path,
    overview: Optional[Dict[str, Any]] = None,
    size: Tuple[int, int] = (1080, 1080),
) -> Path:
    """Pollinations 失败时的本地卡通风信息图。"""
    from PIL import Image, ImageDraw

    w, h = size
    rainy = float(weather["total_rainfall"]) > 0 or _has_active_rain_warning(overview)
    top = (70, 140, 210) if rainy else (100, 180, 230)
    bottom = (30, 90, 160) if rainy else (50, 120, 200)

    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)

    title_font = _load_cjk_font(48)
    body_font = _load_cjk_font(34)
    caption = build_social_caption_tc(weather, overview)

    draw.ellipse((120, 180, 420, 480), fill=(120, 200, 255))
    draw.ellipse((620, 260, 900, 540), fill=(255, 220, 120))
    draw.text((180, 300), "☔" if rainy else "🌤️", fill=(255, 255, 255), font=title_font)

    lines = [
        "沙田區天氣插圖",
        f"氣溫 {weather['air_temperature']}°C  濕度 {weather['relative_humidity']}%",
        f"過去1小時雨量 {weather['total_rainfall']} mm",
        analysis.get("headline", "")[:28],
    ]
    y = 560
    for line in lines:
        draw.text((80, y), line, fill=(255, 255, 255), font=body_font)
        y += 52

    banner_h = 96
    draw.rectangle((0, h - banner_h, w, h), fill=(20, 60, 120))
    bbox = draw.textbbox((0, 0), caption, font=body_font)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) // 2, h - banner_h + 28), caption, fill=(255, 255, 255), font=body_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG", optimize=True)
    return output_path


def _save_raw_as_final(raw_path: Path, output_path: Path) -> Path:
    from PIL import Image

    with Image.open(raw_path) as img:
        img.convert("RGB").save(output_path, format="PNG", optimize=True)
    return output_path


def refine_style_prompt_with_deepseek(style_id: str, base_prompt: str) -> str:
    if style_id == "poster":
        return base_prompt
    if not has_deepseek_api_key():
        return base_prompt
    try:
        refined = chat_completion(
            deepseek_refine_instruction(style_id) + f"\nInput: {base_prompt}",
            max_tokens=160,
            temperature=0.7,
        )
        return refined.strip() or base_prompt
    except Exception:
        return base_prompt


def generate_social_style_image(
    style_id: str,
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    output_path: Path,
    overview: Optional[Dict[str, Any]] = None,
    width: int = 0,
    height: int = 0,
) -> Tuple[Path, str, str, str]:
    """按风格生成一张社交配图。返回 (路径, provider, prompt, caption)。"""
    if style_id not in SOCIAL_IMAGE_STYLES:
        raise ValueError(f"未知风格: {style_id}")

    if width <= 0 or height <= 0:
        if style_id == "poster":
            width, height = poster_dimensions()
        else:
            width, height = _social_image_dimensions()

    base_prompt = build_style_prompt_en(style_id, weather, analysis, overview)
    prompt = refine_style_prompt_with_deepseek(style_id, base_prompt)
    caption = build_social_caption_tc(weather, overview)

    if style_id == "poster":
        return _generate_poster_image(
            prompt, weather, analysis, output_path, overview, caption, width, height
        )

    overlay_theme = "ink" if style_id == "chinese_shatin" else "modern"
    skip_caption = os.environ.get("SKIP_IMAGE_CAPTION", "").strip().lower() in (
        "1", "true", "yes",
    )

    provider = (os.environ.get("IMAGE_PROVIDER", "pollinations")).lower()
    use_openai = (
        os.environ.get("OPENAI_API_KEY", "").startswith("sk-")
        and (
            provider == "openai"
            or style_id in _openai_styles_enabled()
        )
    )

    if use_openai:
        try:
            raw_path = output_path.with_name(output_path.stem + "_raw.png")
            download_openai_image(prompt, "1024x1024", raw_path)
            final = overlay_social_caption(
                raw_path, caption, output_path, theme=overlay_theme
            ) if not skip_caption else _save_raw_as_final(raw_path, output_path)
            raw_path.unlink(missing_ok=True)
            return final, "openai", prompt, caption
        except Exception:
            provider = "pollinations"

    if provider == "pollinations":
        try:
            raw_path = output_path.with_name(output_path.stem + "_raw.png")
            neg = POLLINATIONS_NEGATIVE_INK if style_id == "chinese_shatin" else None
            download_pollinations(
                prompt, width, height, raw_path,
                model=_pollinations_model(), negative=neg,
            )
            final = (
                overlay_social_caption(
                    raw_path, caption, output_path, theme=overlay_theme
                )
                if not skip_caption
                else _save_raw_as_final(raw_path, output_path)
            )
            raw_path.unlink(missing_ok=True)
            return final, f"pollinations/{_pollinations_model()}", prompt, caption
        except requests.RequestException:
            pass

    if style_id == "cartoon":
        path = render_social_cartoon_card(
            weather, analysis, output_path, overview, (width, height)
        )
    else:
        path = render_social_ink_card(
            style_id, weather, analysis, output_path, overview, (width, height)
        )
    return path, "pillow", prompt, caption


def _generate_poster_image(
    prompt: str,
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    output_path: Path,
    overview: Optional[Dict[str, Any]],
    caption: str,
    width: int,
    height: int,
) -> Tuple[Path, str, str, str]:
    """海报：Pollinations 无字底图 + Pillow 拼版（免费）。"""
    provider = (os.environ.get("IMAGE_PROVIDER", "pollinations")).lower()
    raw_path = output_path.with_name(output_path.stem + "_raw.png")
    bg_path: Optional[Path] = None

    if provider == "pollinations":
        try:
            download_pollinations(
                prompt,
                width,
                height,
                raw_path,
                model=_pollinations_model(),
                negative=POLLINATIONS_NEGATIVE_POSTER,
            )
            bg_path = raw_path
            provider_name = f"pollinations+poster/{_pollinations_model()}"
        except requests.RequestException:
            provider_name = "pillow+poster"
    else:
        provider_name = "pillow+poster"

    try:
        compose_weather_poster(
            bg_path, weather, analysis, output_path, overview=overview, caption=caption
        )
    finally:
        if bg_path and bg_path.exists():
            raw_path.unlink(missing_ok=True)

    return output_path, provider_name, prompt, caption


def generate_all_social_images(
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    image_dir: Path,
    stamp: str,
    overview: Optional[Dict[str, Any]] = None,
    styles: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """生成多种风格的社交配图。"""
    style_list = styles or parse_social_style_list()
    results: List[Dict[str, Any]] = []
    image_dir.mkdir(parents=True, exist_ok=True)

    for style_id in style_list:
        label, suffix = SOCIAL_IMAGE_STYLES[style_id]
        out = image_dir / f"social_{stamp}_{suffix}.png"
        try:
            path, provider, prompt, caption = generate_social_style_image(
                style_id, weather, analysis, out, overview=overview
            )
            results.append(
                {
                    "style": style_id,
                    "label": label,
                    "file": f"images/{path.name}",
                    "provider": provider,
                    "caption": caption,
                    "prompt_en": prompt[:400],
                }
            )
        except Exception as exc:
            results.append({"style": style_id, "label": label, "error": str(exc)})
    return results


def render_social_ink_card(
    style_id: str,
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    output_path: Path,
    overview: Optional[Dict[str, Any]] = None,
    size: Tuple[int, int] = (1080, 1080),
) -> Path:
    """AI 失败时的中国风备用信息图。"""
    from PIL import Image, ImageDraw

    w, h = size
    paper = (248, 242, 230)
    img = Image.new("RGB", (w, h), paper)
    draw = ImageDraw.Draw(img)

    label, _ = SOCIAL_IMAGE_STYLES[style_id]
    title_font = _load_cjk_font(44)
    body_font = _load_cjk_font(32)
    caption = build_social_caption_tc(weather, overview)

    draw.rectangle((40, 40, w - 40, h - 120), outline=(60, 60, 60), width=2)
    draw.text((80, 80), f"沙田天氣 · {label}", fill=(30, 30, 30), font=title_font)
    lines = [
        f"氣溫 {weather['air_temperature']}°C  濕度 {weather['relative_humidity']}%",
        f"雨量 {weather['total_rainfall']} mm",
        analysis.get("headline", "")[:24],
    ]
    y = 180
    for line in lines:
        draw.text((80, y), line, fill=(50, 50, 50), font=body_font)
        y += 48

    banner_h = 88
    draw.rectangle((0, h - banner_h, w, h), fill=(230, 220, 205))
    bbox = draw.textbbox((0, 0), caption, font=body_font)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) // 2, h - banner_h + 24), caption, fill=(40, 40, 40), font=body_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG", optimize=True)
    return output_path


def generate_social_cartoon_image(
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    output_path: Path,
    overview: Optional[Dict[str, Any]] = None,
    width: int = 1080,
    height: int = 1080,
) -> Tuple[Path, str, str, str]:
    """
    生成社交帖卡通配图（默认免费 Pollinations + Pillow 加字）。
    返回 (路径, provider, 英文 prompt, 中文标语)。
    """
    return generate_social_style_image(
        "cartoon", weather, analysis, output_path, overview, width, height
    )


def refine_cartoon_prompt_with_deepseek(base_prompt: str) -> str:
    return refine_style_prompt_with_deepseek("cartoon", base_prompt)


def build_image_prompt_en(weather: Dict[str, Any], analysis: Dict[str, Any]) -> str:
    """根据实况生成英文文生图提示（模型对英文更稳）。"""
    temp = weather["air_temperature"]
    rh = weather["relative_humidity"]
    rain = weather["total_rainfall"]
    wind = weather["wind_speed"]
    direction = weather["wind_direction"]
    headline = analysis.get("headline", "")

    scene = "overcast humid" if rh >= 75 else "clear pleasant"
    if float(rain) > 5:
        scene = "rainy wet streets umbrellas"
    elif float(rain) > 0:
        scene = "light rain drizzle"
    if float(temp) >= 30:
        scene += ", hot summer haze"
    elif float(temp) <= 18:
        scene += ", cool crisp air"

    return (
        f"Professional weather photo for social media, Sha Tin district Hong Kong, "
        f"{scene}, {direction} wind, realistic documentary style, soft natural light, "
        f"subtle Hong Kong residential hills in background, no text no watermark no logos, "
        f"atmospheric mood reflecting {headline}, 8k photorealistic"
    )


def refine_prompt_with_deepseek(base_prompt: str) -> str:
    if not has_deepseek_api_key():
        return base_prompt
    try:
        refined = chat_completion(
            f"""Rewrite this image generation prompt in English only (max 80 words).
Keep: Sha Tin Hong Kong weather scene, photorealistic, no text/watermark.
Input: {base_prompt}
Output prompt only:""",
            max_tokens=120,
            temperature=0.7,
        )
        return refined.strip() or base_prompt
    except Exception:
        return base_prompt


def download_pollinations(
    prompt: str,
    width: int,
    height: int,
    output_path: Path,
    timeout: int = 180,
    model: Optional[str] = None,
    enhance: bool = True,
    negative: Optional[str] = None,
) -> Path:
    encoded = urllib.parse.quote(prompt, safe="")
    seed = abs(hash(prompt)) % 999999
    model_name = model or _pollinations_model()
    url = (
        f"{POLLINATIONS_BASE}/{encoded}"
        f"?width={width}&height={height}&nologo=true&seed={seed}"
        f"&model={urllib.parse.quote(model_name, safe='')}"
    )
    if enhance:
        url += "&enhance=true"
    if negative:
        url += f"&negative={urllib.parse.quote(negative, safe='')}"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)

    # 若 API 返回尺寸偏小，用高质量重采样放大到目标尺寸
    try:
        from PIL import Image

        resample = getattr(Image, "Resampling", Image).LANCZOS
        with Image.open(output_path) as img:
            if img.width < width or img.height < height:
                upscaled = img.resize((width, height), resample)
                upscaled.save(output_path, format="PNG", optimize=True)
    except Exception:
        pass

    return output_path


def download_openai_image(
    prompt: str,
    size: str,
    output_path: Path,
) -> Path:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    result = client.images.generate(
        model="dall-e-3",
        prompt=prompt[:4000],
        size=size,
        quality="standard",
        n=1,
    )
    image_url = result.data[0].url
    if not image_url:
        raise ValueError("OpenAI 未返回图片 URL")
    response = requests.get(image_url, timeout=60)
    response.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    return output_path


def render_pillow_card(
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    output_path: Path,
    size: Tuple[int, int] = (1080, 1080),
) -> Path:
    """无 AI API 时生成简约天气信息图（本地渲染）。"""
    from PIL import Image, ImageDraw, ImageFont

    w, h = size
    img = Image.new("RGB", (w, h), (41, 98, 150))
    draw = ImageDraw.Draw(img)
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 52)
        body_font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 36)
    except OSError:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    lines = [
        "沙田區天氣｜香港天文台數據",
        f"氣溫 {weather['air_temperature']}°C  濕度 {weather['relative_humidity']}%",
        f"雨量(1h) {weather['total_rainfall']} mm",
        f"{weather['wind_direction']}風 {weather['wind_speed']} km/h",
        analysis.get("headline", "")[:40],
    ]
    draw.text((60, 60), lines[0], fill=(255, 255, 255), font=title_font)
    y = 160
    for line in lines[1:]:
        draw.text((60, y), line, fill=(230, 240, 255), font=body_font)
        y += 56

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG", optimize=True)
    return output_path


def generate_weather_image(
    weather: Dict[str, Any],
    analysis: Dict[str, Any],
    output_path: Path,
    width: int,
    height: int,
    provider: Optional[str] = None,
) -> Tuple[Path, str, str]:
    """
    生成一张配图。返回 (路径, 实际使用的 provider, 最终 prompt)。
    provider: auto | pollinations | openai | pillow
    """
    provider = (provider or os.environ.get("IMAGE_PROVIDER", "auto")).lower()
    base_prompt = build_image_prompt_en(weather, analysis)
    prompt = refine_prompt_with_deepseek(base_prompt)

    if provider == "auto":
        if os.environ.get("OPENAI_API_KEY", "").startswith("sk-"):
            provider = "openai"
        else:
            provider = "pollinations"

    if provider == "openai":
        size = "1792x1024" if width > height else "1024x1024"
        if width == height:
            size = "1024x1024"
        return (
            download_openai_image(prompt, size, output_path),
            "openai",
            prompt,
        )

    if provider == "pollinations":
        try:
            return (
                download_pollinations(
                    prompt, width, height, output_path, model=_pollinations_model()
                ),
                f"pollinations/{_pollinations_model()}",
                prompt,
            )
        except requests.RequestException:
            provider = "pillow"

    path = render_pillow_card(weather, analysis, output_path, (width, height))
    return path, "pillow", prompt
