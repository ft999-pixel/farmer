"""語意抽取層測試：關鍵字後備與幻覺防火牆。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aidstation.extract import KeywordExtractor, validate_facts
from aidstation.fields import load_fields

FIELDS = load_fields()


def test_keyword_taigi():
    """台語口語 → 正確欄位。"""
    facts = KeywordExtractor(FIELDS).extract("阮的檨仔攏落了了")
    assert facts == {"crop": "芒果", "event": "天然災害"}


def test_keyword_injury():
    facts = KeywordExtractor(FIELDS).extract("我在果園跌倒受傷了")
    assert facts["event"] == "職業傷害"


def test_firewall_drops_unregistered_fields():
    """LLM 自作主張的判定欄位必須被丟棄——判定只發生在規則引擎。"""
    raw = {"crop": "芒果", "status": "符合", "eligible": True, "amount": 90000}
    cleaned = validate_facts(raw, FIELDS)
    assert cleaned == {"crop": "芒果"}


def test_firewall_drops_illegal_enum():
    """幻覺出來的作物名（不在合法值清單）必須被丟棄。"""
    cleaned = validate_facts({"crop": "火星果", "event": "天然災害"}, FIELDS)
    assert "crop" not in cleaned
    assert cleaned["event"] == "天然災害"


def test_firewall_normalizes_alias_then_validates():
    cleaned = validate_facts({"crop": "檨仔"}, FIELDS)
    assert cleaned["crop"] == "芒果"


def test_firewall_drops_bad_types():
    cleaned = validate_facts({"loss_rate": "很多", "age": "abc"}, FIELDS)
    assert cleaned == {}
