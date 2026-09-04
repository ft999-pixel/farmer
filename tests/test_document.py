"""公文白話化測試：受控欄位、期限兩型分流、絕不猜原則。"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aidstation.document import (RegexDocumentTranslator, build_plain_card,
                                 roc_to_date, sanitize_doc)

SAMPLE_WENDAO = """發文機關：○○縣政府農業處
主旨：所報損害面積與現地勘查未合，請於文到7日內檢具佐證資料到府說明。
說明：一、依農產業天然災害救助作業要點辦理。
二、請檢附災損照片及土地使用證明文件。
三、逾期未補正者，駁回其申請。"""

SAMPLE_EXPLICIT = """發文機關：○○區公所
主旨：受理天然災害現金救助申請。
說明：請於115年8月20日前向本所農業課提出申請。"""


def test_roc_date():
    assert roc_to_date("請於115年8月20日前") == date(2026, 8, 20)
    assert roc_to_date("沒有日期") is None


def test_wendao_type_asks_received_date():
    """文到型：沒給收文日 → 卡片必須反問，不得出現推算結果。"""
    doc = RegexDocumentTranslator().translate(SAMPLE_WENDAO)
    assert doc["doc_type"] == "補正通知"
    card = build_plain_card(doc, today=date(2026, 8, 10))
    assert card["deadline"]["type"] == "文到型"
    assert card["deadline"]["ask_received_date"] is True
    assert "deadline" not in card["deadline"].get("calc", "")


def test_wendao_with_received_date_shows_calc():
    """給了收文日 → 白話計算式。8/5 收到＋7日＝8/12 前。"""
    doc = RegexDocumentTranslator().translate(SAMPLE_WENDAO)
    card = build_plain_card(doc, received_date=date(2026, 8, 5), today=date(2026, 8, 10))
    assert card["deadline"]["deadline"] == "2026-08-12"
    assert "8/5 收到" in card["deadline"]["calc"]


def test_explicit_date_counts_down_without_asking():
    """公告型（民國明確日期）→ 直接倒數，不問收文日。"""
    doc = RegexDocumentTranslator().translate(SAMPLE_EXPLICIT)
    assert doc["deadline_date"] == "2026-08-20"
    card = build_plain_card(doc, today=date(2026, 8, 10))
    assert card["deadline"]["type"] == "公告型"
    assert card["deadline"]["days_left"] == 10


def test_no_deadline_never_guesses():
    """完全沒期限 → 導向承辦電話，絕不猜。"""
    card = build_plain_card({"conclusion": "х", "todo": []}, today=date(2026, 8, 10))
    assert card["deadline"]["type"] == "未知"
    assert "電洽" in card["deadline"]["advice"]


def test_consequence_and_todo_extracted():
    doc = RegexDocumentTranslator().translate(SAMPLE_WENDAO)
    assert "駁回" in (doc["consequence"] or "")
    assert any("災損照片" in t["item"] for t in doc["todo"])


def test_sanitize_drops_extra_keys():
    """受控輸出：LLM 多給的鍵一律丟棄。"""
    doc = sanitize_doc({"conclusion": "ok", "todo": ["補件"],
                        "hallucinated_advice": "放棄吧", "eligible": False})
    assert "hallucinated_advice" not in doc and "eligible" not in doc
    assert doc["todo"] == [{"item": "補件", "where": None}]
