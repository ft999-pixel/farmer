"""期限計算測試：兩型分流、工作日、解析失敗不猜。"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aidstation.deadline import countdown, deadline_from_received, parse_rule


def test_calendar_days():
    """文到7日內：7/21 收到 → 7/28 前。"""
    r = deadline_from_received(date(2026, 7, 21), "請於文到7日內檢具佐證資料", holidays=set())
    assert r["deadline"] == "2026-07-28"
    assert "7/21 收到" in r["calc"] and "7/28 前" in r["calc"]


def test_workdays_skip_weekend():
    """文到3個工作日內：週五收到 → 跳過週末 → 下週三。"""
    r = deadline_from_received(date(2026, 8, 7), "文到3個工作日內", holidays=set())  # 8/7 是週五
    assert r["deadline"] == "2026-08-12"


def test_workdays_skip_holiday():
    """工作日計算需跳過國定假日。"""
    r = deadline_from_received(date(2026, 9, 24), "文到2個工作日內",
                               holidays={date(2026, 9, 25)})  # 9/25 假日、9/26-27 週末
    assert r["deadline"] == "2026-09-29"


def test_unparseable_returns_none():
    """解析不出就回 None——絕不猜，由呼叫端導向承辦電話。"""
    assert deadline_from_received(date(2026, 8, 1), "依相關規定辦理") is None
    assert parse_rule("") is None


def test_countdown_urgent():
    c = countdown(date(2026, 8, 12), today=date(2026, 8, 10))
    assert c["days_left"] == 2 and c["urgent"] and not c["expired"]
    assert countdown(date(2026, 8, 1), today=date(2026, 8, 10))["expired"]
