"""多值事實測試：一個農民可能同時種好幾種作物。

這裡釘住的是安全性質——多值不能造成「假的不符合」。
農民被錯誤告知不符合，比沒查到還糟：他會直接放棄申請。
"""
from aidstation.engine import Tri, eval_node, match_program
from aidstation.fields import load_fields, normalize_facts

FIELDS = load_fields()
MANGO_ONLY = {"field": "crop", "op": "in", "value": ["芒果"]}
NOT_MANGO = {"field": "crop", "op": "not_in", "value": ["芒果"]}


def test_多種作物只要其中一種符合就算符合():
    assert eval_node(MANGO_ONLY, {"crop": ["芒果", "文旦"]}) is Tri.YES
    assert eval_node(MANGO_ONLY, {"crop": ["文旦", "絲瓜"]}) is Tri.NO


def test_單一作物行為不變():
    assert eval_node(MANGO_ONLY, {"crop": "芒果"}) is Tri.YES
    assert eval_node(MANGO_ONLY, {"crop": "水稻"}) is Tri.NO


def test_否定條件要全部成立才通過():
    """「作物不得為芒果」：有種芒果就是不符合，不能因為還種了別的就放行。"""
    assert eval_node(NOT_MANGO, {"crop": ["文旦", "絲瓜"]}) is Tri.YES
    assert eval_node(NOT_MANGO, {"crop": ["芒果", "文旦"]}) is Tri.NO


def test_空清單算未知不算不符合():
    """還沒選作物 ≠ 作物都不符合。錯判成不符合會讓農民直接放棄。"""
    assert eval_node(MANGO_ONLY, {"crop": []}) is Tri.UNKNOWN
    assert eval_node(MANGO_ONLY, {}) is Tri.UNKNOWN
    assert eval_node(MANGO_ONLY, {"crop": None}) is Tri.UNKNOWN


def test_別名在複選時逐項套用():
    facts = normalize_facts({"crop": ["檨仔", "文旦"]}, FIELDS)
    assert facts["crop"] == ["芒果", "文旦"]


def test_複選走完整比對流程():
    program = {
        "id": "t", "name": "測試", "source": {},
        "eligibility": {"all": [
            {"field": "crop", "op": "in", "value": ["芒果"]},
            {"field": "is_farming", "op": "=", "value": True},
        ]},
    }
    facts = normalize_facts({"crop": ["檨仔", "絲瓜"], "is_farming": "有"}, FIELDS)
    assert match_program(program, facts)["status"] == "符合"
