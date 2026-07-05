"""沙田历史文化与天气气候资料：从汇总 docx 选取当日相关素材。"""

from __future__ import annotations

import hashlib
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
from zoneinfo import ZoneInfo

HK_TZ = ZoneInfo("Asia/Hong_Kong")
LangCode = Literal["tc", "zh", "en", "ur"]

_SCRIPT_DIR = Path(__file__).resolve().parent
_MONTH_ZH = (
    "正月", "二月", "三月", "四月", "五月", "六月",
    "七月", "八月", "九月", "十月", "十一月", "十二月",
)

# 文档第三节「播报素材运用建议」整理为可编程规则
_WEATHER_GUIDANCE: Dict[str, Dict[str, str]] = {
    "daily": {
        "tc": "可結合《沙田山居》對雨聲、山嵐、季節變換的描寫，以文學化語句點綴實況數據。",
        "zh": "可结合《沙田山居》对雨声、山岚、季节变换的描写，以文学化语句点缀实况数据。",
        "en": "Pair live readings with literary images from Yu Guangzhong's Shatin essays—rain, mist, and seasonal change.",
        "ur": "《شا ٹن ماؤنٹ لائف》 میں بارش، دھند اور موسمی تبدیلی کی عبارتیں حقیقی اعداد کے ساتھ ملائیں۔",
    },
    "rain": {
        "tc": "方志載近海多風，民間有「潮生風起，潮退風止」之說；暴雨時可留意虹霓、海氣等先兆。",
        "zh": "方志载近海多风，民间有「潮生风起，潮退风止」之说；暴雨时可留意虹霓、海气等先兆。",
        "en": "Gazetteers note coastal winds and the saying “wind rises with the tide”; watch for rainbows and sea haze as storm signs.",
        "ur": "گزٹیر میں ساحلی ہواؤں اور «جزر کے ساتھ ہوا» جیسی کہاوتیں ملتی ہیں؛ طوفانی بارش میں قوس قزح وغیرہ دیکھیں۔",
    },
    "typhoon": {
        "tc": "《新安縣志》「氣候與月令」載颱風徵兆（虹先兆、海氣沸騰等）及「母不回南，再來不待三」等民間經驗。",
        "zh": "《新安县志》「气候与月令」载台风征兆（虹先兆、海气沸腾等）及「母不回南，再来不待三」等民间经验。",
        "en": "The Xin'an Gazetteer records typhoon signs (rainbows, boiling sea air) and folk rhymes about returning storms.",
        "ur": "شین آن گزٹیر میں طوفانی علامات (قوس قزح، سمندری بخار) اور لوک کہاوتیں درج ہیں۔",
    },
    "hot": {
        "tc": "方志述粵地「三冬無雪，四時似夏」；六月為收早禾、再插秧之時，農忙與暑熱並行。",
        "zh": "方志述粤地「三冬无雪，四时似夏」；六月为收早禾、再插秧之时，农忙与暑热并行。",
        "en": "Gazetteers describe south China as snowless and summer-like; June was harvest and replanting season.",
        "ur": "دستاویزات میں جنوبی چین کو بغیر برف، گرمی جیسی چار موسم والا بتایا گیا؛ جون میں کٹائی کا موسم تھا۔",
    },
    "season": {
        "tc": "方志有「一雨成秋」之說，節氣轉換時可把古書月令與沙田當季實況對照播報。",
        "zh": "方志有「一雨成秋」之说，节气转换时可把古书月令与沙田当季实况对照播报。",
        "en": "Folk wisdom says “one rain turns to autumn”—compare ancient monthly almanacs with today's Sha Tin weather.",
        "ur": "کہاوت ہے «ایک بارش سے خزاں»—قدیم ماہانہ کیلنڈر کو آج کے شا ٹن موسم سے ملائیں۔",
    },
}

_PLACE_GUIDANCE = {
    "tc": "田心圍、火炭、馬鞍山、吐露港、九肚山等地名，至今沿用自清《新安縣志》官富司轄境。",
    "zh": "田心围、火炭、马鞍山、吐露港、九肚山等地名，至今沿用自清《新安县志》官富司辖境。",
    "en": "Names like Tin Hau, Fo Tan, Ma On Shan, Tolo Harbour, and Kau To trace back to the Qing Xin'an Gazetteer.",
    "ur": "ٹن ہاؤ، فو ٹان، ما آن شان، ٹولو بندر اور کاؤ ٹو جیسے نام چنگ خاندان کے گزٹیر سے ملتے ہیں۔",
}

_YU_IMAGERY = {
    "tc": "余光中筆下的沙田雨、獅子山、船灣淡水湖與中文大學遠景，是街坊熟悉的文化意象。",
    "zh": "余光中笔下的沙田雨、狮子山、船湾淡水湖与中文大学远景，是街坊熟悉的文化意象。",
    "en": "Yu Guangzhong's images—Shatin rain, Lion Rock, Plover Cove, CUHK vistas—are familiar local symbols.",
    "ur": "یو گوانگ ژونگ کی تصویریں—شا ٹن کی بارش، شیر چٹان، پلوور کوب، یونیورسٹی منظر—مقامی علامات ہیں۔",
}

