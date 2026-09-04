"""規則引擎測試：三值邏輯、豁免路徑、缺口驅動提問。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aidstation.engine import Tri, eval_node, match_all, match_program, next_question
from aidstation.fields import load_fields, normalize_facts
from aidstation.knowledge import load_programs

FIELDS = load_fields()
PROGRAMS = load_programs(fields=FIELDS)
DISASTER = next(p for p in PROGRAMS if p["id"] == "moa-disaster-cash-sample-2026")

BASE = {"event": "天然災害", "crop": "芒果", "township": "玉井區", "loss_rate": 0.6}


def test_exemption_path_oral_lease():
    """口頭租約＋政策登錄 → 豁免條款成立 → 符合，且土地文件標記免附。"""
    facts = {**BASE, "land_tenure": "口頭租約", "land_doc": "無", "policy_enrolled_2y": True}
    r = match_program(DISASTER, facts)
    assert r["status"] == "符合"
    land_doc = next(d for d in r["documents"] if d["name"] == "土地合法使用證明")
    assert land_doc["exempt"] is True


def test_unknown_drives_maybe():
    """口頭租約、登錄狀態未知 → 可能符合，未知欄位含 policy_enrolled_2y。"""
    facts = {**BASE, "land_tenure": "口頭租約", "land_doc": "無"}
    r = match_program(DISASTER, facts)
    assert r["status"] == "可能符合"
    assert "policy_enrolled_2y" in r["unknown_fields"]


def test_fail_with_legal_ref():
    """損失率 10% → 不符合，且附法條依據。"""
    facts = {**BASE, "loss_rate": 0.1, "land_tenure": "自有"}
    r = match_program(DISASTER, facts)
    assert r["status"] == "不符合"
    assert any("§6" in (f.get("legal_ref") or "") for f in r["failed"])


def test_any_no_dominated_by_yes():
    """any 群組：一個 NO 不影響其他 YES。"""
    node = {"any": [{"field": "a", "op": "=", "value": 1},
                    {"field": "b", "op": "=", "value": 2}]}
    assert eval_node(node, {"a": 9, "b": 2}) == Tri.YES
    assert eval_node(node, {"a": 9, "b": 9}) == Tri.NO
    assert eval_node(node, {"a": 9}) == Tri.UNKNOWN


def test_alias_normalization():
    """台語別名：檨仔 → 芒果。"""
    facts = normalize_facts({"crop": "檨仔"}, FIELDS)
    assert facts["crop"] == "芒果"


def test_next_question_targets_biggest_gap():
    """缺口驅動提問：只給作物與災害 → 應追問而非亂猜。"""
    facts = normalize_facts({"crop": "芒果", "event": "天然災害"}, FIELDS)
    results = match_all(PROGRAMS, facts)
    q = next_question(results, FIELDS, asked=set(facts))
    assert q is not None
    assert q["field"] not in facts


def test_question_loop_converges():
    """最多 5 題內收斂（設計原則）。"""
    facts = normalize_facts({"crop": "芒果", "event": "天然災害"}, FIELDS)
    answers = {"township": "玉井區", "loss_rate": 0.6, "land_tenure": "口頭租約",
               "land_doc": "無", "policy_enrolled_2y": True, "is_farming": True,
               "insured_farmer": True, "age": 65}
    asked = set()
    for _ in range(5):
        results = match_all(PROGRAMS, facts)
        q = next_question(results, FIELDS, asked=asked | set(facts))
        if q is None:
            break
        asked.add(q["field"])
        if q["field"] in answers:
            facts[q["field"]] = answers[q["field"]]
    final = match_all(PROGRAMS, facts)
    assert not any(r["status"] == "可能符合" and "township" in r["unknown_fields"]
                   for r in final)
