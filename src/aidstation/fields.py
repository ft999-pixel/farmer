"""欄位字典：整個系統的中樞。

LLM 抽取、規則引擎、對話提問共用同一套欄位定義（data/fields.json）。
新增補助時若需要新欄位，先在 fields.json 註冊，再寫進補助資料。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_fields(path: Path | None = None) -> dict[str, dict]:
    """載入欄位字典。回傳 {欄位名: 定義} 的有序 dict（順序即提問優先序的最後依據）。"""
    p = path or (DATA_DIR / "fields.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def normalize_facts(raw: dict[str, Any], fields: dict[str, dict]) -> dict[str, Any]:
    """把輸入的條件參數正規化：

    - 作物等 enum 欄位套用別名表（檨仔 → 芒果）
    - 數值欄位轉 float、布林欄位轉 bool
    - 未註冊的欄位原樣保留（不丟棄，方便除錯）
    """
    facts: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None:
            continue
        spec = fields.get(key)
        if spec is None:
            facts[key] = value
            continue
        ftype = spec.get("type")
        if ftype == "enum":
            aliases = spec.get("aliases", {})
            # 可複選欄位（例如同時種芒果和文旦）：逐項套別名，順便丟掉空值
            if isinstance(value, list):
                value = [aliases.get(v, v) if isinstance(v, str) else v
                         for v in value if v not in (None, "")]
            elif isinstance(value, str):
                value = aliases.get(value, value)
        elif ftype == "number":
            value = float(value)
        elif ftype == "bool":
            if isinstance(value, str):
                value = value.strip() in ("是", "有", "true", "True", "1", "y", "yes")
            else:
                value = bool(value)
        facts[key] = value
    return facts
