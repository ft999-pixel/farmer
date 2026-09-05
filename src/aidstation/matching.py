"""Backend matching pipeline for the canonical ``MatchingProfile`` contract.

The matching unit is a ``Variant`` plus an ``ApplicationRound``.  Programme
metadata is checked deterministically first (especially dates), then entry
criteria are evaluated by an optional Anthropic adapter or by the small,
offline-safe heuristic matcher below.  The fallback is deliberately a
keyword/demo matcher rather than a second rule language: criteria remain
human-readable text and uncertain cases are surfaced as ``NEED_INFO`` or
``REVIEW``.

This module never receives or forwards ``PrivateFormProfile`` values.  Form
templates may contain browser-only source *references* such as
``private.full_name``; they do not contain private values and are retained so
the browser can perform local prefill.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Protocol, Sequence

from .fields import load_fields, normalize_facts
from .knowledge import normalize_program, program_dict
from .schemas import (
    PRIVATE_PROFILE_KEYS,
    MatchStatus,
    MatchingProfile,
)


STATUS_ORDER: dict[str, int] = {
    "MATCH": 0,
    "NEED_INFO": 1,
    "REVIEW": 2,
    "NOT_RELEVANT": 3,
    "CLOSED": 4,
}

_MISSING = object()

# Shared profile names are intentionally the public names exposed in schemas.
# Legacy flat seeds use the aliases on the right; they are only used internally
# and never added back to the response profile.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "crop": ("crops", "crop"),
    "township": ("location", "township", "region"),
    "event": ("disaster_situation", "event"),
    "land_doc": ("land_doc",),
}
_CANONICAL_MISSING_KEY = {
    "crop": "crops",
    "township": "location",
    "event": "disaster_situation",
}

_QUESTION_OVERRIDES = {
    "applicant_type": "你是個人農民、農業團體，還是其他申請人？",
    "location": "你的田地或申請地點在哪個縣市／鄉鎮？",
    "crops": "你種的是什麼作物？",
    "disaster_situation": "最近遇到的是什麼情況？",
    "certifications": "你目前有哪一種驗證或登錄？（沒有或不確定也可以說。）",
    "age": "請問你今年幾歲？",
    "farming_years": "你大約從農幾年了？",
    "land_area_ha": "你的耕作面積大約幾公頃？",
    "land_use": "土地目前是合法農業使用嗎？",
    "land_tenure": "土地是自有、租用，還是其他權屬？",
    "has_land_use_proof": "你有土地使用權或合法使用證明嗎？",
    "self_operated": "這塊地是你自己實際經營嗎？",
    "is_farming": "這塊地目前有實際在耕作嗎？",
    "insured_farmer": "有沒有保農保？",
    "machine_model_status": "你想買的農機有確定品牌或型號，而且在當年度公告牌型內嗎？",
    "requested_facility_area_ha": "申請的設施面積大約幾公頃？",
    "agriculture_training_hours": "你修過的農業訓練大約幾小時？",
    "agriculture_credits": "你修過的農業相關學分大約幾學分？",
    "technical_qualification": "你有農業相關學歷、訓練或其他技術資格嗎？",
    # 災害救助判準。問法沿用 fields.json，維持長輩看得懂的白話，
    # 不要讓農民看到「請提供你的 loss_rate 資訊」這種欄位代號。
    "loss_rate": "大概損失幾成？",
    "land_doc": "手邊有這些文件嗎？（租約、地主同意書、從農工作證明）",
    "policy_enrolled_2y": "最近兩年，有沒有用這塊地去公所或農會申報過東西？"
                          "（例如綠色環境給付、轉契作）",
}

_CERTIFICATION_TERMS = (
    "有機",
    "轉型",
    "友善",
    "產銷履歷",
    "溯源",
    "追溯",
    "qr code",
    "cas",
)
_KNOWN_CROPS = (
    "芒果", "水稻", "香蕉", "蓮霧", "文旦", "絲瓜", "蝴蝶蘭", "文心蘭",
    "桃", "楊桃", "紅龍果", "番荔枝", "鳳梨釋迦", "柑橘", "百香果", "荔枝",
    "紅棗", "獼猴桃", "鳳梨", "香菇", "木耳", "草菇", "洋菇", "香莢蘭",
)
_CATEGORY_GROUPS = {
    "machine": frozenset(("農機", "機械", "省工", "割草", "購機", "碳匯", "設備")),
    "facility": frozenset(("設施", "溫網室", "網室", "防災", "農地")),
    "disaster": frozenset(("災害", "救助", "颱風", "豪雨", "寒害", "災損", "損失")),
    "insurance": frozenset(("保險", "投保", "保費")),
    "organic": frozenset(("有機", "友善", "堆肥", "驗證", "轉型")),
    "young": frozenset(("青年", "從農", "經營準備", "準備金")),
    "welfare": frozenset(("福利", "退休", "農保", "職保", "儲金")),
}


class MatchingInputError(ValueError):
    """Raised when a profile or asked key violates the public contract."""


def _private_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    return lowered if lowered in PRIVATE_PROFILE_KEYS else None


def reject_private_keys(value: Any, *, path: str = "profile") -> None:
    """Reject private-only keys recursively, including nested extra fields."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            private = _private_key(key)
            if private:
                raise MatchingInputError(
                    f"{path}.{key} 是瀏覽器本地欄位，不能送到後端。"
                )
            reject_private_keys(child, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple, set)):
        for index, child in enumerate(value):
            reject_private_keys(child, path=f"{path}[{index}]")


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _iso_date(value: Any) -> str | None:
    parsed = _date_value(value)
    return parsed.isoformat() if parsed else None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("臺", "台")


def _provided_keys(profile: Mapping[str, Any]) -> set[str]:
    provided = profile.get("__provided_keys__")
    if isinstance(provided, set):
        return provided
    if isinstance(provided, (list, tuple)):
        return set(provided)
    return {str(k) for k in profile if not str(k).startswith("__")}


def _is_missing(profile: Mapping[str, Any], key: str) -> bool:
    value = profile.get(key, _MISSING)
    if value is _MISSING or value is None:
        return True
    if isinstance(value, (list, tuple, set)) and not value:
        return key not in _provided_keys(profile)
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _get_profile_value(profile: Mapping[str, Any], field: str) -> Any:
    for alias in _FIELD_ALIASES.get(field, (field,)):
        if not _is_missing(profile, alias):
            value = profile.get(alias)
            if field == "crop" and alias == "crops":
                values = _as_list(value)
                return values if len(values) != 1 else values[0]
            return value
    return _MISSING


