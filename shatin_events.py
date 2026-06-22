"""沙田官方活动：文化博物馆、沙田大会堂、康文署节目表。"""

from __future__ import annotations

import calendar
import html
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Literal, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

HK_TZ = ZoneInfo("Asia/Hong_Kong")
USER_AGENT = (
    "Mozilla/5.0 (compatible; ShatinWeatherBot/1.0; +https://github.com/Wallace-chan/Shatin-)"
)
TIMEOUT = 25

HERITAGE_BASE = "https://hk.heritage.museum"
HERITAGE_EXHIBITIONS = f"{HERITAGE_BASE}/tc/exhibitions.html"
LCSD_STTH = "https://www.lcsd.gov.hk/tc/stth"
PA_API = "https://api.performing-arts.gov.hk/backend/public/searchProgrammeByEmailPage"
PA_WEB = "https://www.performing-arts.gov.hk"

LangCode = Literal["tc", "zh", "en", "ur"]
Timing = Literal["today", "week", "month"]


@dataclass
class ShatinEvent:
    title: str
    venue: str
    date_text: str
    url: str
    source: str
    timing: Timing
    event_dates: List[date] = field(default_factory=list)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8"})
    return s


def _today() -> date:
    return datetime.now(HK_TZ).date()


def _week_end(today: date) -> date:
    return today + timedelta(days=6)


def _month_range(today: date) -> Tuple[date, date]:
    last = calendar.monthrange(today.year, today.month)[1]
    return date(today.year, today.month, 1), date(today.year, today.month, last)


