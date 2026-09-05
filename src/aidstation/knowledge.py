"""補助知識庫載入、正規化與驗證。

補助資料仍以 JSON 掛載（``data/programs/*.json``），但執行期的主模型是
``Program -> Variant -> ApplicationRound``。既有 demo seed 使用舊的 flat
``eligibility/documents/window`` 格式，因此載入時會包成一個 default variant
與 round；原始欄位仍保留在 model 的 extra fields，讓舊的 flow/engine 可以繼續
工作。新資料可以直接提供自然語言 ``entry_criteria``、tasks 與 form template，
不需要把每一條公文規則塞進全域 fields.json 或另一套 DSL。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .fields import DATA_DIR, load_fields
from .schemas import (
    ApplicationRound,
    EntryCriterion,
    FormField,
    FormTemplate,
    Program,
    TaskTemplate,
    Variant,
)

REQUIRED_KEYS = ("id", "name")
OPERATORS = ("=", "!=", "in", "not_in", ">=", "<=", ">", "<")


class LoadedProgram(Program):
    """A schema ``Program`` with a tiny mapping compatibility surface.

    The original flow and admin code predate the shared Pydantic models and use
    ``program["id"]``/``program.get(...)``. Keeping those two operations here
    avoids a broad rewrite of unrelated modules while callers of the new
    contract still receive a real ``Program`` model.
    """

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def _as_date(value: Any) -> Any:
    """Return an ISO-like value as a date when possible.

    Invalid dates are left as-is for validation/reporting. The shared models use
    ``date | None`` for canonical boundaries, so callers can distinguish an
    unknown date from a valid one without guessing.
    """
    from datetime import date, datetime

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        value = value.strip()
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return value
    return value


def _window_payload(raw: Any) -> dict[str, Any]:
    """Normalise common window aliases while retaining legacy ``open/close``."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        return {"note": raw}
    if not isinstance(raw, Mapping):
        return {}

    result = dict(raw)
    start = next((result.get(key) for key in
                  ("start", "open", "from", "start_date")
                  if result.get(key) is not None), None)
    end = next((result.get(key) for key in
                ("end", "close", "to", "end_date")
                if result.get(key) is not None), None)
    if start is not None:
        result["start"] = _as_date(start)
        result.setdefault("open", start)
    if end is not None:
        result["end"] = _as_date(end)
        result.setdefault("close", end)
    return result


def _criterion_text(raw: Mapping[str, Any]) -> str:
    """Make a readable criterion sentence for old leaf-shaped criteria."""
    if raw.get("text") is not None:
        return str(raw["text"])
    if raw.get("description") is not None:
        return str(raw["description"])
    field = raw.get("field")
    op = raw.get("op")
    value = raw.get("value")
    if field is None:
        return ""
    if isinstance(value, list):
        value_text = "、".join(map(str, value))
    else:
        value_text = str(value)
    return f"{field} {op or '='} {value_text}"


def _normalise_criteria(raw: Any, prefix: str) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, (str, Mapping)):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    criteria: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            criteria.append({"id": f"{prefix}-criterion-{index + 1}",
                             "text": item})
            continue
        if not isinstance(item, Mapping):
            continue
        criterion = dict(item)
        criterion.setdefault("id", f"{prefix}-criterion-{index + 1}")
        criterion["text"] = _criterion_text(criterion)
        source = dict(criterion.get("source") or {})
        if criterion.get("legal_ref") and "legal_ref" not in source:
            source["legal_ref"] = criterion["legal_ref"]
        if source:
            criterion["source"] = source
        criteria.append(criterion)
    return criteria


def _normalise_tasks(raw: Any, prefix: str) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, (str, Mapping)):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    tasks: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            tasks.append({"id": f"{prefix}-task-{index + 1}", "title": item})
            continue
        if not isinstance(item, Mapping):
            continue
        task = dict(item)
        task.setdefault("id", f"{prefix}-task-{index + 1}")
        task.setdefault("title", task.get("name") or task.get("label") or
                        f"申請步驟 {index + 1}")
        tasks.append(task)
    return tasks


