"""對話流程引擎（狀態機）：LINE 與 PWA 共用，不依賴任何通訊平台。

設計原則（《系統設計建議書》§4.1）：
- 一次一題、每題有按鈕選項、3~5 題內必出結果
- 「我卡住了」隨時可按 → 先一題三選項釐清卡點，再給對應協助
- 公文流程：文到型期限必問收文日
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from . import blockers
from .document import build_plain_card, get_translator
from . import engine as matching_engine
from .engine import match_all, next_question
from .extract import get_extractor
from .extract import MATCHING_PROFILE_KEYS, validate_facts
from .fields import DATA_DIR, load_fields, normalize_facts
from .knowledge import load_programs

MAX_QUESTIONS = 5
# The legacy disaster flow historically needed five questions.  New
# MatchingProfile flows are intentionally tighter: a matcher can ask at most
# three missing-info questions before returning a recommendation payload.
NEW_MAX_QUESTIONS = 3
STUCK_BUTTON = "我卡住了"
STUCK_REASONS = ["太麻煩了", "文件生不出來", "看不懂"]

# 求助回覆依情境不同：在「查詢結果」卡住 vs 在「公文」卡住，該給的幫助不一樣
STUCK_HELP_RESULTS = {
    "太麻煩了": ("可以找人幫你辦：農會推廣員、公所農業課、村里幹事都能協助，"
               "你只要帶身分證件過去。也可以請家人用這個系統代你操作。"),
    "文件生不出來": ("先別放棄——很多文件其實可以用別的方式代替（例如有申報過政策就免附土地文件）。"
                 "帶著你有的東西去公所農業課問一次，或打電話給承辦科室確認替代方案。"),
    "看不懂": ("我換個方式說：上面每一張卡片就是一項你可能可以申請的補助，"
             "最重要的是「⏰ 期限」和「📄 要帶的東西」。\n"
             "想多了解哪一項，把它的名字打給我；"
             "或帶身分證去農會或公所農業課，他們會一步一步幫你辦。"),
}
STUCK_HELP_DOCUMENT = {
    **STUCK_HELP_RESULTS,
    "看不懂": ("把公文拍照傳上來，我翻譯成白話給你；"
             "或直接打公文右上角的承辦電話，請對方用白話說明。"),
}

_MATCHING_LABELS = {
    "applicant_type": "申請人類型",
    "age": "年齡",
    "location": "地點",
    "crops": "作物",
    "land_area_ha": "耕作面積",
    "farming_years": "從農年資",
    "certifications": "驗證／登錄",
    "intent": "申請意圖",
    "equipment_intent": "想辦的農機",
    "machine_model_status": "公告牌型",
    "replacement_same_type": "是否同機種汰換",
    "old_fuel_machine_year": "舊燃油農機年份",
    "ghg_reduction_consent": "溫室氣體減量效益歸屬",
    "self_operated": "本人實際經營",
    "has_operating_site": "有實際營運場所",
    "requested_facility_area_ha": "申請設施面積",
}

_MATCHING_OPTIONS = {
    "machine_model_status": ["有，在公告補助牌型內", "還沒有品牌或型號", "不確定"],
    "replacement_same_type": ["是，同機種", "不是", "不確定"],
    "ghg_reduction_consent": ["同意", "不同意", "不確定"],
    "self_operated": ["是", "不是", "不確定"],
    "has_operating_site": ["有", "沒有", "不確定"],
}


def _plain(value: Any) -> Any:
    """Turn a dict-like Pydantic result into plain JSON-compatible data."""
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=False)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _is_new_program(program: Any) -> bool:
    program = _plain(program)
    return isinstance(program, dict) and isinstance(program.get("variants"), list) \
        and bool(program.get("variants"))


@dataclass
class Session:
    """單一使用者的對話狀態（LINE 以 userId 為鍵；記憶體版，MVP 用）。"""
    facts: dict[str, Any] = field(default_factory=dict)
    asked: set[str] = field(default_factory=set)
    pending_field: str | None = None      # 等待回答的欄位
    pending_question: dict | None = None  # 新 matcher 的 missing_info（可含 options）
    pending_stuck: bool = False           # 等待「卡住原因」三選一
    pending_doc: dict | None = None       # 等待收文日的公文
    questions_asked: int = 0
    last_context: str = "results"         # "results"＝查詢流程｜"document"＝公文流程
    profile_mode: str | None = None        # lock legacy/new flow after first turn

    @property
    def profile(self) -> dict[str, Any]:
        """MatchingProfile 相容別名；PrivateFormProfile 永不放進此物件。"""
        return self.facts

    @profile.setter
    def profile(self, value: dict[str, Any]) -> None:
        self.facts = dict(value or {})


@dataclass
class Reply:
    text: str
    options: list[str] | None = None
    payload: dict | None = None   # 結構化資料：網頁端用來畫卡片（LINE 端可忽略）


class Flow:
    def __init__(self, today: date | None = None):
        self.fields = load_fields()
        # ``load_programs`` is intentionally kept for the old deterministic
        # engine.  New fixtures are read as Program/Variant/Round dictionaries
        # as well, so this adapter remains usable while the backend agent is
        # migrating its loader and matcher.
        self.programs = [_plain(p) for p in load_programs(fields=self.fields)]
        # ``load_programs`` normalizes flat records into the new hierarchy, so
        # classify legacy files before that adapter erases their original
        # shape.  The disaster/injury smoke path still uses the old engine.
        self.legacy_programs = self._load_legacy_programs()
        self.demo_programs = self._load_demo_programs()
        self.extractor = get_extractor(self.fields)
        self.translator = get_translator()
        self.today = today or self._demo_today() or date.today()

    @staticmethod
    def _demo_today() -> date | None:
        if os.environ.get("DEMO_MODE", "").strip().lower() not in {
            "1", "true", "yes", "on"
        }:
            return None
        raw = os.environ.get("DEMO_DATE", "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None

    @staticmethod
    def _load_legacy_programs() -> list[dict]:
        programs: list[dict] = []
        directory = DATA_DIR / "programs"
        for path in sorted(directory.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    program = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(program, dict) and not _is_new_program(program) \
                    and isinstance(program.get("eligibility"), dict):
                programs.append(program)
        return programs

    @staticmethod
    def _load_demo_programs() -> list[dict]:
        programs: list[dict] = []
        directory = DATA_DIR / "programs"
        for path in sorted(directory.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    program = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if _is_new_program(program):
                programs.append(program)
        return programs

    # ---- 主入口 ----------------------------------------------------------

    def handle_text(self, session: Session, text: str) -> Reply:
        text = text.strip()
        if text == STUCK_BUTTON:
            session.pending_stuck = True
            return Reply("哪裡卡住了？跟我說，我幫你想辦法：", STUCK_REASONS)
        if session.pending_stuck:
            return self._handle_stuck(session, text)
        if session.pending_doc is not None:
            return self._handle_received_date(session, text)
        preface = None
        if session.pending_field:
            preface = self._apply_answer(session, text)
        else:
            extracted = self.extractor.extract(text)
            session.facts.update(extracted)
            # 抽取器的地點是縣市層級，認不出「玉井」這種鄉鎮名。
            # 這裡補一層：直接在原句裡找公告涵蓋的鄉鎮，省下反問一題。
            if "township" not in session.facts:
                found = self._township_in_text(text)
                if found:
                    session.facts["township"] = found
                    session.asked.add("township")
        reply = self._advance(session)
        if preface:
            reply.text = preface + "\n\n" + reply.text
        return reply

    def handle_document_text(self, session: Session, ocr_text: str) -> Reply:
        """公文流程入口（影像經 OCR 後的文字）。"""
        session.last_context = "document"
        doc = self.translator.translate(ocr_text)
        card = build_plain_card(doc, today=self.today)
        if card["deadline"].get("ask_received_date"):
            session.pending_doc = doc
            return Reply(f"這是一張「{card['deadline']['rule_text']}」的公文。\n"
                         f"{card['deadline']['question']}",
                         ["今天", "昨天", "其他日期"])
        return Reply(self._render_card(card), card["actions"],
                     payload={"kind": "doc_card", "card": card})

    # ---- 內部步驟 --------------------------------------------------------

    def _handle_stuck(self, session: Session, text: str) -> Reply:
        session.pending_stuck = False
        table = STUCK_HELP_DOCUMENT if session.last_context == "document" else STUCK_HELP_RESULTS
        help_text = table.get(text)
        if help_text is None:
            return Reply("沒關係，你可以找農會推廣員、公所農業課或村里幹事幫忙，"
                         "或把卡住的地方再跟我說一次。")
        # 卡點去識別化入庫（§5.1「資料是副產品」）：只記原因與鄉鎮，不記人
        blockers.record(text, blockers.SOURCE_STUCK,
                        township=session.facts.get("township"))
        return Reply(help_text)

    def _handle_received_date(self, session: Session, text: str) -> Reply:
        today = self.today or date.today()
        received = None
        if text == "今天":
            received = today
        elif text == "昨天":
            received = today - timedelta(days=1)
        else:
            m = re.search(r"(\d{1,2})[/月](\d{1,2})", text)
            if m:
                received = date(today.year, int(m.group(1)), int(m.group(2)))
            else:
                try:
                    received = date.fromisoformat(text)
                except ValueError:
                    pass
        if received is None:
            return Reply("請告訴我收到的日期（例如：8/5），期限要從收文那天算才準。",
                         ["今天", "昨天"])
        card = build_plain_card(session.pending_doc, received_date=received, today=self.today)
        session.pending_doc = None
        return Reply(self._render_card(card), card["actions"],
                     payload={"kind": "doc_card", "card": card})

    def _apply_answer(self, session: Session, text: str) -> str | None:
        """套用回答。回傳值若非 None，會加在下一則回覆前面（例如查無作物的說明）。"""
        field_name = session.pending_field
        if field_name not in self.fields:
            return self._apply_matching_answer(session, text)
        spec = self.fields[field_name]
        value = spec.get("option_map", {}).get(text, text)
        session.asked.add(field_name)
        session.pending_field = None
        session.pending_question = None
        if value == "不確定":
            return None  # 不確定就先跳過，之後仍以「可能符合」呈現該補助
        if field_name == "township" and isinstance(value, str):
            matched, county_only = self._match_township(value)
            if matched:
                value = matched
            elif county_only:
                # 只答到縣市：維持未知（＝「可能符合」），不要判成不符合。
                # 農民只是講得籠統，不代表他不在救助地區內。
                towns = sorted(self._known_townships())
                hint = ("、".join(towns[:5]) + " 等") if towns else ""
                return (f"「{value.strip()}」是縣市，救助公告是按鄉鎮區公告的。\n"
                        f"方便的話再跟我說是哪一個區（例如 {hint}），我可以幫你對得更準；\n"
                        "先不確定也沒關係，下面會把可能有關的都列出來。")
            # 認不出來就照實寫入，讓限定地區的補助正確排除
        if field_name == "crop" and isinstance(value, str):
            matched = self._match_crop(value)
            if matched is None:
                # 查無此作物：照實寫入（讓限定品項的補助正確變為「先不用看」），
                # 並主動說明還有哪些路可走——不能讓人問完就沒下文。
                session.facts["crop"] = value.strip()
                return (f"目前的災損救助公告裡，還沒有「{value.strip()}」這個品項。\n"
                        "先別急，你還有這幾條路：\n"
                        "・打給公所農業課，問這次公告有沒有要增列你的作物\n"
                        "・下面幫你列出不分作物也能用的保障（保險、福利、貸款可問農會）")
            value = matched
        try:
            normalized = normalize_facts({field_name: value}, self.fields)
            # enum 選項題答非所問（打了不在合法值裡的字）→ 不寫入，避免污染判定
            if spec.get("type") == "enum" and spec.get("values") \
                    and normalized.get(field_name) not in spec["values"]:
                return None
            session.facts.update(normalized)
        except (ValueError, TypeError):
            pass  # 答非所問（如數字欄位打了文字）→ 不寫入，下一輪可再問
        return None

    def _apply_matching_answer(self, session: Session, text: str) -> str | None:
        """Apply a new matcher ``missing_info`` answer without fields.json DSL."""
        field_name = session.pending_field
        if not field_name:
            return None
        question = session.pending_question or {}
        option_map = question.get("option_map") or {}
        value = option_map.get(text, text.strip())
        # The Hero question is intentionally human-readable while the matcher
        # receives a stable programme-specific value.
        aliases = {
            "有，在公告補助牌型內": "listed_subsidized_model",
            "有，在公告補助牌型內。": "listed_subsidized_model",
            "listed_subsidized_model": "listed_subsidized_model",
            "還沒有品牌或型號": "model_not_confirmed",
            "還沒有品牌或型號。": "model_not_confirmed",
            "沒有品牌或型號": "model_not_confirmed",
            "不確定": "unknown",
            "unknown": "unknown",
        }
        value = aliases.get(value, value)
        session.asked.add(field_name)
        session.pending_field = None
        session.pending_question = None
        if value in (None, ""):
            return None
        # Do not let an answer accidentally introduce PII into the matching
        # profile.  Programme-specific non-private fields are normalized here;
        # fields known to the legacy dictionary keep its old normalization path.
        cleaned = validate_facts({field_name: value}, self.fields)
        if field_name in cleaned:
            session.facts[field_name] = cleaned[field_name]
        elif field_name not in {
            "full_name", "name", "national_id", "id_number", "birthday", "birth_date",
            "birth_year", "phone", "tel", "full_address", "address", "addr",
            "bank_account", "bank_branch", "parcel_numbers", "parcel_number", "signature",
        }:
            # A future backend may add a safe programme-specific key to
            # MatchingProfile before this worker receives a new fields.json.
            session.facts[field_name] = value
        return None

    # 縣市層級的答案（台南、臺南市）比補助條件的鄉鎮層級粗，
    # 不能當成「不符合」，否則只是講得籠統的人會被直接排除。
    # 用明確清單而不是靠「市」結尾判斷——員林市、頭份市是縣轄市，屬鄉鎮層級。
    _COUNTIES = (
        "台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市",
        "基隆市", "新竹市", "嘉義市",
        "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義縣",
        "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣",
    )

    def _known_townships(self) -> set[str]:
        """從所有補助的條件樹收集出現過的鄉鎮名，作為比對字典。"""
        found: set[str] = set()

        def walk(node):
            if not isinstance(node, dict):
                return
            for group in ("all", "any"):
                for child in node.get(group, []) or []:
                    walk(child)
            if node.get("field") == "township":
                value = node.get("value")
                found.update(value if isinstance(value, list) else [value])

        for program in self.legacy_programs:
            walk(program.get("eligibility") or {})
        return {v for v in found if isinstance(v, str)}

    def _township_in_text(self, text: str) -> str | None:
        """從一整句話裡找出公告涵蓋的鄉鎮。

        「我在台南玉井的芒果被颱風吹壞了」→ 玉井區。
        比對去掉後綴的字根，所以寫「玉井」或「玉井區」都認得。
        """
        t = (text or "").replace("臺", "台")
        best = None
        for town in self._known_townships():
            stem = town.replace("臺", "台").rstrip("區鄉鎮市")
            if stem and stem in t:
                # 取最長的字根，避免短名誤中（例如「南化」不該被「南」勾到）
                if best is None or len(stem) > len(best[0]):
                    best = (stem, town)
        return best[1] if best else None

    def _match_township(self, text: str) -> tuple[str | None, bool]:
        """回傳 (對應到的鄉鎮, 是否為縣市層級)。

        「玉井」→「玉井區」；「台南」→ (None, True) 代表還要再問是哪一區。
        台／臺互通。
        """
        t = (text or "").strip().replace("臺", "台")
        if not t:
            return None, False
        known = self._known_townships()
        norm = {v.replace("臺", "台"): v for v in known}
        if t in norm:
            return norm[t], False
        # 少寫了「區／鄉／鎮」也要認得
        for plain, canonical in norm.items():
            if plain.rstrip("區鄉鎮市") == t.rstrip("區鄉鎮市"):
                return canonical, False
        # 只講到縣市層級：不是不符合，是還不夠細，要再問是哪一區
        bare = t.rstrip("縣市")
        if any(t == c or bare == c.rstrip("縣市") for c in self._COUNTIES):
            return None, True
        return None, False

    def _match_crop(self, text: str) -> str | None:
        """把使用者打的作物名對回資料庫：正式名、台語別名、部分包含都認得。"""
        spec = self.fields.get("crop", {})
        t = text.strip()
        values = spec.get("values", [])
        aliases = spec.get("aliases", {})
        if t in values:
            return t
        if t in aliases:
            return aliases[t]
        for v in values:
            if v in t or t in v:
                return v
        for alias, v in aliases.items():
            if alias in t or t in alias:
                return v
        return None

    def _advance(self, session: Session) -> Reply:
        if session.profile_mode is None:
            session.profile_mode = "new" if self._uses_new_profile(session) else "legacy"
        if session.profile_mode == "new":
            return self._advance_matching(session)
        return self._advance_legacy(session)

    def _uses_new_profile(self, session: Session) -> bool:
        """Detect the new profile contract while keeping old event smoke intact."""
        return any(key in session.facts for key in MATCHING_PROFILE_KEYS) \
            or "crops" in session.facts \
            or "location" in session.facts \
            or "intent" in session.facts

    def _question_options(self, key: str, response: dict | None = None) -> list[str] | None:
        """Find demo choices in programme metadata, with stable hero defaults."""
        for result in (response or {}).get("results", []):
            metadata = result.get("metadata") or {}
            options = metadata.get("question_options")
            if isinstance(options, dict) and isinstance(options.get(key), list):
                return [str(item) for item in options[key]]
        return list(_MATCHING_OPTIONS[key]) if key in _MATCHING_OPTIONS else None

    def _advance_matching(self, session: Session) -> Reply:
        """Bridge the canonical matcher into the shared chat Reply shape."""
        response = matching_engine.match_profile(
            self.demo_programs,
            session.profile,
            asked=sorted(session.asked),
            today=self.today,
        )
        question = response.get("next_question")
        has_recommendation = any(
            str(result.get("status")) == "MATCH"
            for result in response.get("results", [])
        )
        if question and not has_recommendation \
                and session.questions_asked < NEW_MAX_QUESTIONS:
            key = str(question.get("key") or "")
            if key and key not in session.asked:
                session.pending_field = key
                session.pending_question = dict(question)
                session.questions_asked += 1
                return Reply(
                    str(question.get("question") or f"請提供你的「{key}」資訊。"),
                    self._question_options(key, response),
                )

        payload = self._matching_results_payload(response, session)
        return Reply(
            self._render_matching_results(response, payload),
            [STUCK_BUTTON],
            payload=payload,
        )

    def _matching_results_payload(self, response: dict, session: Session) -> dict:
        """Convert canonical MatchResponse into the UI's three-tier cards."""
        today = response.get("today") or self.today or date.today()
        if isinstance(today, str):
            try:
                today = date.fromisoformat(today[:10])
            except ValueError:
                today = date.today()

        def days_left(result: dict) -> int | None:
            deadline = result.get("deadline")
            if not deadline:
                window = result.get("window") or {}
                deadline = window.get("close") or window.get("end")
            if not deadline:
                return None
            try:
                remaining = (date.fromisoformat(str(deadline)[:10]) - today).days
            except (ValueError, TypeError):
                return None
            return remaining if remaining >= 0 else None

        def display_value(value: Any) -> str:
            if isinstance(value, list):
                return "、".join(str(item) for item in value)
            if value is True:
                return "有"
            if value is False:
                return "沒有"
            return str(value)

        def card(result: dict) -> dict:
            window = result.get("window") or {}
            authority = result.get("authority") or {}
            source = result.get("source") or {}
            form = result.get("form_template")
            if not isinstance(form, dict):
                form = None
            metadata = result.get("metadata") or {}
            missing_info = [
                {"key": str(item.get("key")),
                 "question": str(item.get("question") or "")}
                for item in result.get("missing_info") or []
                if isinstance(item, dict) and item.get("key")
            ]
            documents = []
            for item in result.get("documents") or []:
                if isinstance(item, dict) and item.get("name"):
                    documents.append({
                        "name": str(item["name"]),
                        "where": str(item.get("where") or ""),
                        "exempt": bool(item.get("exempt")),
                    })
            tasks = [
                _plain(item) for item in (result.get("tasks") or [])
                if isinstance(_plain(item), dict)
            ]
            return {
                "program_id": result.get("program_id"),
                "variant_id": result.get("variant_id"),
                "round_id": result.get("round_id"),
                "form_template_id": (form or {}).get("id"),
                "form_template": form,
                "name": result.get("name"),
                "summary": result.get("summary") or "",
                "category": result.get("category"),
                "status": result.get("status"),
                "reason": list(result.get("reason") or []),
                "why": "；".join(str(item) for item in result.get("reason") or []),
                "missing_info": missing_info,
                "missing": [
                    _MATCHING_LABELS.get(item["key"], item["key"])
                    for item in missing_info
                ],
                "deadline": result.get("deadline"),
                "close": window.get("close") or window.get("end") or result.get("deadline"),
                "window_note": window.get("note"),
                "window_type": window.get("type"),
                "days_left": days_left(result),
                "amount": display_value(result.get("amount")) if result.get("amount") else "",
                "documents": documents,
                "tasks": tasks,
                "agency": authority.get("agency", ""),
                "office": authority.get("office", ""),
                "tel": authority.get("tel", ""),
                "source": source,
                "official_form": metadata.get("official_form"),
                "last_verified": source.get("last_verified", ""),
            }

        profile = response.get("profile") or {}
        you_said = [
            {"label": _MATCHING_LABELS.get(key, key), "value": display_value(value)}
            for key, value in profile.items()
            if not str(key).startswith("__") and value not in (None, "", [])
        ]
        tiers: dict[str, list[dict]] = {"priority": [], "maybe": [], "skip": []}
        relevant_count = 0
        for result in response.get("results", []):
            status = str(result.get("status") or "REVIEW")
            if status == "MATCH":
                tiers["priority"].append(card(result))
                relevant_count += 1
            elif status in {"NEED_INFO", "REVIEW"}:
                tiers["maybe"].append(card(result))
                relevant_count += 1
            else:
                reason = (result.get("reason") or ["目前資料與這筆補助的條件不相符。"])[0]
                tiers["skip"].append({
                    "name": result.get("name"),
                    "status": status,
                    "why": str(reason),
                })

        for key in ("priority", "maybe"):
            tiers[key].sort(key=lambda item: (
                item["days_left"] if item["days_left"] is not None else 9999,
                str(item.get("name") or ""),
            ))
        # Keep the first screen demo-sized while retaining every skip reason.
        remaining = 5
        priority = tiers["priority"][:remaining]
        remaining -= len(priority)
        maybe = tiers["maybe"][:max(0, remaining)]
        return {
            "kind": "results",
            "matching_profile": profile,
            "you_said": you_said,
            "tiers": {"priority": priority, "maybe": maybe, "skip": tiers["skip"]},
            "relevant_count": relevant_count,
            "disclaimer": response.get("disclaimer") or "實際資格由承辦單位認定。",
        }

    def _render_matching_results(self, response: dict, payload: dict) -> str:
        lines: list[str] = []
        cards = [*payload["tiers"]["priority"], *payload["tiers"]["maybe"]]
        labels = {
            "MATCH": ("✅", "建議優先看"),
            "NEED_INFO": ("⚠️", "可能有關"),
            "REVIEW": ("🟡", "建議帶資料問承辦"),
            "CLOSED": ("⏳", "這一輪已截止"),
        }
        for item in cards[:3]:
            icon, label = labels.get(str(item.get("status")), ("🟡", "可能有關"))
            lines.append(f"{icon} {label}｜{item.get('name', '')}")
            if item.get("close"):
                lines.append(f"　⏰ 受理至 {item['close']}")
            if item.get("missing"):
                lines.append(f"　還差沒確認：{'、'.join(item['missing'])}")
            elif item.get("tasks"):
                lines.append(f"　下一步：{item['tasks'][0].get('title', '整理申請資料')}")
        if not lines:
            lines.append("目前比對不到相關的補助。你可以按「我卡住了」，我幫你找可以問的單位。")
        lines.append("\n※ 實際資格由承辦單位認定，這裡只是幫你先整理。")
        return "\n".join(lines)

    def _advance_legacy(self, session: Session) -> Reply:
        results = match_all(self.legacy_programs, session.facts)
        if session.questions_asked < MAX_QUESTIONS:
            q = next_question(results, self.fields,
                              asked=session.asked | set(session.facts),
                              today=self.today)
            if q is not None:
                session.pending_field = q["field"]
                session.questions_asked += 1
                if q["field"] == "crop":
                    # 作物用打的（配對資料庫，含台語別名），不用固定選項——
                    # 選項列不完所有作物，反而讓人以為「沒列的就不能問」。
                    return Reply(q["question"] + "\n（直接打作物名稱就可以，台語名嘛通）")
                return Reply(q["question"], q.get("options"))
        return Reply(self._render_results(results), [STUCK_BUTTON],
                     payload=self._results_payload(results, session))

    # ---- 呈現 ------------------------------------------------------------

    def _render_results(self, results: list[dict], limit: int = 3) -> str:
        """文字版結果（LINE 用）。措辭鐵則：不出現「符合／不符合／資格」等判定字眼。"""
        icons = {"符合": "✅", "可能符合": "⚠️"}
        wording = {"符合": "建議優先看", "可能符合": "可能有關"}
        lines: list[str] = []
        shown = 0
        for r in results:
            if r["status"] == "不符合" or shown >= limit:
                continue
            shown += 1
            lines.append(f"{icons[r['status']]} {wording[r['status']]}｜{r['name']}")
            w = r.get("window") or {}
            if w.get("close"):
                lines.append(f"　⏰ 受理至 {w['close']}")
            if r["status"] == "符合":
                for d in r["documents"]:
                    tag = "免附（豁免條款）" if d["exempt"] else (d.get("where") or "")
                    lines.append(f"　📄 {d['name']}｜{tag}")
                a = r.get("authority") or {}
                if a.get("tel"):
                    lines.append(f"　📞 {a.get('agency', '')} {a['tel']}")
            elif r["unknown_fields"]:
                labels = [self.fields.get(f, {}).get("label", f) for f in r["unknown_fields"]]
                lines.append(f"　還差沒確認：{'、'.join(labels)}（帶著文件直接去問承辦，會幫你確認）")
        if not lines:
            lines.append("目前比對不到相關的補助。你可以按「我卡住了」，我幫你找可以問的單位。")
        lines.append("\n※ 實際資格由承辦單位認定，這裡只是幫你先整理。")
        return "\n".join(lines)

    def _results_payload(self, results: list[dict], session: Session) -> dict:
        """結構化結果：網頁端畫三層卡片用（建議優先看／可能有關／這次先不用看）。"""
        today = self.today or date.today()

        def days_left(r: dict) -> int | None:
            w = r.get("window") or {}
            if w.get("type") == "公告型" and w.get("close"):
                try:
                    d = (date.fromisoformat(w["close"]) - today).days
                    return max(d, 0) if d >= 0 else None  # 過期不倒數
                except (ValueError, TypeError):
                    return None
            return None

        def amount_text(r: dict) -> str:
            a = r.get("amount") or {}
            if a.get("value"):
                v = a["value"]
                v_str = f"{v / 10000:g} 萬元" if v >= 10000 else f"{v:g} 元"
                return f"{a.get('unit', '')} {v_str}".strip()
            return "・".join(x for x in (a.get("unit"), a.get("note")) if x)

        def card(r: dict) -> dict:
            w = r.get("window") or {}
            return {
                "name": r["name"],
                "category": r.get("category"),
                "days_left": days_left(r),
                "close": w.get("close"),
                "window_note": w.get("note"),
                "window_type": w.get("type"),
                "amount": amount_text(r),
                "documents": [{"name": d["name"],
                               "where": d.get("where") or "",
                               "exempt": d["exempt"]} for d in r["documents"]],
                "agency": (r.get("authority") or {}).get("agency", ""),
                "office": (r.get("authority") or {}).get("office", ""),
                "tel": (r.get("authority") or {}).get("tel", ""),
                "missing": [self.fields.get(f, {}).get("label", f)
                            for f in r.get("unknown_fields", [])],
                "last_verified": (r.get("source") or {}).get("last_verified", ""),
            }

        def skip_reason(r: dict) -> str:
            for f in r.get("failed", []):
                if f.get("note"):
                    return f["note"]
                if f.get("field") == "crop":
                    said = session.facts.get("crop", "")
                    return f"這次公告的品項沒有包含你說的「{said}」" if said \
                        else "這次公告限定特定品項"
                label = self.fields.get(f.get("field", ""), {}).get("label", f.get("field", ""))
                return f"你說的「{label}」和這筆的條件不同"
            return "條件對不上"

        # 「你剛剛說的狀況」chips：enum 直接顯示、選項題反查回原本按的字
        you_said = []
        for name, value in session.facts.items():
            spec = self.fields.get(name)
            if spec is None:
                continue
            shown = value
            option_map = spec.get("option_map", {})
            for opt_text, mapped in option_map.items():
                if mapped == value:
                    shown = opt_text
                    break
            if isinstance(shown, bool):
                shown = "有" if shown else "沒有"
            you_said.append({"label": spec.get("label", name), "value": str(shown)})

        tiers = {"priority": [], "maybe": [], "skip": []}
        for r in results:
            if r["status"] == "符合":
                tiers["priority"].append(card(r))
            elif r["status"] == "可能符合":
                tiers["maybe"].append(card(r))
            else:
                tiers["skip"].append({"name": r["name"], "why": skip_reason(r)})
        # 有期限的排前面
        for key in ("priority", "maybe"):
            tiers[key].sort(key=lambda c: c["days_left"] if c["days_left"] is not None else 9999)

        return {
            "kind": "results",
            "you_said": you_said,
            "tiers": tiers,
            "disclaimer": "實際資格由承辦單位認定，這裡只是幫你先整理。",
        }

    def _render_card(self, card: dict) -> str:
        lines = [f"📋 {card['conclusion']}"]
        dl = card["deadline"]
        if dl.get("calc"):
            lines.append(f"⏰ {dl['calc']}")
        elif dl.get("text"):
            lines.append(f"⏰ {dl['text']}")
        elif dl.get("advice"):
            lines.append(f"⏰ {dl['advice']}")
        for t in card["todo"]:
            where = f"（{t['where']}）" if t.get("where") else ""
            lines.append(f"☐ {t['item']}{where}")
        if card.get("consequence"):
            lines.append(f"⚠️ {card['consequence']}")
        lines.append(f"\n{card['disclaimer']}")
        return "\n".join(lines)