def _normalise_profile(profile: MatchingProfile | Mapping[str, Any]) -> tuple[MatchingProfile, dict[str, Any], dict[str, Any]]:
    """Validate and normalize a profile.

    Returns ``(model, internal_facts, public_profile)``. The internal mapping
    contains legacy aliases and a private bookkeeping key; it is never returned
    or sent to an adapter.
    """
    if isinstance(profile, MatchingProfile):
        model = profile
        # model_extra keeps values allowed by the shared schema. A nested extra
        # object is checked here as well; the shared validator intentionally
        # focuses on the normal top-level path.
        raw_model_extra = getattr(model, "model_extra", None) or {}
        reject_private_keys(raw_model_extra)
    elif isinstance(profile, Mapping):
        reject_private_keys(profile)
        try:
            model = MatchingProfile.model_validate(dict(profile))
        except Exception as exc:
            raise MatchingInputError(str(exc)) from exc
    else:
        raise MatchingInputError("profile 必須是 MatchingProfile 物件")

    reject_private_keys(model.model_dump(mode="python"))
    public = model.model_dump(
        mode="python", exclude_none=True, exclude_defaults=True
    )
    explicit = set(getattr(model, "model_fields_set", set()))
    explicit.update((getattr(model, "model_extra", None) or {}).keys())

    # A few old clients still call these fields crop/township/event. Accepting
    # them through MatchingProfile.extra is the compatibility bridge, but the
    # response is canonicalized to crops/location/disaster_situation below.
    if "crops" not in public and "crop" in public:
        public["crops"] = _as_list(public["crop"])
    if "location" not in public and "township" in public:
        public["location"] = public["township"]
    if "disaster_situation" not in public and "event" in public:
        public["disaster_situation"] = public["event"]

    facts = dict(public)
    facts["__provided_keys__"] = explicit | set(public)
    aliases = (load_fields().get("crop", {}).get("aliases", {}) or {})
    if "crops" in facts:
        crops = [aliases.get(item, item) if isinstance(item, str) else item
                 for item in _as_list(facts["crops"])]
        facts["crops"] = crops
        facts["crop"] = crops if len(crops) != 1 else crops[0]
    if "location" in facts:
        facts["township"] = facts["location"]
    if "disaster_situation" in facts:
        facts["event"] = facts["disaster_situation"]

    # Normalize legacy registered fields (aliases, numeric and bool values)
    # without dropping programme-specific profile extras.
    try:
        normalized_legacy = normalize_facts(
            {key: value for key, value in facts.items()
             if not str(key).startswith("__")}, load_fields())
        facts.update(normalized_legacy)
    except (TypeError, ValueError):
        pass
    facts["__provided_keys__"] = explicit | set(public) | {
        "crop", "township", "event"
    }

    # Re-normalize aliases after normalize_facts potentially changed crop.
    if "crop" in facts and "crops" not in facts:
        facts["crops"] = _as_list(facts["crop"])
    elif "crops" in facts:
        facts["crop"] = facts["crops"] if len(_as_list(facts["crops"])) != 1 else _as_list(facts["crops"])[0]
    return model, facts, _public_profile(public)