def _clean_text(text: str) -> str:
    text = html.unescape(re.sub(r"<br\s*/?>", " ", text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _parse_hk_dates(text: str) -> Tuple[Optional[date], Optional[date]]:
    """Parse 至2026年7月27日 / 2026年5月1日至2026年7月25日 / 2026-06-01."""
    text = _clean_text(text)
    if not text:
        return None, None

    range_m = re.search(
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*[至到\-–]\s*(20\d{2})年(\d{1,2})月(\d{1,2})日",
        text,
    )
    if range_m:
        y1, m1, d1, y2, m2, d2 = map(int, range_m.groups())
        return date(y1, m1, d1), date(y2, m2, d2)

    end_m = re.search(r"至\s*(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
    if end_m:
        y, m, d = map(int, end_m.groups())
        return None, date(y, m, d)

    single_m = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
    if single_m:
        y, m, d = map(int, single_m.groups())
        day = date(y, m, d)
        return day, day

    iso_m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", text)
    if iso_m:
        y, m, d = map(int, iso_m.groups())
        day = date(y, m, d)
        return day, day

    return None, None


def _active_on(day: date, start: Optional[date], end: Optional[date]) -> bool:
    if start and end:
        return start <= day <= end
    if end and not start:
        return day <= end
    if start and not end:
        return day >= start
    return False


def _classify_timing(
    event_dates: List[date], start: Optional[date], end: Optional[date], today: date
) -> Optional[Timing]:
    week_end = _week_end(today)
    month_start, month_end = _month_range(today)

    if event_dates:
        if today in event_dates:
            return "today"
        if any(today <= d <= week_end for d in event_dates):
            return "week"
        if any(month_start <= d <= month_end for d in event_dates):
            return "month"
        return None

    if _active_on(today, start, end):
        return "today"
    if start and end:
        if start <= week_end and end >= today:
            return "week"
        if start <= month_end and end >= month_start:
            return "month"
    elif end:
        if today <= end <= week_end:
            return "week"
        if month_start <= end <= month_end or today <= month_end <= end:
            return "month"
    return None


def _parse_prog_show_dates(raw: str) -> List[date]:
    dates: List[date] = []
    for chunk in re.split(r"\*{2,}|\\n|\n", raw or ""):
        chunk = chunk.strip()
        m = re.search(r"(\d{2})/(\d{2})/(20\d{2})", chunk)
        if m:
            d, mo, y = map(int, m.groups())
            try:
                dates.append(date(y, mo, d))
            except ValueError:
                continue
    return dates


def _fetch_heritage_exhibitions(sess: requests.Session, today: date) -> List[ShatinEvent]:
    events: List[ShatinEvent] = []
    try:
        resp = sess.get(HERITAGE_EXHIBITIONS, timeout=TIMEOUT)
        resp.raise_for_status()
        text = resp.text
    except requests.RequestException:
        return events

    blocks = re.findall(
        r'<a href="(/tc/exhibitions/[^"]+)"[^>]*>(.*?)</a>',
        text,
        flags=re.S,
    )
    seen: set[str] = set()
    for href, block in blocks:
        if href in seen:
            continue
        seen.add(href)
        title_m = re.search(r'related-exhibition-title">(.*?)</p>', block, re.S)
        date_m = re.search(r'related-exhibition-date">\s*<p>([^<]+)</p>', block, re.S)
        if not title_m:
            continue
        title = _clean_text(title_m.group(1))
        date_text = _clean_text(date_m.group(1)) if date_m else ""
        start, end = _parse_hk_dates(date_text)
        timing = _classify_timing([], start, end, today)
        if not timing:
            continue
        events.append(
            ShatinEvent(
                title=title,
                venue="香港文化博物館",
                date_text=date_text or "展覽中",
                url=HERITAGE_BASE + href,
                source="heritage_museum",
                timing=timing,
            )
        )
    return events


def _fetch_stth_programmes(sess: requests.Session, today: date) -> List[ShatinEvent]:
    events: List[ShatinEvent] = []
    month_start, month_end = _month_range(today)
    body = {
        "subscribeCode": "STTH",
        "startDate": month_start.isoformat(),
        "endDate": month_end.isoformat(),
        "month": str(today.month),
        "allFacilityIds": [],
        "facility": [],
        "pageState": {"page": 0, "pageSize": 100},
    }
    try:
        resp = sess.post(PA_API, json=body, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
    except (requests.RequestException, ValueError):
        return events

    for rec in data.get("recordList") or []:
        title = (rec.get("lcsd_prog_title_tc") or rec.get("lcsd_prog_title_en") or "").strip()
        if not title:
            continue
        venue = (rec.get("lcsd_venue_cht") or rec.get("lcsd_venue_en") or "沙田大會堂").strip()
        date_text = _clean_text(rec.get("lcsd_prog_date_tc") or rec.get("lcsd_prog_date_en") or "")
        show_dates = _parse_prog_show_dates(rec.get("lcsd_internal_date") or "")
        timing = _classify_timing(show_dates, None, None, today)
        if not timing and date_text:
            timing = "month"
        if not timing:
            continue
        path = rec.get("lcsd_prog_url_tc") or rec.get("lcsd_prog_url_en") or ""
        url = PA_WEB + path if path.startswith("/") else path or LCSD_STTH
        events.append(
            ShatinEvent(
                title=title,
                venue=venue,
                date_text=date_text[:80] if date_text else "本月",
                url=url,
                source="stth_programme",
                timing=timing,
                event_dates=show_dates,
            )
        )
    return events


def _fetch_stth_notices(sess: requests.Session, today: date) -> List[ShatinEvent]:
    events: List[ShatinEvent] = []
    try:
        resp = sess.get(LCSD_STTH, timeout=TIMEOUT)
        resp.raise_for_status()
        text = resp.text
    except requests.RequestException:
        return events

    if "沙田大會堂通告" not in text:
        return events

    notice_block = text.split("沙田大會堂通告", 1)[-1].split("<hr", 1)[0]
    title_m = re.search(r"<h3[^>]*>(.*?)</h3>", notice_block, re.S)
    body_m = re.search(r"<p[^>]*style=\"text-align: center;\"[^>]*>(.*?)</p>", notice_block, re.S)
    if not title_m:
        return events

    title = _clean_text(title_m.group(1))
    summary = _clean_text(body_m.group(1)) if body_m else ""
    summary = re.sub(r"https?://\S+", "", summary)
    if summary:
        summary = re.split(r"[。；;]", summary)[0].strip()
    if len(summary) > 80:
        summary = summary[:77] + "…"

    date_m = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", notice_block)
    notice_day: Optional[date] = None
    if date_m:
        y, m, d = map(int, date_m.groups())
        try:
            notice_day = date(y, m, d)
        except ValueError:
            pass

    timing: Timing = "month"
    if notice_day:
        if notice_day == today:
            timing = "today"
        elif today <= notice_day <= _week_end(today):
            timing = "week"

    link_m = re.search(r'href="(https://www\.lcsd\.gov\.hk[^"]+)"', notice_block)
    url = link_m.group(1) if link_m else LCSD_STTH

    events.append(
        ShatinEvent(
            title=title,
            venue="沙田大會堂",
            date_text=summary or "最新通告",
            url=url,
            source="stth_notice",
            timing=timing,
            event_dates=[notice_day] if notice_day else [],
        )
    )
    return events


def _dedupe(events: List[ShatinEvent]) -> List[ShatinEvent]:
    seen: set[Tuple[str, str]] = set()
    out: List[ShatinEvent] = []
    for ev in events:
        key = (ev.title, ev.venue)
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    return out


def fetch_shatin_events() -> Dict[str, Any]:
    """抓取沙田相关官方活动，按今日/本周/本月归类。"""
    if os.environ.get("SKIP_SHATIN_EVENTS", "").strip().lower() in ("1", "true", "yes"):
        return {
            "today": [],
            "week": [],
            "month": [],
            "notices": [],
            "skipped": True,
            "sources_ok": {},
            "errors": [],
        }

    today = _today()
    sess = _session()
    errors: List[str] = []
    sources_ok: Dict[str, bool] = {}

    heritage = _fetch_heritage_exhibitions(sess, today)
    sources_ok["heritage_museum"] = bool(heritage) or _source_reachable(sess, HERITAGE_EXHIBITIONS)

    programmes = _fetch_stth_programmes(sess, today)
    sources_ok["performing_arts"] = programmes is not None and _source_reachable(
        sess, PA_API, method="POST"
    )

    notices = _fetch_stth_notices(sess, today)
    sources_ok["lcsd_stth"] = _source_reachable(sess, LCSD_STTH)

    all_events = _dedupe(heritage + programmes)
    today_list = [e for e in all_events if e.timing == "today"]
    week_list = [e for e in all_events if e.timing == "week"]
    month_list = [e for e in all_events if e.timing == "month"]

    return {
        "today": today_list[:5],
        "week": week_list[:5],
        "month": month_list[:6],
        "notices": notices[:2],
        "skipped": False,
        "sources_ok": sources_ok,
        "errors": errors,
    }


def _source_reachable(sess: requests.Session, url: str, method: str = "GET") -> bool:
    try:
        if method == "POST":
            r = sess.post(
                url,
                json={"subscribeCode": "STTH", "pageState": {"page": 0, "pageSize": 1}},
                timeout=TIMEOUT,
            )
        else:
            r = sess.get(url, timeout=TIMEOUT)
        return r.status_code < 500
    except requests.RequestException:
        return False


def _section_header(lang: LangCode) -> str:
    return {
        "tc": "【沙田活動】",
        "zh": "【沙田活动】",
        "en": "【Sha Tin Events】",
        "ur": "【شا ٹن سرگرمیاں】",
    }[lang]


def _timing_label(timing: Timing, lang: LangCode) -> str:
    labels = {
        "today": {"tc": "今日", "zh": "今日", "en": "Today", "ur": "آج"},
        "week": {"tc": "本週", "zh": "本周", "en": "This week", "ur": "اس ہفتے"},
        "month": {"tc": "本月", "zh": "本月", "en": "This month", "ur": "اس ماہ"},
    }
    return labels[timing][lang]


def _format_event_line(ev: ShatinEvent, lang: LangCode) -> str:
    if lang == "zh":
        venue = ev.venue.replace("博物館", "博物馆").replace("會堂", "大会堂")
    elif lang == "en":
        venue = {
            "香港文化博物館": "Heritage Museum",
            "沙田大會堂": "Sha Tin Town Hall",
        }.get(ev.venue, ev.venue)
    elif lang == "ur":
        venue = {
            "香港文化博物館": "ثقافتی عجائب گھر",
            "沙田大會堂": "شا ٹن ہال",
        }.get(ev.venue, ev.venue)
    else:
        venue = ev.venue

    date_bit = ev.date_text
    if lang == "en" and "至" in date_bit:
        date_bit = date_bit.replace("至", "until ").replace("年", "-").replace("月", "-").replace("日", "")
    return f"· {ev.title}（{venue}｜{date_bit}）"


def format_events_facts(events: Dict[str, Any], lang: LangCode = "tc") -> str:
    """供 AI prompt 使用的活动事实块。"""
    if events.get("skipped"):
        return ""
    lines = [_section_header(lang).strip("【】")]
    has_any = False
    for timing in ("today", "week", "month"):
        bucket = events.get(timing) or []
        if not bucket:
            continue
        has_any = True
        lines.append(f"{_timing_label(timing, lang)}：")
        for ev in bucket:
            lines.append(_format_event_line(ev, lang))
    for notice in events.get("notices") or []:
        has_any = True
        label = {"tc": "通告", "zh": "通告", "en": "Notice", "ur": "اعلان"}[lang]
        lines.append(f"{label}：{_format_event_line(notice, lang)}")
    if not has_any:
        empty = {
            "tc": "官方節目表本月暫無沙田演出；文化博物館展覽請留意博物館網站。",
            "zh": "官方节目表本月暂无沙田演出；文化博物馆展览请留意博物馆网站。",
            "en": "No Sha Tin Town Hall performances listed this month; check Heritage Museum for exhibitions.",
            "ur": "اس ماہ شا ٹن ہال میں کوئی پروگرام درج نہیں؛ میوزیم کی نمائشوں کے لیے ویب سائٹ دیکھیں۔",
        }
        lines.append(empty[lang])
    lines.append(
        {
            "tc": "資料來源：hk.heritage.museum、lcsd.gov.hk/tc/stth、performing-arts.gov.hk",
            "zh": "数据来源：hk.heritage.museum、lcsd.gov.hk/tc/stth、performing-arts.gov.hk",
            "en": "Sources: hk.heritage.museum, lcsd.gov.hk/tc/stth, performing-arts.gov.hk",
            "ur": "ماخذ: hk.heritage.museum، lcsd.gov.hk/tc/stth، performing-arts.gov.hk",
        }[lang]
    )
    return "\n".join(lines)


def format_events_section(events: Dict[str, Any], lang: LangCode = "tc") -> str:
    """帖文模板用的活动板块（无活动则返回空字符串）。"""
    if events.get("skipped"):
        return ""
    facts = format_events_facts(events, lang)
    if not facts:
        return ""
    body_lines: List[str] = [_section_header(lang)]
    has_items = any(events.get(k) for k in ("today", "week", "month")) or events.get("notices")
    if not has_items:
        return ""

    for timing in ("today", "week", "month"):
        bucket = events.get(timing) or []
        if not bucket:
            continue
        body_lines.append(f"{_timing_label(timing, lang)}")
        for ev in bucket[:3]:
            body_lines.append(_format_event_line(ev, lang))
    for notice in events.get("notices") or []:
        label = {"tc": "通告", "zh": "通告", "en": "Notice", "ur": "اعلان"}[lang]
        body_lines.append(label)
        body_lines.append(_format_event_line(notice, lang))
    return "\n".join(body_lines)


def append_events_section(post: str, events: Dict[str, Any], lang: LangCode = "tc") -> str:
    """在 hashtag 之前插入活动板块。"""
    section = format_events_section(events, lang)
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
