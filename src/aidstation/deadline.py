"""期限計算：兩型分流（《系統設計建議書》§2.4）。

- 公告型：起迄日期明確 → 直接倒數，不提問。
- 文到型：「文到○日內」「自送達之翌日起○個工作日內」→ 必須先取得收文日再推算，
  並回傳白話計算式，畫面須原樣顯示。

第一安全原則：算錯期限比功能不存在更糟。所以：
- 工作日與日曆日分開處理，工作日需接假日行事曆（data/holidays.json）。
- 解析不出規則就回傳 None，由呼叫端導向「請向承辦確認」＋電話，絕不猜。
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_RULE = re.compile(r"(?:文到|送達之?翌日起?|收文(?:之日)?起?)\s*(\d+)\s*(?:個)?\s*(工作)?日\s*內?")


def load_holidays(path: Path | None = None) -> set[date]:
    p = path or (DATA_DIR / "holidays.json")
    if not p.exists():
        return set()
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return {date.fromisoformat(d) for d in data.get("holidays", [])}


def parse_rule(rule: str) -> dict | None:
    """解析文到型規則。回傳 {"days": int, "workdays": bool}；解析失敗回 None。"""
    m = _RULE.search(rule or "")
    if not m:
        return None
    return {"days": int(m.group(1)), "workdays": m.group(2) is not None}


def _add_workdays(start: date, days: int, holidays: set[date]) -> date:
    d, remaining = start, days
    while remaining > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in holidays:
            remaining -= 1
    return d


def deadline_from_received(received: date, rule: str,
                           holidays: set[date] | None = None) -> dict | None:
    """文到型：由收文日推算期限，回傳期限與白話計算式。"""
    parsed = parse_rule(rule)
    if parsed is None:
        return None
    holidays = holidays if holidays is not None else load_holidays()
    if parsed["workdays"]:
        due = _add_workdays(received, parsed["days"], holidays)
        unit = "個工作日"
    else:
        due = received + timedelta(days=parsed["days"])
        unit = "日"
    calc = (f"{received.month}/{received.day} 收到 ＋ {parsed['days']}{unit}"
            f" ＝ {due.month}/{due.day} 前要完成")
    return {"deadline": due.isoformat(), "calc": calc, "workdays": parsed["workdays"]}


def countdown(close: date, today: date | None = None) -> dict:
    """公告型：直接倒數。3 天內介面轉紅（urgent）。"""
    today = today or date.today()
    days_left = (close - today).days
    return {
        "close": close.isoformat(),
        "days_left": days_left,
        "expired": days_left < 0,
        "urgent": 0 <= days_left <= 3,
        "text": ("已截止" if days_left < 0 else f"{close.month}/{close.day} 前（剩 {days_left} 天）"),
    }
