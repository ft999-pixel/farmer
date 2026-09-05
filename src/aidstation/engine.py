"""三值邏輯規則引擎：符合／可能符合（未知）／不符合。

設計依據《系統設計建議書》§2.2：
- LLM 從頭到尾不回答「你符不符合資格」，判定只在這裡發生。
- 「未知」不是缺陷，而是下一題提問從哪來的依據。
- 每條判定結果附法條依據（legal_ref），可回溯。

條件樹格式（與補助 schema 的 eligibility 一致）：
    葉節點： {"field": "crop", "op": "in", "value": ["芒果"], "legal_ref": "..."}
    群組：   {"all": [節點, ...]} 或 {"any": [節點, ...]}
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class Tri(str, Enum):
    YES = "符合"
    NO = "不符合"
    UNKNOWN = "未知"


# 否定型運算子：多值事實要「全部成立」才算通過，不能只看其中一項
_NEGATIVE_OPS = ("!=", "not_in")


def _leaf_ok(op: str, actual: Any, target: Any) -> bool:
    # 事實本身可能是多值（一個農民種好幾種作物）。
    # 正向條件：任一項成立就算符合（種了芒果和文旦，芒果的救助就適用）。
    # 否定條件：必須每一項都成立（「作物不得為芒果」時，有種芒果就是不符合）。
    if isinstance(actual, list):
        judge = all if op in _NEGATIVE_OPS else any
        return judge(_leaf_ok(op, item, target) for item in actual)
    if op == "=":
        return actual == target
    if op == "!=":
        return actual != target
    if op == "in":
        return actual in target
    if op == "not_in":
        return actual not in target
    if op == ">=":
        return float(actual) >= float(target)
    if op == "<=":
        return float(actual) <= float(target)
    if op == ">":
        return float(actual) > float(target)
    if op == "<":
        return float(actual) < float(target)
    raise ValueError(f"未知運算子：{op}")


def eval_node(node: dict, facts: dict[str, Any], trace: list[dict] | None = None) -> Tri:
    """遞迴評估條件樹。trace 收集所有葉節點的評估結果供上層歸因。"""
    if "all" in node:
        results = [eval_node(child, facts, trace) for child in node["all"]]
        if Tri.NO in results:
            return Tri.NO
        if Tri.UNKNOWN in results:
            return Tri.UNKNOWN
        return Tri.YES
    if "any" in node:
        results = [eval_node(child, facts, trace) for child in node["any"]]
        if Tri.YES in results:
            return Tri.YES
        if Tri.UNKNOWN in results:
            return Tri.UNKNOWN
        return Tri.NO
    # 葉節點
    field = node["field"]
    value = facts.get(field)
    # 空清單＝還沒選任何一項，等同未知；不能當成「都不符合」
    if field not in facts or value is None or (isinstance(value, list) and not value):
        result = Tri.UNKNOWN
    else:
        result = Tri.YES if _leaf_ok(node["op"], value, node["value"]) else Tri.NO
    if trace is not None:
        trace.append({**node, "result": result})
    return result


def match_program(program: dict, facts: dict[str, Any]) -> dict:
    """比對單一補助，回傳結構化結果。

    status：符合／可能符合／不符合
    unknown_fields：導致「可能符合」的未確認欄位
    failed：導致「不符合」的條件（附 legal_ref）
    documents：應備文件，含豁免判定（exempt_if 欄位為真即標記免附）
    """
    trace: list[dict] = []
    overall = eval_node(program["eligibility"], facts, trace)

    unknown_fields = sorted({t["field"] for t in trace if t["result"] == Tri.UNKNOWN}) \
        if overall == Tri.UNKNOWN else []
    failed = [
        {"field": t["field"], "op": t["op"], "value": t["value"],
         "legal_ref": t.get("legal_ref"), "note": t.get("note")}
        for t in trace if t["result"] == Tri.NO
    ] if overall == Tri.NO else []

    documents = []
    for doc in program.get("documents", []):
        exempt_field = doc.get("exempt_if")
        exempt = bool(exempt_field and facts.get(exempt_field) is True)
        documents.append({**doc, "exempt": exempt})

    status = {Tri.YES: "符合", Tri.UNKNOWN: "可能符合", Tri.NO: "不符合"}[overall]
    return {
        "program_id": program["id"],
        "name": program["name"],
        "category": program.get("category"),
        "status": status,
        "unknown_fields": unknown_fields,
        "failed": failed,
        "documents": documents,
        "window": program.get("window"),
        "amount": program.get("amount"),
        "authority": program.get("authority"),
        "source": program.get("source"),
    }


def match_all(programs: list[dict], facts: dict[str, Any]) -> list[dict]:
    """比對全部補助，依 符合 → 可能符合 → 不符合 排序。"""
    order = {"符合": 0, "可能符合": 1, "不符合": 2}
    results = [match_program(p, facts) for p in programs]
    results.sort(key=lambda r: order[r["status"]])
    return results


def next_question(results: list[dict], fields: dict[str, dict],
                  asked: set[str] | None = None,
                  today: "object | None" = None) -> dict | None:
    """缺口驅動提問：優先問「期限最近的補助」缺的欄位。

    排序：① 該欄位所卡住的補助中，最近的截止日（災害救助剩 4 天 > 常態補助）
    　　　② 卡住的補助數（頻率）③ 欄位字典註冊順序。
    題數有限（3~5 題），先解急的——這是設計原則「期限就是金錢」的落實。
    回傳 {"field", "question", "options"}；沒有可問的則回傳 None。
    """
    from datetime import date as _date
    asked = asked or set()
    today = today or _date.today()
    stats: dict[str, tuple[int, int]] = {}  # field -> (count, min_days_to_close)
    for r in results:
        if r["status"] != "可能符合":
            continue
        window = r.get("window") or {}
        urgency = 9999
        if window.get("type") == "公告型" and window.get("close"):
            try:
                urgency = max((_date.fromisoformat(window["close"]) - today).days, 0)
            except (ValueError, TypeError):
                pass
        for f in r["unknown_fields"]:
            if f in asked or f not in fields:
                continue
            count, min_urgency = stats.get(f, (0, 9999))
            stats[f] = (count + 1, min(min_urgency, urgency))
    if not stats:
        return None
    field_order = {name: i for i, name in enumerate(fields)}
    best = min(stats, key=lambda f: (stats[f][1], -stats[f][0], field_order.get(f, 999)))
    spec = fields[best]
    return {
        "field": best,
        "question": spec.get("question", f"請問你的「{spec.get('label', best)}」是？"),
        "options": spec.get("options") or spec.get("values"),
        "type": spec.get("type"),
    }


def match_profile(programs: list, profile, *, asked=None, today=None, matcher=None):
    """Canonical MatchingProfile pipeline, kept importable from the engine.

    The original engine API above remains the compatibility path used by the
    LINE/web Flow. Importing lazily avoids a cycle because the new matcher uses
    ``eval_node`` for legacy eligibility trees.
    """
    from .matching import match_profile as _match_profile
    return _match_profile(programs, profile, asked=asked, today=today, matcher=matcher)


match_matching_profile = match_profile
