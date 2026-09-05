"""災害救助判準進入新引擎（MatchingProfile）後的行為。

先前 loss_rate／land_doc／policy_enrolled_2y 只存在於 fields.json，
新引擎看不到，導致「損失幾成」與豁免條款無法參與比對。
這組測試釘住三件事：欄位被正式接受、提問是白話、選項有帶出來。
"""
from datetime import date

from aidstation.fields import load_fields
from aidstation.knowledge import load_programs
from aidstation.matching import match_profile
from aidstation.schemas import MatchingProfile

TODAY = date(2026, 9, 5)          # 示範公告期 9/05–9/11 之內
PROGRAMS = load_programs(fields=load_fields())
DISASTER = "農業天然災害現金救助"

BASE = {"crops": ["芒果"], "location": "玉井區", "disaster_situation": "天然災害",
        "is_farming": True}


def _disaster(profile):
    result = match_profile(PROGRAMS, profile, asked=[], today=TODAY)
    return next(r for r in result["results"] if DISASTER in r["name"])


def test_三個欄位是正式宣告不是extra():
    for field in ("loss_rate", "land_doc", "policy_enrolled_2y"):
        assert field in MatchingProfile.model_fields, f"{field} 應為正式欄位"


def test_沒給損失成數時會問而且是白話():
    r = _disaster({**BASE, "land_tenure": "自有"})
    assert r["status"] == "NEED_INFO"
    questions = {m["key"]: m["question"] for m in r["missing_info"]}
    assert "loss_rate" in questions
    # 不可以出現欄位代號，長輩看不懂
    assert "loss_rate" not in questions["loss_rate"]
    assert questions["loss_rate"] == "大概損失幾成？"


def test_提問要帶白話選項讓長輩用按的():
    r = _disaster({**BASE, "land_tenure": "自有"})
    by_key = {m["key"]: m for m in r["missing_info"]}
    assert by_key["loss_rate"]["options"] == ["兩成以下", "兩成到一半", "超過一半", "幾乎全滅"]
    # 選項要能轉回內部值，否則答了也沒用
    assert by_key["loss_rate"]["option_map"]["超過一半"] == 0.6
    assert by_key["policy_enrolled_2y"]["options"] == ["有", "沒有", "不確定"]


def test_給了損失成數就比得出來():
    assert _disaster({**BASE, "land_tenure": "自有", "loss_rate": 0.6})["status"] == "MATCH"


def test_豁免條款_口頭租約加近兩年申報也算數():
    """設計建議書的關鍵價值：曾申報政策者免附土地文件。"""
    r = _disaster({**BASE, "land_tenure": "口頭租約", "loss_rate": 0.6,
                   "policy_enrolled_2y": True})
    assert r["status"] == "MATCH"


def test_公告期外要顯示已截止():
    result = match_profile(PROGRAMS, {**BASE, "land_tenure": "自有", "loss_rate": 0.6},
                           asked=[], today=date(2026, 10, 1))
    r = next(x for x in result["results"] if DISASTER in x["name"])
    assert r["status"] == "CLOSED"
