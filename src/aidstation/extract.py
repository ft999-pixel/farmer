"""語意抽取層：把口語處境轉成條件參數（受控輸出）。

原則（《系統設計建議書》§2.2）：LLM 只做抽取，不做判定。
所有 LLM 輸出必經 validate_facts() 過濾——未註冊欄位丟棄、enum 值
不合法丟棄、型別不合丟棄。這層是幻覺防火牆：LLM 永遠無法直接影響
資格判定結果，只能提供合法的欄位值。

有 ANTHROPIC_API_KEY 環境變數時使用 Claude；沒有時退回關鍵字抽取
（KeywordExtractor），介面相同，離線可開發可測試。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

from .fields import normalize_facts


def validate_facts(raw: dict[str, Any], fields: dict[str, dict]) -> dict[str, Any]:
    """幻覺防火牆：只放行「已註冊欄位＋合法值」。

    - 未註冊欄位（如 LLM 自作主張的 "status"、"eligible"）：丟棄
    - enum 欄位：先套別名，仍不在合法值清單 → 丟棄
    - number／bool：轉型失敗 → 丟棄
    """
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        spec = fields.get(key)
        if spec is None or value is None:
            continue
        try:
            normalized = normalize_facts({key: value}, fields)[key]
        except (ValueError, TypeError):
            continue
        if spec.get("type") == "enum" and normalized not in spec.get("values", []):
            continue
        cleaned[key] = normalized
    return cleaned


class Extractor(Protocol):
    def extract(self, text: str) -> dict[str, Any]: ...


class KeywordExtractor:
    """離線後備：關鍵字比對。開發、測試與 LLM 故障降級時使用。"""

    EVENT_DISASTER = ("掉", "落", "淹", "倒", "災", "風", "雨", "凍", "旱", "死了")
    EVENT_INJURY = ("受傷", "跌倒", "割到", "骨折", "農機夾")

    def __init__(self, fields: dict[str, dict]):
        self.fields = fields

    def extract(self, text: str) -> dict[str, Any]:
        raw: dict[str, Any] = {}
        crop_spec = self.fields.get("crop", {})
        for name in list(crop_spec.get("values", [])) + list(crop_spec.get("aliases", {})):
            if name in text:
                raw["crop"] = name
                break
        if any(k in text for k in self.EVENT_INJURY):
            raw["event"] = "職業傷害"
        elif any(k in text for k in self.EVENT_DISASTER):
            raw["event"] = "天然災害"
        return validate_facts(raw, self.fields)


class ClaudeExtractor:
    """Claude 受控輸出抽取。輸出仍必過 validate_facts——不信任任何生成內容。"""

    def __init__(self, fields: dict[str, dict], model: str | None = None):
        self.fields = fields
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
        import anthropic  # 延遲載入，未安裝時不影響離線模式
        self.client = anthropic.Anthropic()
        self.fallback = KeywordExtractor(fields)

    def _prompt(self) -> str:
        lines = [
            "你是農業補助查詢系統的欄位抽取器。從農民的口語描述（可能含台語）抽取欄位值。",
            "只輸出一個 JSON 物件，不輸出任何其他文字。",
            "規則：只抽取使用者明確提到的資訊，不推測、不判斷資格。",
            "可用欄位（其餘一律不得出現）：",
        ]
        for name, spec in self.fields.items():
            desc = f"- {name}（{spec.get('label')}，{spec.get('type')}）"
            if spec.get("values"):
                desc += f"：{'/'.join(map(str, spec['values']))}"
            if spec.get("aliases"):
                desc += f"；台語別名 {spec['aliases']}"
            lines.append(desc)
        lines += [
            "換算規則：損失「○成」→ 小數（六成 = 0.6、一半 = 0.5、全掉/攏落了了 = 0.9）；",
            "「租的沒簽約／口頭講好」→ land_tenure=口頭租約；「地是我的」→ 自有。",
            "範例：",
            '「阮的檨仔攏落了了」→ {"crop": "芒果", "event": "天然災害", "loss_rate": 0.9}',
            '「租的地沒簽約，颱風把香蕉都吹倒了，損失大概六成」→ '
            '{"crop": "香蕉", "event": "天然災害", "land_tenure": "口頭租約", "loss_rate": 0.6}',
            '「我在玉井種芒果，想問有什麼保險」→ {"crop": "芒果", "township": "玉井區"}',
        ]
        return "\n".join(lines)

    def extract(self, text: str) -> dict[str, Any]:
        try:
            msg = self.client.messages.create(
                model=self.model, max_tokens=300,
                system=self._prompt(),
                messages=[{"role": "user", "content": text}],
            )
            content = msg.content[0].text
            match = re.search(r"\{.*\}", content, re.S)
            raw = json.loads(match.group(0)) if match else {}
        except Exception:
            # LLM 故障 → 降級為關鍵字抽取，服務不中斷
            return self.fallback.extract(text)
        return validate_facts(raw, self.fields)


def get_extractor(fields: dict[str, dict]) -> Extractor:
    """有金鑰用 Claude，沒有用關鍵字。呼叫端不需要知道差別。"""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return ClaudeExtractor(fields)
        except Exception:
            pass
    return KeywordExtractor(fields)
