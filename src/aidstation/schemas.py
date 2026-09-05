"""Shared contracts for the Futuremode demo.

The matching side of the product deliberately has a small, stable contract.
Government programme criteria remain human-readable text instead of being
forced into a second global rule language.  Private form data is intentionally
not modelled here: it belongs to the browser only.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PRIVATE_PROFILE_KEYS = frozenset({
    "full_name",
    "name",
    "national_id",
    "id_number",
    "birthday",
    "birth_date",
    "birth_year",
    "phone",
    "tel",
    "full_address",
    "address",
    "addr",
    "bank_account",
    "bank_branch",
    "parcel_numbers",
    "parcel_number",
    "signature",
    "contact",
    "private_profile",
    "private",
})


class _MatchingBase(BaseModel):
    """Allow new programme-specific matching facts without accepting PII."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def reject_private_fields(cls, value: Any) -> Any:
        private: set[str] = set()

        def walk(item: Any) -> None:
            if isinstance(item, dict):
                for key, child in item.items():
                    if key in PRIVATE_PROFILE_KEYS:
                        private.add(str(key))
                    walk(child)
            elif isinstance(item, list):
                for child in item:
                    walk(child)

        walk(value)
        if private:
            raise ValueError(
                "PrivateFormProfile 欄位只能留在瀏覽器本地，不能送到後端："
                + "、".join(sorted(private))
            )
        return value


class MatchingProfile(_MatchingBase):
    """Facts that can safely be used for subsidy discovery."""

    applicant_type: str | None = None
    age: int | float | None = None
    location: str | None = None
    crops: list[str] = Field(default_factory=list)
    land_area_ha: float | None = None
    farming_years: float | None = None
    certifications: list[str] = Field(default_factory=list)
    young_farmer: bool | None = None
    young_farmer_status: bool | None = None
    self_operated: bool | None = None
    land_use: str | None = None
    land_tenure: str | None = None
    has_land_use_proof: bool | None = None
    intent: str | None = None
    equipment_intent: str | None = None
    disaster_situation: str | None = None
    disaster_situation_details: str | None = None
    requested_facility_area_ha: float | None = None
    agriculture_training_hours: float | None = None
    agriculture_credits: float | None = None
    technical_qualification: list[str] = Field(default_factory=list)
    crop_category: str | None = None
    insured_farmer: bool | None = None
    is_farming: bool | None = None
    # 災害救助的法定判準。先前只存在於 fields.json，新引擎看不到，
    # 導致「損失幾成」與豁免條款無法參與比對。
    loss_rate: float | None = None            # 災損成數，0.2 ＝ 兩成（作業要點§6 門檻）
    land_doc: str | None = None               # 土地文件種類：書面租約／使用同意書／從農工作證明／無
    policy_enrolled_2y: bool | None = None    # 近兩年以同地參與政策並登錄 → 免附土地文件


class MatchRequest(BaseModel):
    """Canonical request for ``POST /match``.

    ``facts`` is retained as a short-lived compatibility bridge for the old
    profile page and existing integrations; new callers should send ``profile``.
    Neither branch can contain private-only fields.
    """

    model_config = ConfigDict(extra="forbid")

    profile: MatchingProfile | None = None
    facts: dict[str, Any] | None = None
    asked: list[str] = Field(default_factory=list)
    today: date | None = None

    @model_validator(mode="after")
    def require_profile(self) -> "MatchRequest":
        if self.profile is None and self.facts is None:
            raise ValueError("請提供 profile")
        if self.profile is None:
            self.profile = MatchingProfile.model_validate(self.facts or {})
        elif self.facts:
            raise ValueError("profile 與 facts 請擇一提供")
        return self


class EntryCriterion(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    text: str
    source: dict[str, Any] | None = None


class ApplicationWindow(BaseModel):
    model_config = ConfigDict(extra="allow")

    start: date | None = None
    end: date | None = None
    type: str | None = None
    note: str | None = None


class TaskTemplate(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    deadline: date | str | None = None
    depends_on: list[str] = Field(default_factory=list)
    description: str | None = None


class FormField(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    key: str | None = None
    label: str
    source: str | None = None
    storage: Literal["local_only", "matching", "display_only"] = "display_only"
    required: bool = False
    editable: bool = True


class FormTemplate(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    fields: list[FormField] = Field(default_factory=list)
    source: dict[str, Any] | None = None


class ApplicationRound(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    window: ApplicationWindow = Field(default_factory=ApplicationWindow)
    metadata: dict[str, Any] = Field(default_factory=dict)
    entry_criteria: list[EntryCriterion] = Field(default_factory=list)
    tasks: list[TaskTemplate] = Field(default_factory=list)
    form_template: FormTemplate | None = None
    form_template_id: str | None = None
    authority: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)


class Variant(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    summary: str = ""
    category: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    entry_criteria: list[EntryCriterion] = Field(default_factory=list)
    rounds: list[ApplicationRound] = Field(default_factory=list)
    authority: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)


class Program(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    summary: str = ""
    category: str | None = None
    variants: list[Variant] = Field(default_factory=list)
    authority: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)


MatchStatus = Literal["MATCH", "NEED_INFO", "NOT_RELEVANT", "REVIEW", "CLOSED"]


class MissingInfo(BaseModel):
    key: str
    question: str
    # 白話選項，讓長輩用按的不用打字（設計建議書 §4.1）。
    # option_map 把選項轉回內部值（「超過一半」→ 0.6），來源是 data/fields.json。
    options: list[str] | None = None
    option_map: dict[str, Any] | None = None


class MatchResult(BaseModel):
    program_id: str
    variant_id: str
    round_id: str
    name: str
    summary: str = ""
    category: str | None = None
    status: MatchStatus
    reason: list[str] = Field(default_factory=list)
    missing_info: list[MissingInfo] = Field(default_factory=list)
    evidence_criterion_ids: list[str] = Field(default_factory=list)
    deadline: str | None = None
    window: dict[str, Any] = Field(default_factory=dict)
    authority: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    tasks: list[TaskTemplate] = Field(default_factory=list)
    form_template: FormTemplate | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MatchResponse(BaseModel):
    profile: MatchingProfile
    results: list[MatchResult] = Field(default_factory=list)
    next_question: MissingInfo | None = None
    disclaimer: str = "這是申請起點建議，最終認定仍以承辦單位為準。"
    demo_mode: bool = True
    today: date