# 摘自《沙田山居》原文段落（已略去 OCR 錯字），按天氣情境分組
_YU_QUOTES: Dict[str, List[str]] = {
    "daily": [
        "書齋外面是陽台，陽台外面是海，是山。海是碧湛湛的一彎，山是青郁郁的連環。",
        "無言的山水，一動一止，在相知的作者眼中，都有別樣的風姿。",
        "沙田的山緣裏水更長。這裏原是水藍的世界，水上浮着青山的倒影。",
        "若是晴天，獅子山與馬鞍山，便投影在我游離的眼裏，海的上，山的外。",
    ],
    "rain": [
        "最動人是在雨季，山中一夜豪雨，第二天早上她便翩然出山來了。",
        "一場天地動的大雷雨當頂砸下，沙田一帶草木水汪汪的，真有江湖滿地的意思。",
        "來的日子，山變成一座座島嶼，在白煙的橫波縱浪裏，載浮載沉。",
    ],
    "typhoon": [
        "千山磅礴的來勢如壓，誰敢相撼？但是雲煙一起，莊重的山容便改了。",
        "八仙嶺果真化作了過海的八仙，時在波上，時在彌漫的雲間。",
    ],
    "hot": [
        "春來半島，木棉花暖鷓鴣飛。沙田一帶，春來最引人注目。",
        "方志述粵地四時似夏；六月為收早禾、再插秧之時，農忙與暑熱並行。",
    ],
}

_PARA_CACHE: Optional[List[str]] = None
_ALMANAC_CACHE: Optional[Dict[str, str]] = None


@dataclass
class CultureSnippet:
    category: str
    text: str
    source: str


def _docx_path() -> Optional[Path]:
    if os.environ.get("SKIP_SHATIN_CULTURE", "").strip().lower() in ("1", "true", "yes"):
        return None
    env = os.environ.get("SHATIN_CULTURE_DOCX", "").strip()
    if env:
        p = Path(env).expanduser()
        return p if p.is_file() else None
    for candidate in (
        _SCRIPT_DIR / "data" / "沙田历史文化与天气气候资料汇总.docx",
        Path.home() / "Desktop" / "沙田culture" / "沙田历史文化与天气气候资料汇总.docx",
    ):
        if candidate.is_file():
            return candidate
    return None


def _load_paragraphs(path: Path) -> List[str]:
    global _PARA_CACHE
    key = f"{path}:{path.stat().st_mtime_ns}"
    if _PARA_CACHE is not None and getattr(_load_paragraphs, "_cache_key", "") == key:
        return _PARA_CACHE
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paras: List[str] = []
    for para in root.iter(w + "p"):
        line = "".join((n.text or "") for n in para.iter(w + "t")).strip()
        if line:
            paras.append(line)
    _PARA_CACHE = paras
    _load_paragraphs._cache_key = key  # type: ignore[attr-defined]
    return paras


