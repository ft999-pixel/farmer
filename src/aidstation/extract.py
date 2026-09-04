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


# The new matching contract deliberately allows programme-specific facts.  They
# do not belong in ``data/fields.json``: that file is the legacy rule-engine
# dictionary and growing it for every subsidy would turn entry criteria into a
# second global DSL.  Keep this allow-list explicit so the extractor remains a
# closed-world, non-PII boundary even when the matching profile is extensible.
MATCHING_PROFILE_KEYS = frozenset({
    "applicant_type",
    "age",
    "location",
    "crops",
    "land_area_ha",
    "farming_years",
    "certifications",
    "young_farmer",
    "young_farmer_status",
    "self_operated",
    "land_use",
    "land_tenure",
    "has_land_use_proof",
    "intent",
    "equipment_intent",
    "disaster_situation",
    "disaster_situation_details",
    "requested_facility_area_ha",
    "agriculture_training_hours",
    "agriculture_credits",
    "technical_qualification",
    "crop_category",
    "insured_farmer",
    "is_farming",
    # Programme-specific facts are safe matching facts, not personal data.
    "machine_model_status",
    "replacement_same_type",
    "old_fuel_machine_year",
    "ghg_reduction_consent",
    "has_operating_site",
    "operating_scale_ok",
    "organic_area_ratio",
    "has_organic_certification",
    "requested_facility_type",
    "facility_is_replacement",
})

_PRIVATE_PROFILE_KEYS = frozenset({
    "full_name", "name", "national_id", "id_number", "birthday",
    "birth_date", "birth_year", "phone", "tel", "full_address", "address",
    "addr", "bank_account", "bank_branch", "parcel_numbers", "parcel_number",
    "signature",
})
_PROFILE_LIST_KEYS = frozenset({"crops", "certifications", "technical_qualification"})
_PROFILE_NUMBER_KEYS = frozenset({
    "age", "land_area_ha", "farming_years", "requested_facility_area_ha",
    "agriculture_training_hours", "agriculture_credits", "organic_area_ratio",
    "old_fuel_machine_year",
})
_PROFILE_BOOL_KEYS = frozenset({
    "young_farmer", "young_farmer_status", "self_operated", "has_land_use_proof",
    "insured_farmer", "is_farming", "replacement_same_type", "ghg_reduction_consent",
    "has_operating_site", "operating_scale_ok", "has_organic_certification",
    "facility_is_replacement",
})