def _public_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Strip internal aliases/private values from the response profile."""
    output = {
        str(key): value for key, value in profile.items()
        if not str(key).startswith("__")
    }
    if "crops" not in output and "crop" in output:
        output["crops"] = _as_list(output["crop"])
    if "location" not in output and "township" in output:
        output["location"] = output["township"]
    if "disaster_situation" not in output and "event" in output:
        output["disaster_situation"] = output["event"]
    output.pop("crop", None)
    output.pop("township", None)
    output.pop("event", None)
    reject_private_keys(output)
    return output


@dataclass(frozen=True)
class Candidate:
    program: dict[str, Any]
    variant: dict[str, Any]
    round: dict[str, Any]

    @property
    def program_id(self) -> str:
        return str(self.program.get("id"))

    @property
    def variant_id(self) -> str:
        return str(self.variant.get("id"))

    @property
    def round_id(self) -> str:
        return str(self.round.get("id"))


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    return {}


def iter_candidates(programs: Sequence[Any]) -> list[Candidate]:
    """Flatten loaded hierarchy into the actual matching unit."""
    candidates: list[Candidate] = []
    for raw_program in programs:
        program = _mapping(raw_program)
        if not program.get("id"):
            continue
        # Direct callers may pass old JSON dicts rather than load_programs().
        # Normalize them here, keeping the public helper convenient in tests.
        if not program.get("variants"):
            try:
                program = program_dict(normalize_program(program))
            except Exception:
                program = dict(program)
        variants = program.get("variants") or [{}]
        if isinstance(variants, Mapping):
            variants = [variants]
        for variant_index, raw_variant in enumerate(variants):
            variant = _mapping(raw_variant)
            variant.setdefault("id", f"{program['id']}-variant-{variant_index + 1}")
            variant.setdefault("name", program.get("name") or variant["id"])
            rounds = variant.get("rounds") or variant.get("application_rounds") or [{}]
            if isinstance(rounds, Mapping):
                rounds = [rounds]
            for round_index, raw_round in enumerate(rounds):
                round_data = _mapping(raw_round)
                round_data.setdefault(
                    "id", f"{variant['id']}-round-{round_index + 1}"
                )
                # The loader inherits these values. Direct dict callers get the
                # same behavior without needing to know the normalization API.
                for key in ("window", "authority", "source"):
                    if not round_data.get(key):
                        round_data[key] = variant.get(key) or program.get(key) or {}
                for key in ("entry_criteria", "tasks"):
                    if round_data.get(key) is None:
                        round_data[key] = variant.get(key)
                    if round_data.get(key) is None:
                        round_data[key] = program.get(key)
                if round_data.get("form_template") is None:
                    round_data["form_template"] = (
                        variant.get("form_template") or program.get("form_template")
                    )
                candidates.append(Candidate(program, variant, round_data))
    return candidates


def _window(candidate: Candidate) -> tuple[dict[str, Any], date | None, date | None]:
    raw_window: Any = None
    for owner in (candidate.round, candidate.variant, candidate.program):
        raw_window = owner.get("window") or owner.get("application_window")
        if raw_window is not None:
            break
    window = _mapping(raw_window)
    start_raw = next((window.get(key) for key in
                      ("start", "open", "from", "start_date")
                      if window.get(key) is not None), None)
    end_raw = next((window.get(key) for key in
                    ("end", "close", "to", "end_date", "deadline")
                    if window.get(key) is not None), None)
    start, end = _date_value(start_raw), _date_value(end_raw)
    output: dict[str, Any] = {}
    for key, value in window.items():
        if isinstance(value, (date, datetime)):
            output[key] = value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
        else:
            output[key] = value
    if start:
        output["start"] = start.isoformat()
        output.setdefault("open", start.isoformat())
    if end:
        output["end"] = end.isoformat()
        output.setdefault("close", end.isoformat())
    return output, start, end


def _merged_metadata(candidate: Candidate) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for owner in (candidate.program, candidate.variant, candidate.round):
        value = owner.get("metadata")
        if isinstance(value, Mapping):
            metadata.update(value)
    # Seed authors sometimes put filter metadata next to metadata for
    # readability. Copy only known filter keys, leaving the original model
    # untouched.
    for owner in (candidate.program, candidate.variant, candidate.round):
        for key in (
            "applicant_type", "applicant_types", "eligible_applicant_types",
            "regions", "region", "coarse_region", "locations",
            "eligible_regions", "intent_keywords", "keywords", "crops",
            "crop_scope", "category", "categories", "required_matching_facts",
            "missing_questions", "question_options", "required_certification_any",
        ):
            if key in owner and key not in metadata:
                metadata[key] = owner[key]
    return metadata


def _values_for(metadata: Mapping[str, Any], keys: Sequence[str]) -> list[Any]:
    for key in keys:
        if key in metadata and metadata[key] is not None:
            value = metadata[key]
            return _as_list(value)
    return []


def _same_text(left: Any, right: Any) -> bool:
    a, b = _text(left), _text(right)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _applicant_match(actual: Any, allowed: Any) -> bool:
    actual_text = _text(actual).replace(" ", "_")
    aliases = {
        "individual_farmer": {"individual_farmer", "individual", "farmer", "農民", "自然人農民", "自然人"},
        "farmer": {"individual_farmer", "individual", "farmer", "農民", "自然人農民", "自然人"},
        "farmer_group": {"farmer_group", "group", "產銷班", "農業團體", "團體"},
        "農民": {"individual_farmer", "individual", "farmer", "農民", "自然人農民", "自然人"},
    }
    actual_set = aliases.get(actual_text, {actual_text})
    for item in _as_list(allowed):
        item_text = _text(item).replace(" ", "_")
        if item_text in {"all", "any", "全國", "全台", "全臺"}:
            return True
        if item_text in actual_set or item_text == actual_text:
            return True
        if _same_text(actual, item):
            return True
    return False


def _region_match(actual: Any, allowed: Any) -> bool:
    actual_text = _text(actual)
    if not actual_text:
        return False
    actual_text = actual_text.replace("臺", "台")
    for item in _as_list(allowed):
        item_text = _text(item).replace("臺", "台")
        if item_text in {"all", "any", "全國", "全台"}:
            return True
        if item_text and (item_text in actual_text or actual_text in item_text):
            return True
    return False


def _category_groups(value: Any) -> set[str]:
    text = _text(value)
    groups: set[str] = set()
    for group, terms in _CATEGORY_GROUPS.items():
        if any(term.lower() in text for term in terms):
            groups.add(group)
    return groups


def _intent_match(intent: Any, candidate_terms: Sequence[Any]) -> bool:
    intent_text = _text(intent)
    if not intent_text:
        return True
    if any(term in intent_text for term in ("查補助", "找補助", "想了解", "不確定", "申請")):
        # Generic intents do not provide enough signal for a coarse exclusion.
        return True
    intent_groups = _category_groups(intent_text)
    candidate_text = " ".join(_text(item) for item in candidate_terms)
    candidate_groups = _category_groups(candidate_text)
    if intent_groups and candidate_groups:
        return bool(intent_groups & candidate_groups)
    terms = [term for term in re.findall(r"[\w\u3400-\u9fff]+", intent_text) if len(term) > 1]
    return not terms or any(term in candidate_text for term in terms)


@dataclass
class PrefilterDecision:
    status: MatchStatus | None = None
    reason: list[str] | None = None
    missing_info: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if self.reason is None:
            self.reason = []
        if self.missing_info is None:
            self.missing_info = []


def _missing(key: str, *, question: str | None = None) -> dict[str, Any]:
    canonical = _CANONICAL_MISSING_KEY.get(key, key)
    out: dict[str, Any] = {
        "key": canonical,
        "question": question or _QUESTION_OVERRIDES.get(
            canonical, f"請提供你的「{canonical}」資訊。"
        ),
    }
    # 帶上欄位字典裡的白話選項，讓農民用按的而不是打字（設計建議書 §4.1）。
    # option_map 一併回傳，答案才轉得回內部值（「超過一半」→ 0.6）。
    spec = load_fields().get(canonical) or load_fields().get(key) or {}
    if spec.get("options"):
        out["options"] = list(spec["options"])
        if spec.get("option_map"):
            out["option_map"] = dict(spec["option_map"])
    return out


def metadata_prefilter(candidate: Candidate, profile: Mapping[str, Any], today: date) -> PrefilterDecision:
    """Filter only coarse metadata and deterministic application dates."""
    window, start, end = _window(candidate)
    if start and today < start:
        return PrefilterDecision(
            status="CLOSED",
            reason=[f"申請尚未開始，受理起日為 {start.isoformat()}。"],
        )
    if end and today > end:
        return PrefilterDecision(
            status="CLOSED",
            reason=[f"申請期限已過，截止日為 {end.isoformat()}。"],
        )

    metadata = _merged_metadata(candidate)
    decision = PrefilterDecision()

    allowed_applicants = _values_for(metadata, (
        "applicant_types", "eligible_applicant_types", "applicant_type",
    ))
    if allowed_applicants:
        applicant = profile.get("applicant_type")
        if _is_missing(profile, "applicant_type"):
            decision.missing_info.append(_missing("applicant_type"))
        elif not _applicant_match(applicant, allowed_applicants):
            decision.status = "NOT_RELEVANT"
            decision.reason.append("申請人類型與這筆補助的適用對象不同。")

    allowed_regions = _values_for(metadata, (
        "regions", "eligible_regions", "locations", "region", "coarse_region",
    ))
    if allowed_regions:
        location = profile.get("location") or profile.get("region")
        if _is_missing(profile, "location") and _is_missing(profile, "region"):
            decision.missing_info.append(_missing("location"))
        elif not _region_match(location, allowed_regions):
            decision.status = "NOT_RELEVANT"
            decision.reason.append("申請地區不在這筆補助目前的適用範圍。")

    allowed_crops = _values_for(metadata, ("crops", "crop_scope"))
    if allowed_crops:
        crops = _as_list(profile.get("crops"))
        if _is_missing(profile, "crops"):
            decision.missing_info.append(_missing("crops"))
        elif not any(_same_text(crop, item) for crop in crops for item in allowed_crops):
            decision.status = "NOT_RELEVANT"
            decision.reason.append("目前提供的作物不在這筆補助的適用品項內。")

    candidate_terms = [
        candidate.program.get("name"), candidate.variant.get("name"),
        candidate.program.get("category"), candidate.variant.get("category"),
        *(_values_for(metadata, ("intent_keywords", "keywords", "categories"))),
    ]
    if not _is_missing(profile, "intent") and not _intent_match(profile.get("intent"), candidate_terms):
        decision.status = "NOT_RELEVANT"
        decision.reason.append("你的查詢方向和這筆補助的類別／用途較不相符。")

    if decision.status is None and decision.missing_info:
        # Missing coarse metadata should not discard a candidate. Criteria may
        # still provide a stronger answer after one follow-up question.
        decision.status = "NEED_INFO"
        decision.reason.append("先確認基本申請條件，才能判斷這筆是否值得申請。")
    return decision


def _question_for_field(field: str) -> dict[str, str]:
    return _missing(field)


def _facts_for_criterion(profile: Mapping[str, Any]) -> dict[str, Any]:
    facts = {
        key: value for key, value in profile.items()
        if not str(key).startswith("__")
    }
    # eval_node consumes old names. _get_profile_value also handles canonical
    # names for conditions loaded from legacy flat seeds.
    for field in ("crop", "township", "event"):
        value = _get_profile_value(profile, field)
        if value is not _MISSING:
            facts[field] = value
    return facts


def _numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _criterion_value_match(actual: Any, expected: Any, op: str) -> bool | None:
    """Evaluate one simple criterion leaf without introducing a rule DSL."""
    if actual is _MISSING:
        return None
    values = _as_list(actual) if isinstance(actual, (list, tuple, set)) else [actual]
    expected_values = _as_list(expected)
    if op in ("in", "not_in"):
        matches = [any(_same_text(value, item) or value == item
                       for item in expected_values) for value in values]
        return any(matches) if op == "in" else all(not match for match in matches)
    if op in (">=", "<=", ">", "<"):
        a = _numeric(actual)
        b = _numeric(expected)
        if a is None or b is None:
            return False
        return {
            ">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b,
        }[op]
    if op == "=":
        return any(_same_text(value, expected) or value == expected for value in values)
    if op == "!=":
        return all(not (_same_text(value, expected) or value == expected) for value in values)
    return False


def _explicit_criterion(criterion: Mapping[str, Any], profile: Mapping[str, Any]) -> tuple[str, str, list[dict[str, str]]]:
    field = str(criterion.get("field"))
    actual = _get_profile_value(profile, field)
    if actual is _MISSING:
        return "NEED_INFO", f"還需要確認：{criterion.get('text') or field}。", [_question_for_field(field)]
    matched = _criterion_value_match(actual, criterion.get("value"), str(criterion.get("op", "=")))
    if matched is True:
        return "MATCH", str(criterion.get("text") or f"已提供 {field}。"), []
    return "NOT_RELEVANT", str(criterion.get("note") or criterion.get("text") or f"條件 {field} 不相符。"), []


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    return any(term.lower() in text for term in terms)


def _natural_criterion(criterion: Mapping[str, Any], profile: Mapping[str, Any]) -> tuple[str, str, list[dict[str, str]]]:
    """Conservative keyword/threshold matching for human-readable criteria."""
    original = str(criterion.get("text") or criterion.get("description") or "").strip()
    text = _text(original)
    if not text:
        return "REVIEW", "這項申請條件沒有可供自動比對的說明。", []

    explicit_fields = criterion.get("required_fields") or criterion.get("fields")
    if isinstance(explicit_fields, str):
        explicit_fields = [explicit_fields]
    if isinstance(explicit_fields, list):
        for field in explicit_fields:
            if _is_missing(profile, str(field)):
                return "NEED_INFO", f"還需要確認「{field}」。", [_question_for_field(str(field))]

    # Conditions that explicitly say the requirement can be completed later do
    # not block starting an application (demo acceptance for fruit facilities).
    later_requirement = _contains_any(text, ("後續", "之後取得", "申請後", "尚未取得仍可", "後補"))

    # Age ranges and one-sided age thresholds.
    if _contains_any(text, ("年齡", "歲", "成年", "未滿")):
        age = _numeric(profile.get("age"))
        if _is_missing(profile, "age"):
            return "NEED_INFO", "還需要確認年齡。", [_missing("age")]
        if age is None:
            return "REVIEW", "年齡格式需要承辦單位確認。", []
        range_match = re.search(r"(\d+(?:\.\d+)?)\s*[至到\-~～]\s*(\d+(?:\.\d+)?)\s*歲?", text)
        if range_match:
            low, high = float(range_match.group(1)), float(range_match.group(2))
            if low <= age <= high:
                return "MATCH", "年齡落在申請條件範圍內。", []
            return "NOT_RELEVANT", "年齡不在這筆補助的申請範圍。", []
        minimum = re.search(r"(?:年滿|至少)\s*(\d+(?:\.\d+)?)\s*歲", text)
        maximum = re.search(r"(?:未滿|不滿|不超過|至多)\s*(\d+(?:\.\d+)?)\s*歲", text)
        if minimum and age < float(minimum.group(1)):
            return "NOT_RELEVANT", "年齡低於這筆補助的最低要求。", []
        if maximum and age > float(maximum.group(1)):
            return "NOT_RELEVANT", "年齡高於這筆補助的申請上限。", []
        if minimum or maximum:
            return "MATCH", "年齡條件已初步符合。", []

    # From-farming years, kept separate from age's use of 年.
    if _contains_any(text, ("從農", "耕作年資", "務農年資")):
        years = _numeric(profile.get("farming_years"))
        if _is_missing(profile, "farming_years"):
            return "NEED_INFO", "還需要確認從農年資。", [_missing("farming_years")]
        if years is None:
            return "REVIEW", "從農年資格式需要承辦單位確認。", []
        maximum = re.search(r"(?:未滿|少於|不超過|至多)\s*(\d+(?:\.\d+)?)\s*年", text)
        minimum = re.search(r"(?:至少|達)\s*(\d+(?:\.\d+)?)\s*年", text)
        if maximum and years >= float(maximum.group(1)):
            return "NOT_RELEVANT", "從農年資超過這筆補助的範圍。", []
        if minimum and years < float(minimum.group(1)):
            return "NOT_RELEVANT", "從農年資未達這筆補助的最低要求。", []
        if maximum or minimum:
            return "MATCH", "從農年資條件已初步符合。", []

    # Area thresholds. The unit is optional when text clearly refers to an
    # application/facility area.
    if _contains_any(text, ("面積", "公頃", "ha")):
        area_key = "requested_facility_area_ha" if _contains_any(text, ("設施", "蝴蝶蘭", "網室")) else "land_area_ha"
        area = _numeric(profile.get(area_key))
        if _is_missing(profile, area_key):
            return "NEED_INFO", "還需要確認申請面積。", [_missing(area_key)]
        if area is None:
            return "REVIEW", "面積格式需要承辦單位確認。", []
        threshold_match = re.search(
            r"(?:至少|不低於|達|不少於|>=|＞=)\s*(\d+(?:\.\d+)?)\s*(?:公頃|ha|㏊)?", text
        )
        maximum_match = re.search(
            r"(?:不得超過|不超過|至多|<=|＜=)\s*(\d+(?:\.\d+)?)\s*(?:公頃|ha|㏊)?", text
        )
        if threshold_match:
            threshold = float(threshold_match.group(1))
            if area < threshold:
                return "NOT_RELEVANT", f"面積未達至少 {threshold:g} 公頃的條件。", []
            return "MATCH", "申請面積已達初步門檻。", []
        if maximum_match:
            maximum = float(maximum_match.group(1))
            if area > maximum:
                return "NOT_RELEVANT", f"設施面積超過 {maximum:g} 公頃的條件。", []
            return "MATCH", "設施面積在初步範圍內。", []

    # Technical qualification is an OR of qualification, training, and credits.
    if _contains_any(text, ("農業技術資格", "技術資格", "訓練", "學分", "農業相關科系")):
        qualifications = profile.get("technical_qualification")
        has_qualification = not _is_missing(profile, "technical_qualification") and bool(_as_list(qualifications))
        training = _numeric(profile.get("agriculture_training_hours"))
        credits = _numeric(profile.get("agriculture_credits"))
        training_threshold_match = re.search(r"訓練[^\d]{0,15}(?:至少|達|>=)?\s*(\d+(?:\.\d+)?)\s*小時", text)
        credit_threshold_match = re.search(r"(?:學分|credits?)[^\d]{0,15}(?:至少|達|>=)?\s*(\d+(?:\.\d+)?)", text)
        training_threshold = float(training_threshold_match.group(1)) if training_threshold_match else 150.0
        credit_threshold = float(credit_threshold_match.group(1)) if credit_threshold_match else 9.0
        if has_qualification:
            return "MATCH", "已有農業技術資格資料。", []
        if training is not None and training >= training_threshold:
            return "MATCH", "農業訓練時數已達初步門檻。", []
        if credits is not None and credits >= credit_threshold:
            return "MATCH", "農業學分已達初步門檻。", []
        # An explicitly supplied insufficient training/credits is a clear
        # negative for this criterion; absent alternatives remain a question.
        if training is not None or credits is not None or qualifications is not None:
            if training is not None and training < training_threshold:
                return "NOT_RELEVANT", "目前提供的農業訓練時數不足。", []
            if credits is not None and credits < credit_threshold:
                return "NOT_RELEVANT", "目前提供的農業學分不足。", []
            return "NOT_RELEVANT", "目前沒有可用的農業技術資格。", []
        return "NEED_INFO", "還需要確認農業技術資格、訓練或學分。", [
            _missing("technical_qualification")
        ]

    # Certification/registration alternatives (organic, QR, friendly farming).
    if _contains_any(text, _CERTIFICATION_TERMS):
        certifications = profile.get("certifications")
        if _is_missing(profile, "certifications"):
            if later_requirement:
                return "MATCH", "這項驗證可依規定後續取得，現在可先開始申請。", []
            return "NEED_INFO", "還需要確認驗證或登錄狀態。", [_missing("certifications")]
        cert_text = " ".join(_text(item) for item in _as_list(certifications))
        matching_terms = [term for term in _CERTIFICATION_TERMS if term in text]
        if any(term in cert_text for term in matching_terms) or (cert_text and "驗證" not in text):
            return "MATCH", "已提供與這筆補助相關的驗證／登錄資訊。", []
        if later_requirement:
            return "MATCH", "目前尚未取得也可先受理，後續依規定補齊。", []
        return "NOT_RELEVANT", "目前提供的驗證／登錄與這筆條件不相符。", []

    # Machine model/brand is the hero demo's one-question path.
    if _contains_any(text, ("公告補助牌型", "補助牌型", "牌型", "型號", "品牌")):
        key = "machine_model_status"
        if _is_missing(profile, key):
            return "NEED_INFO", "還需要確認欲購農機是否為公告補助牌型。", [
                _missing(key, question=str(criterion.get("question") or "") or None)
            ]
        value = _text(profile.get(key))
        if any(token in value for token in ("listed", "公告", "有", "是", "符合", "內")):
            return "MATCH", "欲購農機已標示為公告補助牌型。", []
        return "NOT_RELEVANT", "目前提供的農機牌型尚未確認為公告補助牌型。", []

    # Land / operation basics.
    if _contains_any(text, ("自營", "實際耕作", "實際經營")):
        key = "self_operated" if "自營" in text or "經營" in text else "is_farming"
        if _is_missing(profile, key):
            return "NEED_INFO", "還需要確認是否為本人實際耕作／經營。", [_missing(key)]
        if profile.get(key) is True:
            return "MATCH", "已提供實際耕作／經營資訊。", []
        return "NOT_RELEVANT", "目前提供的耕作／經營狀態不符合這項條件。", []
    if _contains_any(text, ("使用權證明", "合法農地", "合法農業使用", "土地合法")):
        if "使用權證明" in text:
            key = "has_land_use_proof"
            if _is_missing(profile, key):
                return "NEED_INFO", "還需要確認土地使用權證明。", [_missing(key)]
            return ("MATCH", "已提供土地使用權證明。", []) if profile.get(key) is True else (
                "NOT_RELEVANT", "目前沒有土地使用權證明。", []
            )
        land_use = _text(profile.get("land_use"))
        if _is_missing(profile, "land_use"):
            return "NEED_INFO", "還需要確認土地是否合法農業使用。", [_missing("land_use")]
        if any(token in land_use for token in ("合法", "農業使用", "農地")):
            return "MATCH", "土地使用狀態已初步符合。", []
        return "NOT_RELEVANT", "目前提供的土地使用狀態不符。", []
    if _contains_any(text, ("農保", "職業災害保險")):
        key = "insured_farmer"
        if _is_missing(profile, key):
            return "NEED_INFO", "還需要確認農保／保險身分。", [_missing(key)]
        return ("MATCH", "已提供保險身分資訊。", []) if profile.get(key) is True else (
            "NOT_RELEVANT", "目前的保險身分不符合這項條件。", []
        )

    # Crop names/categories are useful evidence even when the text has no
    # numeric rule. Explicit metadata crop scopes are handled earlier.
    crop_values = _as_list(profile.get("crops"))
    mentioned_crops = [crop for crop in _KNOWN_CROPS if _text(crop) in text]
    if mentioned_crops:
        if _is_missing(profile, "crops"):
            return "NEED_INFO", "還需要確認作物品項。", [_missing("crops")]
        if any(_same_text(crop, mentioned) for crop in crop_values for mentioned in mentioned_crops):
            return "MATCH", "作物品項與這筆條件有交集。", []
        return "NOT_RELEVANT", "作物品項與這筆條件不相符。", []

    # Existing profile evidence can support a simple criterion such as
    # "個人農民可申請" without inventing a hidden rule.
    evidence_values = []
    for key in ("applicant_type", "location", "intent", "crop_category", "certifications"):
        value = profile.get(key)
        evidence_values.extend(_as_list(value))
    if any(_text(value) and _text(value) in text for value in evidence_values):
        return "MATCH", "已提供與申請條件相關的資料。", []

    # Criteria carrying no recognized anchors should not silently claim a
    # match. REVIEW makes the uncertainty visible while preserving the
    # deterministic/fallback guarantee.
    if later_requirement:
        return "MATCH", "這項條件屬後續要求，不阻擋先開始申請。", []
    if _contains_any(text, ("須", "需", "必須", "申請人", "資格", "符合")):
        return "REVIEW", "這項自然語言條件需要承辦單位人工確認。", []
    return "MATCH", "已讀取這筆補助的申請說明。", []


def _criterion_entries(candidate: Candidate) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    criteria: Any = candidate.round.get("entry_criteria")
    if not criteria:
        criteria = candidate.variant.get("entry_criteria")
    if not criteria:
        criteria = candidate.program.get("entry_criteria")
    if isinstance(criteria, Mapping) or isinstance(criteria, str):
        criteria = [criteria]
    if not isinstance(criteria, list):
        criteria = []

    # New hierarchy records may retain a top-level compatibility marker (or an
    # old flat tree) alongside real natural-language criteria. Prefer the
    # hierarchy criteria whenever present; only use the legacy tree when no
    # entry criteria survived normalization.
    legacy_tree: dict[str, Any] | None = None
    if not criteria:
        for owner in (candidate.round, candidate.variant, candidate.program):
            tree = owner.get("eligibility")
            if isinstance(tree, Mapping):
                legacy_tree = dict(tree)
                break
    return [_mapping(item) if not isinstance(item, str) else {"text": item}
            for item in criteria], legacy_tree


@dataclass
class CriteriaDecision:
    status: MatchStatus
    reasons: list[str]
    missing_info: list[dict[str, Any]]   # 可含 options／option_map
    evidence_ids: list[str]


def _metadata_question(candidate: Candidate, key: str) -> str | None:
    for owner in (candidate.round, candidate.variant, candidate.program):
        metadata = owner.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        questions = metadata.get("missing_questions")
        if isinstance(questions, Mapping) and questions.get(key):
            return str(questions[key])
    return None


def _metadata_value(profile: Mapping[str, Any], key: str) -> Any:
    if key == "crop":
        return _get_profile_value(profile, "crop")
    if key in ("township", "region"):
        return _get_profile_value(profile, "township")
    return profile.get(key, _MISSING)


def metadata_entry_hints(candidate: Candidate, profile: Mapping[str, Any]) -> CriteriaDecision:
    """Apply small, explicit metadata hints used by demo fixtures.

    These are not a general rules language. They cover common scalar hints
    (age/area/years/booleans) and missing-info declarations supplied by a seed;
    the actual explanatory text remains in ``entry_criteria``.
    """
    metadata = _merged_metadata(candidate)
    reasons: list[str] = []
    missing: list[dict[str, str]] = []
    evidence: list[str] = []

    def need(key: str) -> None:
        missing.append(_missing(key, question=_metadata_question(candidate, key)))

    def numeric_check(key: str, *, minimum: float | None = None,
                      maximum: float | None = None,
                      exclusive_max: bool = False,
                      label: str = "數值") -> None:
        value = _metadata_value(profile, key)
        if _is_missing(profile, key):
            need(key)
            return
        parsed = _numeric(value)
        if parsed is None:
            reasons.append(f"{label}格式需要承辦單位確認。")
            return
        if minimum is not None and parsed < minimum:
            reasons.append(f"{label}未達 {minimum:g} 的申請門檻。")
            return
        if maximum is not None and ((parsed >= maximum) if exclusive_max else (parsed > maximum)):
            reasons.append(f"{label}超過申請上限 {maximum:g}。")
            return
        evidence.append(key)

    age_range = metadata.get("age_range")
    if isinstance(age_range, Mapping):
        numeric_check("age", minimum=_numeric(age_range.get("min")),
                      maximum=_numeric(age_range.get("max")), label="年齡")
    if metadata.get("farming_years_max_exclusive") is not None:
        numeric_check("farming_years", maximum=_numeric(metadata["farming_years_max_exclusive"]),
                      exclusive_max=True, label="從農年資")

    for key, hint in (("requires_self_operated", "self_operated"),
                      ("requires_operating_site", "has_operating_site"),
                      ("self_use_required", "self_use"),
                      ("replacement_required", "replacement_same_type"),
                      ("replacement_required_by_default", "replacement_same_type"),
                      ("project_guidance_required", "project_guidance")):
        if not metadata.get(key):
            continue
        value = _metadata_value(profile, hint)
        if _is_missing(profile, hint):
            need(hint)
        elif value is True:
            evidence.append(hint)
        else:
            reasons.append(f"目前提供的「{hint}」狀態不符合這筆補助要求。")

    area_max = metadata.get("requested_facility_area_max_ha")
    if area_max is not None:
        numeric_check("requested_facility_area_ha", maximum=_numeric(area_max),
                      label="設施面積")
    area_min = metadata.get("individual_min_area_ha")
    if area_min is not None and _text(profile.get("applicant_type")) in {
        "individual_farmer", "individual", "farmer", "農民", "自然人農民"
    }:
        numeric_check("land_area_ha", minimum=_numeric(area_min), label="耕作面積")
    group_min = metadata.get("group_combined_min_area_ha")
    if group_min is not None and _text(profile.get("applicant_type")) not in {
        "individual_farmer", "individual", "farmer", "農民", "自然人農民"
    }:
        numeric_check("land_area_ha", minimum=_numeric(group_min), label="團體共同面積")

    crop_thresholds = metadata.get("crop_area_thresholds_ha")
    if isinstance(crop_thresholds, Mapping):
        crop_category = profile.get("crop_category")
        crops = _as_list(profile.get("crops"))
        category = str(crop_category or "")
        if not category and any(_same_text(crop, "香蕉") for crop in crops):
            category = "果樹"
        threshold = crop_thresholds.get(category)
        if threshold is not None:
            numeric_check("land_area_ha", minimum=_numeric(threshold), label=f"{category}面積")
        elif _is_missing(profile, "crops") and _is_missing(profile, "crop_category"):
            need("crops")

    two_crop_mix = metadata.get("two_crop_mix")
    if isinstance(two_crop_mix, Mapping):
        crops = _as_list(profile.get("crops"))
        if _is_missing(profile, "crops"):
            need("crops")
        elif len(crops) < 2:
            reasons.append("這個方案需要兩種作物的經營資料。")
        else:
            evidence.append("crops")

    organic_ratio = metadata.get("organic_area_ratio_min")
    if organic_ratio is not None:
        ratio = _metadata_value(profile, "organic_area_ratio")
        if _is_missing(profile, "organic_area_ratio"):
            need("organic_area_ratio")
        elif (_numeric(ratio) or 0) < float(organic_ratio):
            reasons.append("有機／轉型驗證面積比例未達要求。")
        else:
            evidence.append("organic_area_ratio")

    boxes_min = metadata.get("beekeeping_boxes_min")
    if boxes_min is not None:
        boxes = profile.get("beehive_boxes", profile.get("hive_boxes", _MISSING))
        if _is_missing(profile, "beehive_boxes") and _is_missing(profile, "hive_boxes"):
            need("beehive_boxes")
        elif (_numeric(boxes) or 0) < float(boxes_min):
            reasons.append(f"蜂箱數未達 {float(boxes_min):g} 箱。")
        else:
            evidence.append("beehive_boxes")

    required = metadata.get("required_matching_facts")
    if isinstance(required, str):
        required = [required]
    if isinstance(required, list):
        for key in required:
            key = str(key)
            if _is_missing(profile, key):
                need(key)
            elif _metadata_value(profile, key) is False:
                reasons.append(f"目前提供的「{key}」狀態不符合要求。")
            else:
                evidence.append(key)

    required_certifications = metadata.get("required_certification_any")
    if required_certifications:
        certifications = _as_list(profile.get("certifications"))
        if _is_missing(profile, "certifications"):
            need("certifications")
        elif not any(_same_text(certification, required)
                     or _text(required) in _text(certification)
                     or _text(certification) in _text(required)
                     for certification in certifications for required in _as_list(required_certifications)):
            reasons.append("目前提供的驗證／登錄不在這筆補助的適用範圍。")
        else:
            evidence.append("certifications")

    if reasons:
        # A reason is a hard negative only for explicit scalar failures. A
        # malformed/unknown scalar is safer as REVIEW, but the demo values above
        # produce clear negative text and can be surfaced as NOT_RELEVANT.
        return CriteriaDecision("NOT_RELEVANT", reasons, [], evidence)
    if missing:
        return CriteriaDecision("NEED_INFO", ["還需要補充這筆補助的基本申請資訊。"], missing, evidence)
    return CriteriaDecision("MATCH", [], [], evidence)


def deterministic_entry_match(candidate: Candidate, profile: Mapping[str, Any]) -> CriteriaDecision:
    """Evaluate criteria with legacy leaves or conservative text heuristics."""
    from .engine import Tri, eval_node

    criteria, legacy_tree = _criterion_entries(candidate)
    reasons: list[str] = []
    missing: list[dict[str, str]] = []
    evidence: list[str] = []
    if legacy_tree is not None:
        trace: list[dict[str, Any]] = []
        try:
            overall = eval_node(legacy_tree, _facts_for_criterion(profile), trace)
        except Exception as exc:
            return CriteriaDecision("REVIEW", [f"條件格式需要人工確認：{exc}"], [], [])
        if overall is Tri.NO:
            failed = [item for item in trace if item.get("result") is Tri.NO]
            for item in failed:
                reasons.append(str(item.get("note") or item.get("legal_ref") or
                                   f"條件「{item.get('field')}」與目前資料不相符。"))
            return CriteriaDecision("NOT_RELEVANT", reasons or ["目前資料與申請條件不相符。"], [], [])
        if overall is Tri.UNKNOWN:
            for item in trace:
                if item.get("result") is Tri.UNKNOWN:
                    missing.append(_missing(str(item.get("field"))))
            return CriteriaDecision("NEED_INFO", ["還需要補充部分申請條件，才能判斷是否值得申請。"], missing, [])
        evidence.extend(str(item.get("legal_ref") or item.get("field"))
                       for item in trace if item.get("result") is Tri.YES)
        reasons.append("目前提供的資料符合這筆補助的基本條件。")
        # A flat seed can have both eligibility and normalized criteria. The
        # deterministic tree is authoritative for this compatibility path.
        return CriteriaDecision("MATCH", reasons, [], evidence)

    if not criteria:
        return CriteriaDecision("REVIEW", ["這筆補助尚未提供可供自動比對的入門條件。"], [], [])

    statuses: list[str] = []
    for index, criterion in enumerate(criteria):
        criterion_id = str(criterion.get("id") or f"criterion-{index + 1}")
        if ("field" in criterion and "op" in criterion and "value" in criterion):
            status, reason, criterion_missing = _explicit_criterion(criterion, profile)
        elif "all" in criterion or "any" in criterion:
            # A single small group is supported for data migrated from the old
            # seed; this does not expose or require a new rule language.
            trace: list[dict[str, Any]] = []
            try:
                result = eval_node(dict(criterion), _facts_for_criterion(profile), trace)
            except Exception:
                result = Tri.UNKNOWN
            if result is Tri.YES:
                status, reason, criterion_missing = "MATCH", str(criterion.get("text") or "群組條件已初步符合。"), []
            elif result is Tri.NO:
                status, reason, criterion_missing = "NOT_RELEVANT", "群組條件與目前資料不相符。", []
            else:
                status, reason, criterion_missing = "NEED_INFO", "群組條件仍缺少必要資訊。", [
                    _missing(str(item.get("field"))) for item in trace
                    if item.get("result") is Tri.UNKNOWN
                ]
        else:
            status, reason, criterion_missing = _natural_criterion(criterion, profile)
        statuses.append(status)
        reasons.append(reason)
        missing.extend(criterion_missing)
        if status == "MATCH":
            evidence.append(criterion_id)

    # Hard negatives dominate; then unresolved info; then human review.
    if "NOT_RELEVANT" in statuses:
        return CriteriaDecision("NOT_RELEVANT", reasons, [], evidence)
    if "NEED_INFO" in statuses:
        return CriteriaDecision("NEED_INFO", reasons, missing, evidence)
    if "REVIEW" in statuses:
        return CriteriaDecision("REVIEW", reasons, missing, evidence)
    return CriteriaDecision("MATCH", reasons, [], evidence)


class EntryCriteriaMatcher(Protocol):
    demo_mode: bool

    def match(self, candidate: Candidate, profile: Mapping[str, Any]) -> CriteriaDecision:
        ...


class DeterministicMatcher:
    demo_mode = True

    def match(self, candidate: Candidate, profile: Mapping[str, Any]) -> CriteriaDecision:
        return deterministic_entry_match(candidate, profile)


class AnthropicEntryCriteriaMatcher:
    """Optional structured adapter; every failure falls back locally."""

    demo_mode = False

    def __init__(self, *, timeout: float, fallback: EntryCriteriaMatcher | None = None,
                 model: str | None = None) -> None:
        self.timeout = timeout
        self.fallback = fallback or DeterministicMatcher()
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
        import anthropic  # delayed import keeps offline startup dependency-free
        self.client = anthropic.Anthropic(timeout=timeout)

    def _prompt(self, candidate: Candidate) -> str:
        criteria, _ = _criterion_entries(candidate)
        rows = [
            {"id": str(item.get("id") or index + 1),
             "text": str(item.get("text") or item.get("description") or "")}
            for index, item in enumerate(criteria)
        ]
        return (
            "You match a farmer's public MatchingProfile to human-readable entry criteria. "
            "Do not infer facts. Return JSON only with status MATCH, NEED_INFO, "
            "NOT_RELEVANT, or REVIEW; include reason, missing_info[{key,question}], "
            "and evidence_criterion_ids. Deadline and application dates are handled by code.\n"
            + json.dumps({"criteria": rows}, ensure_ascii=False)
        )

    def match(self, candidate: Candidate, profile: Mapping[str, Any]) -> CriteriaDecision:
        public_profile = _public_profile({
            key: value for key, value in profile.items()
            if not str(key).startswith("__")
        })
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system=self._prompt(candidate),
                messages=[{
                    "role": "user",
                    "content": json.dumps({"profile": public_profile}, ensure_ascii=False),
                }],
            )
            content = response.content[0].text if response.content else ""
            match = re.search(r"\{.*\}", content, re.S)
            payload = json.loads(match.group(0)) if match else {}
            status = str(payload.get("status") or "").upper()
            if status not in {"MATCH", "NEED_INFO", "NOT_RELEVANT", "REVIEW"}:
                raise ValueError("LLM 回傳了未知 status")
            missing = []
            for item in payload.get("missing_info") or []:
                if not isinstance(item, Mapping) or not item.get("key"):
                    continue
                reject_private_keys(item)
                missing.append(_missing(str(item["key"]), question=str(item.get("question") or "")))
            reasons = [str(item) for item in payload.get("reason") or [] if item]
            if not reasons and payload.get("why"):
                reasons = [str(payload["why"])]
            evidence = [str(item) for item in payload.get("evidence_criterion_ids") or []]
            return CriteriaDecision(status, reasons or ["依 entry criteria 初步比對完成。"], missing, evidence)
        except Exception:
            # A timeout, missing SDK feature, malformed JSON, or API outage is
            # never allowed to take down /match or expose private data.
            return self.fallback.match(candidate, profile)


def get_entry_criteria_matcher() -> EntryCriteriaMatcher:
    """Enable Anthropic only when both key and an explicit finite timeout exist."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    timeout_text = (
        os.environ.get("AIDSTATION_MATCH_TIMEOUT")
        or os.environ.get("MATCHING_LLM_TIMEOUT")
        or os.environ.get("ANTHROPIC_TIMEOUT")
    )
    if not key or not timeout_text:
        return DeterministicMatcher()
    try:
        timeout = float(timeout_text)
        if timeout <= 0 or timeout > 60:
            return DeterministicMatcher()
        return AnthropicEntryCriteriaMatcher(timeout=timeout)
    except Exception:
        return DeterministicMatcher()