def _normalise_form(raw: Any, prefix: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return {"id": raw, "name": raw, "fields": []}
    if not isinstance(raw, Mapping):
        return None

    form = dict(raw)
    form.setdefault("id", f"{prefix}-form")
    form.setdefault("name", form.get("title") or form["id"])
    fields: list[dict[str, Any]] = []
    for index, item in enumerate(form.get("fields") or []):
        if isinstance(item, str):
            item = {"label": item}
        if not isinstance(item, Mapping):
            continue
        field = dict(item)
        field.setdefault("id", field.get("key") or f"field-{index + 1}")
        field.setdefault("label", field.get("name") or field["id"])
        storage = field.get("storage")
        if storage not in {"local_only", "matching", "display_only"}:
            field["storage"] = "display_only"
        fields.append(field)
    form["fields"] = fields
    return form


def _normalise_round(raw: Mapping[str, Any], *, prefix: str,
                     inherited: Mapping[str, Any] | None = None,
                     inherited_criteria: Any = None,
                     inherited_tasks: Any = None,
                     inherited_form: Any = None,
                     inherited_authority: Mapping[str, Any] | None = None,
                     inherited_source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    round_data = dict(raw)
    round_id = str(round_data.get("id") or f"{prefix}-round")
    round_data["id"] = round_id
    round_data.setdefault("name", round_data.get("title") or round_id)

    window = round_data.get("window")
    if window is None:
        window = round_data.get("application_window")
    if window is None:
        window = inherited
    round_data["window"] = _window_payload(window)

    criteria = round_data.get("entry_criteria")
    if criteria is None:
        criteria = round_data.get("criteria")
    if criteria is None:
        criteria = inherited_criteria
    round_data["entry_criteria"] = _normalise_criteria(criteria, round_id)

    tasks = round_data.get("tasks")
    if tasks is None:
        tasks = round_data.get("task_templates")
    if tasks is None:
        tasks = inherited_tasks
    round_data["tasks"] = _normalise_tasks(tasks, round_id)

    form = round_data.get("form_template")
    if form is None:
        form = round_data.get("form")
    if form is None:
        form = inherited_form
    if form is not None:
        round_data["form_template"] = _normalise_form(form, round_id)
    elif round_data.get("form_template_id") is not None:
        round_data["form_template"] = None

    if not round_data.get("authority") and inherited_authority:
        round_data["authority"] = dict(inherited_authority)
    if not round_data.get("source") and inherited_source:
        round_data["source"] = dict(inherited_source)
    round_data.setdefault("authority", {})
    round_data.setdefault("source", {})
    return round_data


def _normalise_variant(raw: Mapping[str, Any], *, program: Mapping[str, Any],
                      index: int) -> dict[str, Any]:
    variant = dict(raw)
    program_id = str(program.get("id"))
    variant_id = str(variant.get("id") or f"{program_id}-variant-{index + 1}")
    variant["id"] = variant_id
    variant.setdefault("name", variant.get("title") or program.get("name") or variant_id)
    variant.setdefault("summary", variant.get("description") or program.get("summary") or "")
    variant.setdefault("category", variant.get("category") or program.get("category"))
    variant.setdefault("metadata", {})

    program_window = program.get("window") or program.get("application_window")
    variant_window = variant.get("window") or variant.get("application_window") or program_window
    program_criteria = program.get("entry_criteria") or program.get("criteria")
    variant_criteria = variant.get("entry_criteria") or variant.get("criteria") or program_criteria
    program_tasks = program.get("tasks") or program.get("task_templates")
    variant_tasks = variant.get("tasks") or variant.get("task_templates") or program_tasks
    program_form = program.get("form_template") or program.get("form")
    variant_form = variant.get("form_template") or variant.get("form") or program_form
    authority = variant.get("authority") or program.get("authority") or {}
    source = variant.get("source") or program.get("source") or {}

    rounds = variant.get("rounds")
    if rounds is None:
        rounds = variant.get("application_rounds")
    if rounds is None and variant.get("round") is not None:
        rounds = [variant["round"]]
    if rounds is None:
        # A flat seed has one application round. Keep legacy eligibility and
        # documents on the parent program as well; the matcher can use either.
        rounds = [{}]
    if isinstance(rounds, Mapping):
        rounds = [rounds]
    if not isinstance(rounds, list) or not rounds:
        rounds = [{}]

    normalised_rounds: list[dict[str, Any]] = []
    for round_index, item in enumerate(rounds):
        if not isinstance(item, Mapping):
            item = {}
        round_prefix = f"{variant_id}-round-{round_index + 1}"
        normalised_rounds.append(_normalise_round(
            item,
            prefix=round_prefix,
            inherited=variant_window,
            inherited_criteria=variant_criteria,
            inherited_tasks=variant_tasks,
            inherited_form=variant_form,
            inherited_authority=authority,
            inherited_source=source,
        ))
    variant["rounds"] = normalised_rounds
    variant["entry_criteria"] = _normalise_criteria(
        variant.get("entry_criteria") or program_criteria, variant_id)
    variant.setdefault("authority", dict(authority))
    variant.setdefault("source", dict(source))
    return variant


def normalize_program(program: Mapping[str, Any]) -> LoadedProgram:
    """Convert one flat or hierarchical JSON object into shared schema models."""
    if not isinstance(program, Mapping):
        raise ValueError("補助資料必須是一個 JSON 物件")
    raw = dict(program)
    if not raw.get("id") or not raw.get("name"):
        missing = [key for key in ("id", "name") if not raw.get(key)]
        raise ValueError("補助資料缺少必要欄位：" + "、".join(missing))

    raw.setdefault("summary", raw.get("description") or "")
    raw.setdefault("authority", {})
    raw.setdefault("source", {})

    variants = raw.get("variants")
    if variants is None and raw.get("variant") is not None:
        variants = [raw["variant"]]
    if variants is None:
        variants = [{}]
    if isinstance(variants, Mapping):
        variants = [variants]
    if not isinstance(variants, list) or not variants:
        variants = [{}]
    raw["variants"] = [
        _normalise_variant(item if isinstance(item, Mapping) else {},
                           program=raw, index=index)
        for index, item in enumerate(variants)
    ]

    # Keep top-level flat fields for old clients and ensure the model hierarchy
    # is available to new matching callers.
    if raw.get("window") is not None:
        raw["window"] = _window_payload(raw["window"])
    if raw.get("entry_criteria") is not None:
        raw["entry_criteria"] = _normalise_criteria(
            raw["entry_criteria"], str(raw["id"]))
    if raw.get("tasks") is not None:
        raw["tasks"] = _normalise_tasks(raw["tasks"], str(raw["id"]))
    if raw.get("form_template") is not None:
        raw["form_template"] = _normalise_form(raw["form_template"], str(raw["id"]))

    # Explicitly touch the imported schema types here: this makes malformed
    # nested payloads fail during startup, while Program.model_validate below
    # remains the single source of truth for field coercion.
    _ = (ApplicationRound, EntryCriterion, FormField, FormTemplate,
         TaskTemplate, Variant)
    return LoadedProgram.model_validate(raw)


def program_dict(program: Program | Mapping[str, Any]) -> dict[str, Any]:
    """Return a plain model/dict representation for compatibility consumers."""
    if hasattr(program, "model_dump"):
        return program.model_dump()
    return dict(program)


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

    flat legacy seed 的條件樹仍會對照 fields.json 驗證；新 hierarchy 的
    ``entry_criteria`` 是人類可讀文字，不會被誤當成全域 DSL 驗證。後台存檔
    與啟動載入共用這套規則——後台存得進去的，啟動就一定載得起來。
    """
    prefix = f"{label} " if label else ""
    if not isinstance(program, dict):
        return [f"{prefix}資料必須是一個 JSON 物件"]
    errors = [f"{prefix}缺少必要欄位：{k}" for k in REQUIRED_KEYS if k not in program]

    # A hierarchy payload is intentionally permissive about natural-language
    # criteria, but its container shapes should be clear enough to fail early.
    # ``normalize_program`` performs the detailed Pydantic coercion on startup.
    if "variants" in program:
        variants = program.get("variants")
        if not isinstance(variants, list) or not variants:
            errors.append(f"{prefix}variants 必須是至少一個物件的清單")
        else:
            for i, variant in enumerate(variants):
                if not isinstance(variant, dict):
                    errors.append(f"{prefix}variants[{i}] 必須是物件")
                    continue
                rounds = variant.get("rounds", variant.get("application_rounds"))
                if rounds is not None and not isinstance(rounds, (list, dict)):
                    errors.append(f"{prefix}variants[{i}].rounds 必須是清單或物件")
                criteria = variant.get("entry_criteria", variant.get("criteria"))
                if criteria is not None and not isinstance(criteria, (list, str, dict)):
                    errors.append(f"{prefix}variants[{i}].entry_criteria 格式不合法")

    top_criteria = program.get("entry_criteria", program.get("criteria"))
    if top_criteria is not None and not isinstance(top_criteria, (list, str, dict)):
        errors.append(f"{prefix}entry_criteria 格式不合法")

    if "eligibility" in program:
        sub: list[str] = []
        _check_node(program["eligibility"], fields, sub)
        errors += [prefix + e for e in sub]
    elif "variants" not in program and "entry_criteria" not in program:
        # Preserve the old contract for flat records: they need a deterministic
        # eligibility tree. New records may use only entry_criteria text.
        errors.append(f"{prefix}缺少必要欄位：eligibility")
    return errors


def load_programs(programs_dir: Path | None = None,
                  fields: dict | None = None) -> list[LoadedProgram]:
    d = programs_dir or (DATA_DIR / "programs")
    fields = fields or load_fields()
    programs: list[LoadedProgram] = []
    for path in sorted(d.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        errors = validate_program(p, fields, label=path.name)
        if errors:
            raise ValueError("；".join(errors))
        try:
            programs.append(normalize_program(p))
        except Exception as exc:
            raise ValueError(f"{path.name} schema 正規化失敗：{exc}") from exc
    return programs
