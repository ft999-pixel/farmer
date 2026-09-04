"""卡點統計庫（功能三後半，《系統設計建議書》§5.2）。

兩個資料來源：
- 「我卡住了」三選項（太麻煩了／文件生不出來／看不懂）——農民自述
- 公文白話化的結論欄位——公文寫的駁回／補正理由（資格不符、缺件、逾期…）

去識別化在寫入當下發生（§9）：只存原因、來源、補助類別、鄉鎮、日期，
不存 session、不存原文、不存身分。庫裡有卡點、沒有人。

儲存用 append-only JSONL（MVP）；正式版換資料庫時只需替換 _append／load。
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

STORE = Path(__file__).resolve().parents[2] / "data" / "blockers.jsonl"


def _store() -> Path:
    """測試與多環境用：AIDSTATION_BLOCKERS 可改寫存放位置，預設 data/blockers.jsonl。"""
    return Path(os.environ.get("AIDSTATION_BLOCKERS") or STORE)

# 卡點原因字典。順序＝比對優先序（越前面越具體），也＝報表顯示順序。
REASONS: list[tuple[str, tuple[str, ...]]] = [
    ("超過申請期限", ("逾期", "逾申請期限", "已截止", "過期", "期限已屆", "逾限")),
    ("缺件補正", ("補正", "檢具", "檢附", "補件", "未檢附", "缺漏", "資料不全", "補附")),
    ("資格不符", ("資格不符", "不符合", "未符合", "不合規定", "不予受理", "不予核發", "駁回")),
    ("金額核減", ("核減", "減列", "不足額", "部分核准", "酌減")),
    ("查核未過", ("勘查", "勘災", "查核不符", "現場查證", "實地查核")),
    ("重複請領", ("重複", "已領取", "同一事由")),
    # 以下三項來自「我卡住了」三選項，字面即答案
    ("太麻煩了", ("太麻煩",)),
    ("文件生不出來", ("文件生不出來",)),
    ("看不懂", ("看不懂",)),
]
OTHER = "其他"
LABELS = [r for r, _ in REASONS] + [OTHER]

SOURCE_STUCK = "我卡住了"
SOURCE_DOC = "公文"

# 機關層級：卡點發生在中央政策，還是地方執行？兩者要處理的人不同。
LEVEL_CENTRAL, LEVEL_LOCAL = "中央", "縣市"
_LOCAL_HINTS = ("區公所", "鄉公所", "鎮公所", "市公所", "縣政府", "市政府",
                "農業局", "農業處", "區農會", "鄉農會", "鎮農會")
_CENTRAL_HINTS = ("農業部", "農糧署", "漁業署", "林業署", "農業金融署",
                  "防檢署", "勞保局", "水保署")


def classify_level(text: str) -> str | None:
    """從發文機關判斷層級。分不出來就回 None——不猜。"""
    text = text or ""
    if any(h in text for h in _LOCAL_HINTS):
        return LEVEL_LOCAL
    if any(h in text for h in _CENTRAL_HINTS):
        return LEVEL_CENTRAL
    return None


def classify(text: str) -> str:
    """把公文原文或使用者選項歸類成卡點原因；抓不到就是「其他」——不猜。"""
    text = text or ""
    for reason, keywords in REASONS:
        if any(k in text for k in keywords):
            return reason
    return OTHER


def record(reason: str, source: str, *, category: str | None = None,
           township: str | None = None, level: str | None = None,
           on: date | None = None) -> dict:
    """寫入一筆去識別化卡點。回傳寫入的內容（測試與 API 回應用）。"""
    row = {
        "date": (on or date.today()).isoformat(),
        "reason": reason if reason in LABELS else OTHER,
        "source": source,
        "category": category,
        "township": township,
        "level": level if level in (LEVEL_CENTRAL, LEVEL_LOCAL) else None,
    }
    path = _store()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def record_from_doc(doc: dict, **kw) -> dict | None:
    """從公文抽取欄位歸類卡點。歸不出具體原因就不記——寧可少一筆，不要髒資料。

    層級取自發文機關：擋住民眾的是中央公文還是地方公所，處理的人不一樣。
    """
    text = " ".join(str(doc.get(k) or "") for k in ("doc_type", "conclusion", "consequence"))
    text += " " + " ".join(t.get("item", "") for t in (doc.get("todo") or []))
    reason = classify(text)
    if reason == OTHER:
        return None
    kw.setdefault("level", classify_level(doc.get("issuer") or ""))
    return record(reason, SOURCE_DOC, **kw)


def load() -> list[dict]:
    path = _store()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def stats(weeks: int = 8, today: date | None = None) -> dict:
    """儀表板四張圖的資料：原因排行、補助類別、中央vs縣市、類別×原因交叉。"""
    today = today or date.today()
    rows = load()
    since = _monday(today) - timedelta(weeks=weeks - 1)
    recent = [r for r in rows if r.get("date", "") >= since.isoformat()]

    ranking = Counter(r["reason"] for r in recent)
    by_source: dict[str, Counter] = defaultdict(Counter)
    for r in recent:
        by_source[r["reason"]][r.get("source") or "其他"] += 1

    # 補助類別排行：哪一類補助最卡人，並標出該類最常見的卡點
    cat_total = Counter(r["category"] for r in recent if r.get("category"))
    cat_reason: dict[str, Counter] = defaultdict(Counter)
    for r in recent:
        if r.get("category"):
            cat_reason[r["category"]][r["reason"]] += 1

    # 中央 vs 縣市：同一個卡點原因，兩個層級各發生幾次
    level_reason: dict[str, Counter] = defaultdict(Counter)
    for r in recent:
        if r.get("level"):
            level_reason[r["reason"]][r["level"]] += 1

    matrix: Counter = Counter()
    categories: list[str] = []
    for r in recent:
        cat = r.get("category")
        if not cat:
            continue
        if cat not in categories:
            categories.append(cat)
        matrix[(cat, r["reason"])] += 1

    # 排行榜順序決定另外兩張圖的圖例順序，三張圖顏色才對得起來
    ordered = [r for r, _ in ranking.most_common()]
    levelled = [r for r in ordered if level_reason[r]]
    return {
        "total": len(recent),
        "ranking": [{"reason": r, "count": ranking[r],
                     "by_source": dict(by_source[r])} for r in ordered],
        "by_category": [
            {"category": c, "count": n,
             "top_reason": cat_reason[c].most_common(1)[0][0],
             "top_count": cat_reason[c].most_common(1)[0][1]}
            for c, n in cat_total.most_common()],
        "by_level": {
            "levels": [LEVEL_CENTRAL, LEVEL_LOCAL],
            "rows": [{"reason": r,
                      "中央": level_reason[r][LEVEL_CENTRAL],
                      "縣市": level_reason[r][LEVEL_LOCAL]} for r in levelled],
            "totals": {
                LEVEL_CENTRAL: sum(level_reason[r][LEVEL_CENTRAL] for r in levelled),
                LEVEL_LOCAL: sum(level_reason[r][LEVEL_LOCAL] for r in levelled),
            },
            "unknown": sum(1 for r in recent if not r.get("level")),
        },
        "matrix": {
            "categories": categories,
            "reasons": ordered,
            "cells": [[matrix[(c, r)] for r in ordered] for c in categories],
        },
        "townships": Counter(r["township"] for r in recent if r.get("township")).most_common(10),
    }
