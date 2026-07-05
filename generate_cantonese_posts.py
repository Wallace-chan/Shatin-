"""
沙田天气 · 口语化粤语帖文

数据抓取与 generate_social_posts 相同：
  - 沙田自动气象站：shatin_weather.py
  - 天文台全港概况：hko_overview.py

输出：一篇粵語口語帖文（三平台通用，只保存一个文件）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from cantonese_post import generate_colloquial_post
from deepseek_utils import configure_stdio_utf8, has_deepseek_api_key
from hko_overview import get_hko_overview, print_overview, summarize_overview
from shatin_culture import fetch_culture_context
from shatin_events import fetch_shatin_events
from shatin_weather import analyze_weather, get_shatin_weather, print_weather, weather_fingerprint
from workflow_schedule import (
    HK_TZ,
    github_event_name,
    output_stamp,
    run_slot,
    should_persist_state,
    slot_key,
    slot_record_time,
)

configure_stdio_utf8()

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
DATA_DIR = SCRIPT_DIR / "data"
STATE_FILE = DATA_DIR / "cantonese_state.json"
WORKFLOW = "cantonese"


def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        state.setdefault("runs", {})
        return state
    return {"last_hash": None, "runs": {}}


def _save_state(state: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def _save_output(content: str, stamp: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"post_{stamp}_cantonese.txt"
    path.write_text(content, encoding="utf-8")
    print(f"✅ 已保存: output/{path.name}")
    return path


def main() -> int:
    print("正在拉取天气数据（口语粤语帖文）…")
    print("  · 沙田自动气象站（分区 CSV + rhrread）")
    print("  · 全港概况（rhrread + flw + warnsum，同源 HKO 官网）")
    print("  · 沙田活动（文化博物馆 / 沙田大会堂 / 康文署节目表）\n")

    try:
        weather = get_shatin_weather()
        overview = get_hko_overview(lang="tc")
    except Exception as e:
        print(f"❌ 天气数据获取失败: {e}", file=sys.stderr)
        return 1

    print_weather(weather)
    print_overview(overview)

    shatin_analysis = analyze_weather(weather)
    overview_analysis = summarize_overview(overview)
    print(f"📊 沙田：{shatin_analysis['briefing']}\n")
    print(f"📊 全港：{overview_analysis['briefing']}\n")

    if not has_deepseek_api_key():
        print("⚠️  未设置 DEEPSEEK_API_KEY，使用本地粵語口語模板\n")

    events = fetch_shatin_events()
    if not events.get("skipped"):
        n = sum(len(events.get(k) or []) for k in ("today", "week", "month", "notices"))
        print(f"📅 沙田活动：抓取到 {n} 条官方信息\n")

    culture = fetch_culture_context(weather, overview)
    if not culture.get("skipped"):
        print(f"📜 沙田文史：已载入 {len(culture.get('snippets') or [])} 条当月素材\n")

    state = _load_state()
    now = datetime.now(HK_TZ)
    slot = run_slot(now)
    key = slot_key(now, slot)
    record_time = slot_record_time(now, slot, workflow=WORKFLOW)
    stamp = output_stamp(now, slot, workflow=WORKFLOW)
    trigger = github_event_name()

    print("🤖 正在生成粵語口語帖文…")
    content = generate_colloquial_post(
        weather, overview, shatin_analysis, overview_analysis, events, culture
    )

    h = _content_hash(content)
    prev_hash = (state.get("runs") or {}).get(key, {}).get("hash")
    if prev_hash == h:
        print(f"⚠️  与本次排程 slot（{key}）上次 hash 相同", file=sys.stderr)
    elif state.get("last_hash") == h:
        print("⚠️  与上次生成内容 hash 相同", file=sys.stderr)

    _save_output(content, stamp)
    if should_persist_state():
        state.setdefault("runs", {})[key] = {
            "hash": h,
            "at": record_time.isoformat(),
            "trigger": trigger,
            "stamp": stamp,
        }
        state["last_hash"] = h
        _save_state(state)
    else:
        print(
            "ℹ️  手动 Run：已生成帖文（artifact），不更新仓库内 data/cantonese_state.json，"
            "不影响今日排程 slot",
            file=sys.stderr,
        )

    manifest = {
        "generated_at_hkt": record_time.isoformat(),
        "trigger": trigger,
        "slot": slot,
        "style": "colloquial_cantonese",
        "weather_fingerprint": weather_fingerprint(weather),
        "warnings": [w["label"] for w in overview.get("warnings", [])],
        "stamp": stamp,
        "hko_source": "https://www.hko.gov.hk/tc/index.html",
    }
    (OUTPUT_DIR / "latest_cantonese_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\n--- 粵語口語帖文 ---\n")
    print(content)
    print(f"\n🎉 已生成 1 篇粵語口語帖文")
    return 0


if __name__ == "__main__":
    sys.exit(main())
