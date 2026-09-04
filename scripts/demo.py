"""終端機互動 Demo：模擬「我的芒果全掉了」的完整對話流程。

執行：PYTHONPATH=src python scripts/demo.py
（未接 LLM 前，以關鍵字比對模擬語意抽取；正式版由 LLM 受控輸出取代 naive_extract。）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aidstation.engine import match_all, next_question  # noqa: E402
from aidstation.fields import load_fields, normalize_facts  # noqa: E402
from aidstation.knowledge import load_programs  # noqa: E402


def naive_extract(text: str, fields: dict) -> dict:
    """極簡關鍵字抽取（LLM 佔位）。"""
    facts: dict = {}
    crop_spec = fields["crop"]
    for name in list(crop_spec["values"]) + list(crop_spec.get("aliases", {})):
        if name in text:
            facts["crop"] = name
            break
    if any(k in text for k in ("掉", "落", "淹", "倒", "災", "風", "雨")):
        facts["event"] = "天然災害"
    if any(k in text for k in ("受傷", "跌倒", "割到")):
        facts["event"] = "職業傷害"
    return facts


def ask(question: dict) -> object:
    print(f"\n👉 {question['question']}")
    options = question.get("options")
    if options:
        for i, opt in enumerate(options, 1):
            print(f"   {i}. {opt}")
        choice = input("選擇（輸入數字，直接 Enter 跳過）：").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        return None
    return input("回答（直接 Enter 跳過）：").strip() or None


def main() -> None:
    fields = load_fields()
    programs = load_programs(fields=fields)

    print("🌾 農民補給站（核心引擎 Demo）")
    text = input("請描述你的處境（例：我的檨仔攏落了了）：").strip() or "我的檨仔攏落了了"
    facts = normalize_facts(naive_extract(text, fields), fields)
    print(f"（抽取到的條件：{facts}）")

    asked: set[str] = set()
    for _ in range(5):  # 最多 5 題（設計原則：3~5 題內必出結果）
        results = match_all(programs, facts)
        question = next_question(results, fields, asked=asked | set(facts))
        if question is None:
            break
        answer = ask(question)
        asked.add(question["field"])
        if answer is None:
            continue
        spec = fields[question["field"]]
        mapped = spec.get("option_map", {}).get(answer, answer)
        if mapped == "不確定":
            continue
        facts.update(normalize_facts({question["field"]: mapped}, fields))

    print("\n" + "=" * 46)
    for r in match_all(programs, facts):
        icon = {"符合": "✅", "可能符合": "⚠️ ", "不符合": "❌"}[r["status"]]
        print(f"\n{icon} {r['status']}｜{r['name']}")
        if r["status"] == "符合":
            for doc in r["documents"]:
                tag = "（免附！豁免條款）" if doc["exempt"] else f"（{doc['where']}）"
                print(f"    📄 {doc['name']}{tag}")
            w = r.get("window") or {}
            if w.get("close"):
                print(f"    ⏰ 受理至 {w['close']}")
            a = r.get("authority") or {}
            print(f"    📞 {a.get('agency', '')} {a.get('tel', '')}")
        elif r["status"] == "可能符合":
            print(f"    還差這些沒確認：{'、'.join(r['unknown_fields'])}")
        else:
            for f in r["failed"]:
                print(f"    原因：{f['field']} 不符（依據：{f.get('legal_ref') or '—'}）")
    print("\n（每張卡片下方都有「我卡住了」鍵 → 求助頁）")
    print("※ 本建議不具行政效力，最終以承辦機關公告為準。")


if __name__ == "__main__":
    main()
