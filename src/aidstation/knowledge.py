"""補助知識庫載入與驗證。

補助方案以 JSON 資料集掛載（data/programs/*.json），新增補助不改程式。
載入時做最小驗證：必要欄位、條件樹引用的欄位必須存在於欄位字典——
schema 匯入錯誤要在啟動時炸掉，不能等農民查到一半才發現。
"""
from __future__ import annotations

import json
from pathlib import Path

from .fields import DATA_DIR, load_fields

REQUIRED_KEYS = ("id", "name", "eligibility", "source")
OPERATORS = ("=", "!=", "in", "not_in", ">=", "<=", ">", "<")


def _collect_fields(node: dict, found: set[str]) -> None:
    if "all" in node or "any" in node:
        for child in node.get("all", []) + node.get("any", []):
            _collect_fields(child, found)
    else:
        found.add(node["field"])


def _check_node(node: dict, fields: dict, errors: list[str], path: str = "eligibility") -> None:
    """遞迴檢查條件樹：群組要有子節點，葉節點的欄位與運算子都要合法。"""
    if not isinstance(node, dict):
        errors.append(f"{path} 必須是物件")
        return
    for group in ("all", "any"):
        if group in node:
            children = node[group]
            if not isinstance(children, list) or not children:
                errors.append(f"{path}.{group} 至少要有一個條件")
                return
            for i, child in enumerate(children):
                _check_node(child, fields, errors, f"{path}.{group}[{i}]")
            return
    if "field" not in node:
        errors.append(f"{path} 缺少 field")
        return
    if node["field"] not in fields:
        errors.append(f"{path} 引用了未註冊欄位「{node['field']}」（請先加入 fields.json）")
    if node.get("op") not in OPERATORS:
        errors.append(f"{path} 的運算子「{node.get('op')}」不合法，可用：{'、'.join(OPERATORS)}")
    if "value" not in node:
        errors.append(f"{path} 缺少 value")
    if node.get("op") in ("in", "not_in") and not isinstance(node.get("value"), list):
        errors.append(f"{path} 用 {node['op']} 時 value 必須是清單")


def validate_program(program: dict, fields: dict, label: str = "") -> list[str]:
    """驗證單一補助，回傳錯誤訊息清單（空清單＝通過）。

    後台存檔與啟動載入共用同一套規則——後台存得進去的，啟動就一定載得起來。
    """
    prefix = f"{label} " if label else ""
    if not isinstance(program, dict):
        return [f"{prefix}資料必須是一個 JSON 物件"]
    errors = [f"{prefix}缺少必要欄位：{k}" for k in REQUIRED_KEYS if k not in program]
    if "eligibility" in program:
        sub: list[str] = []
        _check_node(program["eligibility"], fields, sub)
        errors += [prefix + e for e in sub]
    return errors


def load_programs(programs_dir: Path | None = None,
                  fields: dict | None = None) -> list[dict]:
    d = programs_dir or (DATA_DIR / "programs")
    fields = fields or load_fields()
    programs: list[dict] = []
    for path in sorted(d.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        errors = validate_program(p, fields, label=path.name)
        if errors:
            raise ValueError("；".join(errors))
        programs.append(p)
    return programs