def _clean_snippet(text: str, max_len: int = 120) -> str:
    text = re.sub(r"\s+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 1]
    for sep in "。；，,.;":
        if sep in cut:
            cut = cut[: cut.rfind(sep) + 1]
            break
    return cut.rstrip("，,；;") + "…"


def _extract_almanac(paras: List[str]) -> Dict[str, str]:
    global _ALMANAC_CACHE
    if _ALMANAC_CACHE is not None:
        return _ALMANAC_CACHE
    almanac: Dict[str, str] = {}
    blob = "\n".join(paras)
    m = re.search(r"通志[·•]廣东月令(.+?)(?:占候|邑地)", blob, re.S)
    if not m:
        _ALMANAC_CACHE = almanac
        return almanac
    chunk = m.group(1)
    for i, month in enumerate(_MONTH_ZH):
        start = chunk.find(month)
        if start < 0:
            continue
        nxt = len(chunk)
        for later in _MONTH_ZH[i + 1 :]:
            j = chunk.find(later, start + len(month))
            if j > start:
                nxt = min(nxt, j)
        clause = chunk[start:nxt].strip("，,。；; ")
        if len(clause) > 8:
            almanac[month] = _clean_snippet(clause, 90)
    _ALMANAC_CACHE = almanac
    return almanac


def _pick_yu_quote(profile: str, seed: str) -> Optional[str]:
    pool = _YU_QUOTES.get(profile) or _YU_QUOTES["daily"]
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(pool)
    return pool[idx]


def _weather_profile(weather: Dict[str, Any], overview: Dict[str, Any]) -> str:
    rain = float(weather.get("total_rainfall") or 0)
    temp = float(weather.get("air_temperature") or 0)
    labels = " ".join(w.get("label", "") for w in overview.get("warnings", []))
    if any(k in labels for k in ("热带气旋", "颱風", "台风")):
        return "typhoon"
    if rain > 0 or "暴雨" in labels or "雷暴" in labels:
        return "rain"
    if temp >= 30 or "酷熱" in labels or "酷热" in labels:
        return "hot"
    return "daily"


def fetch_culture_context(
    weather: Optional[Dict[str, Any]] = None,
    overview: Optional[Dict[str, Any]] = None,
    *,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """读取 docx 并返回当日可用的文化/气候素材。"""
    path = _docx_path()
    if not path:
        return {"snippets": [], "skipped": True, "source": None}

    today = today or datetime.now(HK_TZ).date()
    weather = weather or {}
    overview = overview or {}
    try:
        paras = _load_paragraphs(path)
    except (OSError, zipfile.BadZipFile, ET.ParseError):
        return {"snippets": [], "skipped": True, "source": str(path), "error": "parse_failed"}

    almanac = _extract_almanac(paras)
    month_name = _MONTH_ZH[today.month - 1]
    profile = _weather_profile(weather, overview)
    seed = f"{today.isoformat()}-{profile}"

    snippets: List[CultureSnippet] = []
    if month_name in almanac:
        snippets.append(
            CultureSnippet("月令", almanac[month_name], "《新安縣志》廣東月令")
        )
    snippets.append(
        CultureSnippet("天氣文化", _WEATHER_GUIDANCE[profile]["tc"], "播报素材运用建议")
    )
    if profile in ("rain", "typhoon"):
        snippets.append(
            CultureSnippet("民間諺", _WEATHER_GUIDANCE["season"]["tc"], "方志气候")
        )
    yu = _pick_yu_quote(profile, seed)
    if yu:
        snippets.append(CultureSnippet("文學", yu, "《沙田山居》余光中"))
    else:
        snippets.append(CultureSnippet("文學", _YU_IMAGERY["tc"], "余光中意象"))
    if int(hashlib.md5(seed.encode()).hexdigest(), 16) % 3 == 0:
        snippets.append(CultureSnippet("地名", _PLACE_GUIDANCE["tc"], "史料对照说明"))

    return {
        "snippets": snippets[:4],
        "skipped": False,
        "source": str(path),
        "month": month_name,
        "profile": profile,
    }


def _localized_snippet(snippet: CultureSnippet, lang: LangCode, profile: str) -> str:
    if lang == "tc":
        text = snippet.text
    elif snippet.category == "月令":
        text = snippet.text
    elif snippet.category == "天氣文化":
        text = _WEATHER_GUIDANCE.get(profile, _WEATHER_GUIDANCE["daily"])[lang]
    elif snippet.category == "民間諺":
        text = _WEATHER_GUIDANCE["season"][lang]
    elif snippet.category == "地名":
        text = _PLACE_GUIDANCE[lang]
    elif snippet.category == "文學" and snippet.text == _YU_IMAGERY["tc"]:
        text = _YU_IMAGERY[lang]
    else:
        text = snippet.text
    return f"· {text}（{snippet.source}）"


def format_culture_facts(
    culture: Dict[str, Any],
    lang: LangCode = "tc",
) -> str:
    if culture.get("skipped") or not culture.get("snippets"):
        return ""
    headers = {
        "tc": "【沙田文史】",
        "zh": "【沙田文史】",
        "en": "【Sha Tin Culture & Climate】",
        "ur": "【شا ٹن ثقافت و موسم】",
    }
    profile = culture.get("profile", "daily")
    lines = [headers[lang]]
    for sn in culture["snippets"]:
        lines.append(_localized_snippet(sn, lang, profile))
    lines.append(
        {
            "tc": "資料來源：沙田历史文化与天气气候资料汇总.docx",
            "zh": "资料来源：沙田历史文化与天气气候资料汇总.docx",
            "en": "Source: Shatin culture & climate reference docx",
            "ur": "ماخذ: شا ٹن ثقافت و موسم حوالہ دستاویز",
        }[lang]
    )
    return "\n".join(lines)


def format_culture_section(culture: Dict[str, Any], lang: LangCode = "tc") -> str:
    facts = format_culture_facts(culture, lang)
    if not facts:
        return ""
    return facts


def append_culture_section(post: str, culture: Dict[str, Any], lang: LangCode = "tc") -> str:
    section = format_culture_section(culture, lang)
    if not section:
        return post
    lines = post.rstrip().split("\n")
    hashtag_idx = next(
        (i for i in range(len(lines) - 1, -1, -1) if lines[i].strip().startswith("#")),
        len(lines),
    )
    head = "\n".join(lines[:hashtag_idx]).rstrip()
    tail = "\n".join(lines[hashtag_idx:]).strip()
    return f"{head}\n\n{section}\n\n{tail}".strip()