def _authority(candidate: Candidate) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for owner in (candidate.program, candidate.variant, candidate.round):
        if isinstance(owner.get("authority"), Mapping):
            result.update(owner["authority"])
    return result


def _source(candidate: Candidate) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for owner in (candidate.program, candidate.variant, candidate.round):
        if isinstance(owner.get("source"), Mapping):
            result.update(owner["source"])
    return result


def _tasks(candidate: Candidate) -> list[dict[str, Any]]:
    raw: Any = None
    for owner in (candidate.round, candidate.variant, candidate.program):
        raw = owner.get("tasks") or owner.get("task_templates")
        if raw is not None:
            break
    if isinstance(raw, Mapping):
        raw = [raw]
    result: list[dict[str, Any]] = []
    for item in raw or []:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json", exclude_none=True)
        if isinstance(item, Mapping):
            result.append(dict(item))
    return result


def _form_template(candidate: Candidate) -> dict[str, Any] | None:
    raw: Any = None
    for owner in (candidate.round, candidate.variant, candidate.program):
        raw = owner.get("form_template")
        if raw is not None:
            break
    if raw is None:
        form_id = next((owner.get("form_template_id") for owner in
                        (candidate.round, candidate.variant, candidate.program)
                        if owner.get("form_template_id")), None)
        if form_id:
            return {"id": str(form_id), "name": str(form_id), "fields": []}
        return None
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(mode="json", exclude_none=True)
    if not isinstance(raw, Mapping):
        return None
    result = dict(raw)
    fields: list[dict[str, Any]] = []
    for field in result.get("fields") or []:
        if hasattr(field, "model_dump"):
            field = field.model_dump(mode="json", exclude_none=True)
        if isinstance(field, Mapping):
            fields.append(dict(field))
    result["fields"] = fields
    return result