def _normalize_profile_value(key: str, value: Any) -> Any:
    """Normalize an allow-listed MatchingProfile value without using fields.json."""
    if key in _PROFILE_LIST_KEYS:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            raise TypeError(f"{key} 必須是清單")
        cleaned = [item.strip() if isinstance(item, str) else item
                   for item in value]
        if any(not isinstance(item, str) or not item for item in cleaned):
            raise TypeError(f"{key} 清單內容不合法")
        return list(dict.fromkeys(cleaned))
    if key in _PROFILE_NUMBER_KEYS:
        if isinstance(value, bool):
            raise TypeError(f"{key} 不接受布林值")
        number = float(value)
        if key in {"age", "old_fuel_machine_year"} and number.is_integer():
            return int(number)
        return number
    if key in _PROFILE_BOOL_KEYS:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"是", "有", "true", "1", "y", "yes"}:
                return True
            if normalized in {"否", "沒有", "無", "false", "0", "n", "no"}:
                return False
            raise ValueError(f"{key} 布林值不合法")
        if not isinstance(value, (bool, int, float)):
            raise TypeError(f"{key} 必須是布林值")
        return bool(value)
    if not isinstance(value, str):
        raise TypeError(f"{key} 必須是文字")
    value = value.strip()
    if not value:
        raise ValueError(f"{key} 不可為空白")
    return value


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
            if key not in MATCHING_PROFILE_KEYS or key in _PRIVATE_PROFILE_KEYS:
                continue
            try:
                cleaned[key] = _normalize_profile_value(key, value)
            except (ValueError, TypeError, OverflowError):
                continue
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

    _CHINESE_NUMBERS = {
        "零": 0, "〇": 0, "一": 1, "兩": 2, "二": 2, "三": 3,
        "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
        "十": 10,
    }

    def _crop_names(self) -> list[tuple[str, str]]:
        crop_spec = self.fields.get("crop", {})
        aliases = crop_spec.get("aliases", {})
        names = [(str(name), str(name)) for name in crop_spec.get("values", [])]
        names += [(str(alias), str(value)) for alias, value in aliases.items()]
        # Longer names first prevents a short alias from winning over a more
        # precise phrase in future data (for example a compound crop name).
        return sorted(names, key=lambda pair: len(pair[0]), reverse=True)

    def _find_crops(self, text: str) -> list[str]:
        crops: list[str] = []
        for name, canonical in self._crop_names():
            if name in text and canonical not in crops:
                crops.append(canonical)
        return crops

    def _looks_like_matching_profile(self, text: str) -> bool:
        profile_markers = (
            "想買", "要買", "購買", "種", "回來", "回鄉", "從農", "務農",
            "公頃", "分地", "ha", "公頃", "QR", "追溯", "內埔", "内埔",
            "屏東", "農民", "耕作", "田在",
        )
        return any(marker in text for marker in profile_markers)

    def _extract_location(self, text: str) -> str | None:
        # Keep location coarse.  This deliberately does not retain an address
        # or parcel number, which belongs to PrivateFormProfile.
        if ("屏東" in text or "屏東縣" in text) and ("內埔" in text or "内埔" in text):
            return "屏東縣內埔鄉"
        if "內埔" in text or "内埔" in text:
            return "內埔鄉"
        if "屏東" in text:
            return "屏東縣"
        if "臺南" in text or "台南" in text:
            return "臺南市"
        return None

    def _extract_area(self, text: str) -> float | None:
        decimal = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:ha|公頃|公顷)", text, re.I)
        if decimal:
            return float(decimal.group(1))
        # In the demo pack 「八分地」 is the farmer-friendly expression for
        # 0.8 ha.  Handle a few common Chinese numerals without pretending to
        # be a general land-unit converter.
        chinese = re.search(r"([零〇一二兩三四五六七八九十])\s*分(?:地)?", text)
        if chinese:
            number = self._CHINESE_NUMBERS.get(chinese.group(1))
            if number is not None:
                return number / 10
        return None

    def _extract_farming_years(self, text: str) -> float | None:
        explicit = re.search(
            r"(?:從農|務農|耕作|種田|種植)\s*(?:約|大概|差不多)?\s*(\d+(?:\.\d+)?)\s*年",
            text,
        )
        if explicit:
            return float(explicit.group(1))
        chinese = re.search(
            r"(?:從農|務農|耕作|種田|種植)\s*(?:約|大概|差不多)?"
            r"([一二兩三四五六七八九十])\s*年",
            text,
        )
        if chinese:
            return float(self._CHINESE_NUMBERS[chinese.group(1)])
        # 「去年才回來種」 means the first farming year for the demo persona.
        if "去年" in text and any(term in text for term in ("回來", "回鄉", "從農", "種", "務農")):
            return 1.0
        return None

    def _extract_certifications(self, text: str) -> list[str]:
        certifications: list[str] = []
        if re.search(r"QR\s*Code|QR\s*code|QR碼|QR碼|追溯條碼|溯源", text, re.I):
            certifications.append("溯源農糧產品追溯條碼（QR Code）")
        if "有機轉型" in text:
            certifications.append("有機轉型期驗證")
        elif "有機" in text:
            certifications.append("有機驗證")
        if "產銷履歷" in text:
            certifications.append("產銷履歷驗證")
        if "CAS" in text:
            certifications.append("台灣優良農產品驗證（CAS）")
        if "友善環境" in text:
            certifications.append("友善環境耕作登錄")
        return certifications

    def _extract_equipment_intent(self, text: str) -> tuple[str | None, str | None]:
        equipment = None
        if "電動割草機" in text:
            equipment = "電動割草機"
        elif "割草機" in text:
            equipment = "割草機"
        elif "農噴無人機" in text or "無人機" in text:
            equipment = "農噴無人機"
        elif "農機" in text or "農業機械" in text:
            equipment = "農業機械"
        if equipment is None:
            return None, None
        if any(term in text for term in ("想買", "要買", "購買", "想要")):
            intent = f"想買{equipment}"
        else:
            intent = f"購買{equipment}"
        return equipment, intent

    def _extract_matching_profile(self, text: str) -> dict[str, Any]:
        raw: dict[str, Any] = {"applicant_type": "individual_farmer"}
        location = self._extract_location(text)
        if location:
            raw["location"] = location
        crops = self._find_crops(text)
        if crops:
            raw["crops"] = crops
            raw["crop_category"] = "果樹" if any(c in {"香蕉", "芒果", "蓮霧", "文旦"} for c in crops) else "農作物"
        area = self._extract_area(text)
        if area is not None:
            raw["land_area_ha"] = area
        years = self._extract_farming_years(text)
        if years is not None:
            raw["farming_years"] = years
        certifications = self._extract_certifications(text)
        if certifications:
            raw["certifications"] = certifications
        equipment, intent = self._extract_equipment_intent(text)
        if equipment:
            raw["equipment_intent"] = equipment
            raw["intent"] = intent
        if "公告補助牌型" in text and any(term in text for term in ("有", "是", "符合", "內")):
            raw["machine_model_status"] = "listed_subsidized_model"
        elif any(term in text for term in ("還沒有品牌", "沒有型號", "尚未確定型號")):
            raw["machine_model_status"] = "NEED_INFO"
        # These are safe, non-private hints useful to the new matcher.
        if any(term in text for term in ("實際自營", "自己種", "自己耕作")):
            raw["self_operated"] = True
        return raw

    def __init__(self, fields: dict[str, dict]):
        self.fields = fields

    def extract(self, text: str) -> dict[str, Any]:
        raw: dict[str, Any] = {}
        text = text.strip()
        # Keep the original disaster/injury smoke path stable.  It is also a
        # useful guard against treating an event description as a subsidy
        # profile merely because it contains a crop name.
        if any(k in text for k in self.EVENT_INJURY):
            raw["event"] = "職業傷害"
        elif any(k in text for k in self.EVENT_DISASTER):
            crops = self._find_crops(text)
            if crops:
                raw["crop"] = crops[0]
            raw["event"] = "天然災害"
        elif self._looks_like_matching_profile(text):
            return validate_facts(self._extract_matching_profile(text), self.fields)
        else:
            crops = self._find_crops(text)
            if crops:
                raw["crop"] = crops[0]
        return validate_facts(raw, self.fields)


