"""對話流程引擎（狀態機）：LINE 與 PWA 共用，不依賴任何通訊平台。

設計原則（《系統設計建議書》§4.1）：
- 一次一題、每題有按鈕選項、3~5 題內必出結果
- 「我卡住了」隨時可按 → 先一題三選項釐清卡點，再給對應協助
- 公文流程：文到型期限必問收文日
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from . import blockers
from .document import build_plain_card, get_translator
from .engine import match_all, next_question
from .extract import get_extractor
from .fields import load_fields, normalize_facts
from .knowledge import load_programs

MAX_QUESTIONS = 5
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


@dataclass
class Session:
    """單一使用者的對話狀態（LINE 以 userId 為鍵；記憶體版，MVP 用）。"""
    facts: dict[str, Any] = field(default_factory=dict)
    asked: set[str] = field(default_factory=set)
    pending_field: str | None = None      # 等待回答的欄位
    pending_stuck: bool = False           # 等待「卡住原因」三選一
    pending_doc: dict | None = None       # 等待收文日的公文
    questions_asked: int = 0
    last_context: str = "results"         # "results"＝查詢流程｜"document"＝公文流程


@dataclass
class Reply:
    text: str
    options: list[str] | None = None
    payload: dict | None = None   # 結構化資料：網頁端用來畫卡片（LINE 端可忽略）


class Flow:
    def __init__(self, today: date | None = None):
        self.fields = load_fields()
        self.programs = load_programs(fields=self.fields)
        self.extractor = get_extractor(self.fields)
        self.translator = get_translator()
        self.today = today  # 測試用；None 則用今天

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
        spec = self.fields[field_name]
        value = spec.get("option_map", {}).get(text, text)
        session.asked.add(field_name)
        session.pending_field = None
        if value == "不確定":
            return None  # 不確定就先跳過，之後仍以「可能符合」呈現該補助
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
        results = match_all(self.programs, session.facts)
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
