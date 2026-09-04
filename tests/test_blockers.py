"""卡點統計庫測試：歸類、去識別化寫入、儀表板三張圖的聚合。"""
from datetime import date, timedelta

from aidstation import blockers


def test_classify_公文常見理由():
    assert blockers.classify("請於文到7日內補正，未檢附土地權利證明") == "缺件補正"
    assert blockers.classify("台端申請已逾申請期限，不予受理") == "超過申請期限"
    assert blockers.classify("經審核資格不符，不予核發") == "資格不符"
    assert blockers.classify("核減為新臺幣 3 萬元") == "金額核減"


def test_classify_我卡住了三選項():
    for reason in ("太麻煩了", "文件生不出來", "看不懂"):
        assert blockers.classify(reason) == reason


def test_classify_歸不出來就是其他_不猜():
    assert blockers.classify("貴單位惠請查照") == blockers.OTHER
    assert blockers.classify("") == blockers.OTHER


def test_record_只存去識別化欄位():
    row = blockers.record("缺件補正", blockers.SOURCE_DOC,
                          category="災害救助", township="玉井區", level="縣市")
    assert set(row) == {"date", "reason", "source", "category", "township", "level"}


def test_classify_level_發文機關分中央地方():
    assert blockers.classify_level("臺南市玉井區公所") == blockers.LEVEL_LOCAL
    assert blockers.classify_level("行政院農業部農糧署") == blockers.LEVEL_CENTRAL
    assert blockers.classify_level("某某民間協會") is None


def test_record_from_doc_由發文機關推出層級():
    row = blockers.record_from_doc({"issuer": "臺南市玉井區公所",
                                    "conclusion": "請補附土地權利證明文件"})
    assert row["level"] == blockers.LEVEL_LOCAL


def test_record_from_doc_歸不出原因就不記():
    before = len(blockers.load())
    assert blockers.record_from_doc({"conclusion": "惠請查照", "todo": []}) is None
    assert len(blockers.load()) == before


def test_record_from_doc_抓到補正就入庫():
    row = blockers.record_from_doc({"doc_type": "補正通知",
                                    "conclusion": "請補附土地權利證明文件",
                                    "todo": [{"item": "檢附土地謄本"}]},
                                   category="災害救助")
    assert row["reason"] == "缺件補正"
    assert row["source"] == blockers.SOURCE_DOC


def test_stats_四張圖的資料齊全():
    today = date(2026, 9, 4)
    blockers.record("缺件補正", blockers.SOURCE_DOC, category="災害救助",
                    level="縣市", on=today)
    blockers.record("缺件補正", blockers.SOURCE_DOC, category="災害救助",
                    level="中央", on=today)
    blockers.record("看不懂", blockers.SOURCE_STUCK, category="農民福利",
                    on=today - timedelta(weeks=1))

    s = blockers.stats(weeks=4, today=today)
    assert s["total"] == 3
    # ① 原因排行
    assert s["ranking"][0] == {"reason": "缺件補正", "count": 2, "by_source": {"公文": 2}}
    # ② 補助類別排行（含該類最常見卡點）
    assert s["by_category"][0] == {"category": "災害救助", "count": 2,
                                   "top_reason": "缺件補正", "top_count": 2}
    # ③ 中央 vs 縣市
    lv = s["by_level"]
    assert lv["rows"][0] == {"reason": "缺件補正", "中央": 1, "縣市": 1}
    assert lv["totals"] == {"中央": 1, "縣市": 1}
    assert lv["unknown"] == 1        # 「看不懂」那筆沒有層級
    # ④ 交叉表維度：類別 × 原因
    m = s["matrix"]
    assert len(m["cells"]) == len(m["categories"])
    assert all(len(row) == len(m["reasons"]) for row in m["cells"])


def test_stats_期間外的資料不算():
    today = date(2026, 9, 4)
    blockers.record("看不懂", blockers.SOURCE_STUCK, on=today - timedelta(weeks=20))
    assert blockers.stats(weeks=4, today=today)["total"] == 0