class ClaudeExtractor:
    """Claude 受控輸出抽取。輸出仍必過 validate_facts——不信任任何生成內容。"""

    def __init__(self, fields: dict[str, dict], model: str | None = None):
        self.fields = fields
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
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
            "可用的 MatchingProfile 擴充欄位（不需登記到 fields.json）：",
        ]
        for name in sorted(MATCHING_PROFILE_KEYS):
            lines.append(f"- {name}")
        lines += [
            "換算規則：損失「○成」→ 小數（六成 = 0.6、一半 = 0.5、全掉/攏落了了 = 0.9）；",
            "「租的沒簽約／口頭講好」→ land_tenure=口頭租約；「地是我的」→ 自有。",
            "只抽取可用於補助媒合的概略資訊；姓名、身分證、電話、完整地址、銀行帳號、地號、簽名一律不得輸出。",
            "範例：",
            '「阮的檨仔攏落了了」→ {"crop": "芒果", "event": "天然災害", "loss_rate": 0.9}',
            '「租的地沒簽約，颱風把香蕉都吹倒了，損失大概六成」→ '
            '{"crop": "香蕉", "event": "天然災害", "land_tenure": "口頭租約", "loss_rate": 0.6}',
            '「我在玉井種芒果，想問有什麼保險」→ {"crop": "芒果", "township": "玉井區"}',
            '「我去年才回來屏東種香蕉，大概八分地，有 QR Code，最近想買電動割草機」→ '
            '{"applicant_type":"individual_farmer","location":"屏東縣內埔鄉","crops":["香蕉"],'
            '"land_area_ha":0.8,"farming_years":1,"certifications":["溯源農糧產品追溯條碼（QR Code）"],'
            '"equipment_intent":"電動割草機","intent":"想買電動割草機"}',
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