def _dedupe_missing(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get("key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        entry: dict[str, Any] = {
            "key": key,
            "question": str(item.get("question") or _missing(key)["question"]),
        }
        # 保留白話選項與轉換表，否則農民會看到空白輸入框而不是按鈕
        for extra in ("options", "option_map"):
            if item.get(extra):
                entry[extra] = item[extra]
        result.append(entry)
    return result


def _result(candidate: Candidate, *, status: MatchStatus, reasons: Sequence[str],
            missing: Sequence[Mapping[str, Any]], evidence: Sequence[str],
            window: Mapping[str, Any], deadline: str | None,
            extra_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    name = candidate.variant.get("name") or candidate.program.get("name") or candidate.variant_id
    summary = candidate.variant.get("summary") or candidate.program.get("summary") or ""
    category = candidate.round.get("category") or candidate.variant.get("category") or candidate.program.get("category")
    reason = [str(item) for item in reasons if item]
    if not reason:
        reason = {
            "MATCH": ["目前資料與這筆補助的入門條件相符。"],
            "NEED_INFO": ["還需要補充少量資訊。"],
            "NOT_RELEVANT": ["目前資料與這筆補助的條件不相符。"],
            "REVIEW": ["這筆補助需要承辦單位人工確認。"],
            "CLOSED": ["目前不在申請期間內。"],
        }[status]
    result = {
        "program_id": candidate.program_id,
        "variant_id": candidate.variant_id,
        "round_id": candidate.round_id,
        "name": str(name),
        "summary": str(summary),
        "category": category,
        "status": status,
        "reason": reason,
        "why": reason,
        "missing_info": _dedupe_missing(missing),
        "evidence_criterion_ids": list(dict.fromkeys(str(item) for item in evidence if item)),
        "deadline": deadline,
        "window": dict(window),
        "authority": _authority(candidate),
        "source": _source(candidate),
        "tasks": _tasks(candidate),
        "form_template": _form_template(candidate),
        "metadata": dict(extra_metadata or _merged_metadata(candidate)),
    }
    # Legacy details remain available for callers that used /match cards before
    # the hierarchy migration, but no profile values are copied here.
    for key in ("amount", "documents"):
        if key in candidate.program:
            result[key] = candidate.program[key]
    # Do not run the profile-key validator over the whole response: the public
    # result contract legitimately has ``name`` and authority/source records
    # may legitimately have ``tel``. The profile itself was recursively
    # validated before matching, and no profile value is copied into this
    # result.
    return result


def _urgency(deadline: str | None, today: date) -> int:
    end = _date_value(deadline)
    return (end - today).days if end else 99999


def _next_question(results: Sequence[Mapping[str, Any]], asked: set[str], today: date,
                   profile: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    choices: list[tuple[int, int, int, int, dict[str, Any]]] = []
    profile = profile or {}
    intent_text = _text(profile.get("equipment_intent") or profile.get("intent"))
    machine_intent = bool(_category_groups(intent_text) & {"machine"})
    for result_index, result in enumerate(results):
        if result.get("status") != "NEED_INFO":
            continue
        urgency = _urgency(result.get("deadline"), today)
        for missing_index, item in enumerate(result.get("missing_info") or []):
            key = str(item.get("key") or "")
            if not key or key in asked:
                continue
            question = {"key": key, "question": str(item.get("question") or _missing(key)["question"])}
            # The Hero path has already established a machine purchase intent;
            # ask the model/牌型 question before unrelated optional details
            # from another machine variant.  In every other case urgency and
            # result order remain the deterministic tie-breakers.
            intent_priority = 0 if machine_intent and key == "machine_model_status" else 1
            choices.append((urgency, intent_priority, result_index, missing_index, question))
    if not choices:
        return None
    choices.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    return choices[0][4]


def match_profile(programs: Sequence[Any], profile: MatchingProfile | Mapping[str, Any],
                  *, asked: Sequence[str] | None = None, today: date | str | None = None,
                  matcher: EntryCriteriaMatcher | None = None) -> dict[str, Any]:
    """Return the canonical match response for one public MatchingProfile."""
    _, facts, public_profile = _normalise_profile(profile)
    asked_list = [str(item) for item in (asked or [])]
    reject_private_keys(asked_list, path="asked")
    asked_set = set(asked_list)
    today_value = _date_value(today) if today is not None else date.today()
    if today_value is None:
        raise MatchingInputError("today 必須是 ISO 日期（YYYY-MM-DD）")
    active_matcher = matcher or get_entry_criteria_matcher()

    results: list[dict[str, Any]] = []
    for candidate in iter_candidates(programs):
        window, _start, end = _window(candidate)
        prefilter = metadata_prefilter(candidate, facts, today_value)
        if prefilter.status in {"CLOSED", "NOT_RELEVANT"}:
            decision_status: MatchStatus = prefilter.status
            reasons = prefilter.reason or []
            missing = []
            evidence: list[str] = []
        else:
            # Metadata hints are deliberately tiny and explicit (age/area,
            # required public facts, and booleans). They complement the
            # human-readable entry-criteria matcher; neither side is a second
            # general-purpose rule DSL.
            metadata_decision = metadata_entry_hints(candidate, facts)
            criteria_decision = active_matcher.match(candidate, facts)
            decisions = [metadata_decision, criteria_decision]
            statuses = {decision.status for decision in decisions}
            if "NOT_RELEVANT" in statuses:
                decision_status = "NOT_RELEVANT"
            elif "REVIEW" in statuses:
                decision_status = "REVIEW"
            elif "NEED_INFO" in statuses or prefilter.status == "NEED_INFO":
                decision_status = "NEED_INFO"
            else:
                decision_status = "MATCH"
            reasons = [
                *(prefilter.reason or []),
                *(reason for decision in decisions for reason in decision.reasons),
            ]
            missing = [
                *(prefilter.missing_info or []),
                *(item for decision in decisions for item in decision.missing_info),
            ]
            evidence = [
                item for decision in decisions for item in decision.evidence_ids
            ]

        results.append(_result(
            candidate,
            status=decision_status,
            reasons=reasons,
            missing=missing,
            evidence=evidence,
            window=window,
            deadline=end.isoformat() if end else None,
        ))

    results.sort(key=lambda item: (
        STATUS_ORDER.get(str(item.get("status")), 99),
        _urgency(item.get("deadline"), today_value),
        str(item.get("name") or ""),
    ))
    return {
        "profile": public_profile,
        "asked": asked_list,
        "today": today_value,
        "results": results,
        "next_question": _next_question(results, asked_set, today_value, facts),
        "disclaimer": "這是申請起點建議，最終認定仍以承辦單位為準。",
        "demo_mode": bool(getattr(active_matcher, "demo_mode", True)),
    }


# Friendly aliases for callers/tests that use the pipeline terminology.
match_matching_profile = match_profile
match_programs = match_profile
