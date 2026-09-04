"""公文白話化模組：受控欄位抽取 → 白話待辦卡。

《系統設計建議書》§2.4：
- 受控輸出：固定欄位，不自由生成，關鍵欄位（期限）低信心就顯示原文＋導向承辦電話。
- 期限兩型分流：公文載明確日期（含民國紀年）→ 直接倒數；
  「文到○日內」→ 必須反問收文日，回傳白話計算式。
- 第一安全原則：解析不出就說不知道，絕不猜。

影像入口：read_image() 用 Claude vision 把公文照片逐字轉成文字，
再走同一條 translate() → build_plain_card() 流程。影像不落地，
處理完即丟。沒有 API 金鑰時明講「認不出來」，不猜。
RegexDocumentTranslator 為離線後備與 LLM 故障降級路徑。
"""
from __future__ import annotations

import base64
import json
import os
import re
from datetime import date
from typing import Any, Protocol

from .deadline import countdown, deadline_from_received, parse_rule

# 受控輸出欄位（不在此清單的鍵一律丟棄）
DOC_KEYS = ("doc_type", "issuer", "conclusion", "todo",
            "deadline_rule", "deadline_date", "consequence")

_ROC_DATE = re.compile(r"(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_TODO_HINTS = ("檢具", "檢附", "補正", "補附", "補繳", "提供", "到府說明", "補件")
_CONSEQ_HINTS = ("逾期", "駁回", "失權", "不予", "註銷", "追回")


def roc_to_date(text: str) -> date | None:
    """民國紀年 → 西元。『115年8月20日』→ 2026-08-20。"""
    m = _ROC_DATE.search(text or "")
    if not m:
        return None
    year = int(m.group(1))
    year = year + 1911 if year < 1000 else year
    try:
        return date(year, int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def sanitize_doc(raw: dict[str, Any]) -> dict[str, Any]:
    """受控輸出防火牆：只留固定欄位，todo 強制為 [{item, where}]。"""
    doc: dict[str, Any] = {k: raw.get(k) for k in DOC_KEYS}
    todo = []
    for t in (doc.get("todo") or []):
        if isinstance(t, str):
            todo.append({"item": t, "where": None})
        elif isinstance(t, dict) and t.get("item"):
            todo.append({"item": t["item"], "where": t.get("where")})
    doc["todo"] = todo
    return doc


class DocumentTranslator(Protocol):
    def translate(self, text: str) -> dict[str, Any]: ...


class RegexDocumentTranslator:
    """離線後備：規則式抽取。正確率有限，但每個欄位抓不到就是 None——不猜。"""

    def translate(self, text: str) -> dict[str, Any]:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        raw: dict[str, Any] = {}

        issuer = next((ln for ln in lines
                       if re.search(r"(縣|市)政府|公所|農糧署|農業部|漁業署", ln)), None)
        raw["issuer"] = re.sub(r"^(發文機關[:：]?)", "", issuer).strip() if issuer else None

        subject = next((ln for ln in lines if ln.startswith(("主旨", "主旨："))), None)
        raw["conclusion"] = re.sub(r"^主旨[:：]?", "", subject).strip() if subject else None

        raw["todo"] = [{"item": ln, "where": None} for ln in lines
                       if any(h in ln for h in _TODO_HINTS) and not ln.startswith("主旨")][:5]
        raw["doc_type"] = "補正通知" if raw["todo"] else "一般公文"

        deadline_line = next((ln for ln in lines if parse_rule(ln)), None)
        raw["deadline_rule"] = deadline_line
        explicit = next((roc_to_date(ln) for ln in lines
                         if "前" in ln and roc_to_date(ln)), None)
        raw["deadline_date"] = explicit.isoformat() if explicit else None

        conseq = next((ln for ln in lines if any(h in ln for h in _CONSEQ_HINTS)), None)
        raw["consequence"] = conseq
        return sanitize_doc(raw)


class ClaudeDocumentTranslator:
    """Claude 受控欄位抽取（正式路徑）。輸出仍必經 sanitize_doc。"""

    SYSTEM = (
        "你是台灣公文解讀器。從公文全文抽取固定欄位，只輸出一個 JSON 物件：\n"
        '{"doc_type": "補正通知/核定通知/駁回通知/一般公文",\n'
        ' "issuer": 發文機關, "conclusion": 用一句白話說結論（國中程度用語）,\n'
        ' "todo": [{"item": 要補的東西（白話）, "where": 去哪拿}],\n'
        ' "deadline_rule": 期限的原文句子（一字不改，找不到給 null）,\n'
        ' "deadline_date": 公文若載明確日期，轉為西元 YYYY-MM-DD（民國年+1911），否則 null,\n'
        ' "consequence": 沒做會怎樣（白話）}\n'
        "規則：deadline_rule 必須逐字引用原文，禁止改寫；不確定的欄位給 null，不要猜。"
    )

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
        import anthropic
        self.client = anthropic.Anthropic()
        self.fallback = RegexDocumentTranslator()

    def translate(self, text: str) -> dict[str, Any]:
        try:
            msg = self.client.messages.create(
                model=self.model, max_tokens=800, system=self.SYSTEM,
                messages=[{"role": "user", "content": text}],
            )
            match = re.search(r"\{.*\}", msg.content[0].text, re.S)
            raw = json.loads(match.group(0)) if match else {}
        except Exception:
            return self.fallback.translate(text)
        return sanitize_doc(raw)


class ImageReadError(RuntimeError):
    """公文影像轉不出文字：沒接上模型、圖太糊、或根本不是公文。"""


# 逐字抄寫，不翻譯不摘要——翻譯是下一段 translate() 的事，兩段分開才好除錯
OCR_SYSTEM = (
    "這是一張台灣公文的照片。把公文上的文字逐字打出來，保持原本的行序與段落。\n"
    "規則：不要翻譯、不要摘要、不要補上原文沒有的字；看不清楚的字用「□」代替。\n"
    "如果這張圖不是公文（風景、農田、人像、收據等），只回覆 NOT_A_DOCUMENT。"
)
IMAGE_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # Claude vision 單張上限


def read_image(data: bytes, media_type: str = "image/jpeg",
               model: str | None = None) -> str:
    """公文照片 → 公文文字。認不出來就 raise，絕不回傳猜測內容。"""
    if media_type not in IMAGE_MEDIA_TYPES:
        raise ImageReadError("照片格式不支援，請用 JPG 或 PNG 重拍一張。")
    if not data:
        raise ImageReadError("沒有收到照片內容，請重新上傳。")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageReadError("照片太大了（超過 5MB），請用手機相機一般畫質重拍。")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ImageReadError("目前系統沒有接上辨識模型，請改用「貼上文字」把公文內容打進來。")

    import anthropic
    client = anthropic.Anthropic()
    try:
        msg = client.messages.create(
            model=model or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8"),
            max_tokens=4000,
            system=OCR_SYSTEM,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": media_type,
                                             "data": base64.standard_b64encode(data).decode()}},
                {"type": "text", "text": "請把這張公文的文字逐字打出來。"},
            ]}],
        )
    except Exception as exc:  # 網路／額度／模型故障
        raise ImageReadError("辨識服務暫時不通，請稍後再試，或改用「貼上文字」。") from exc

    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if "NOT_A_DOCUMENT" in text:
        raise ImageReadError("這張看起來不是公文。請拍公文那張紙，整張入鏡、字不要糊。")
    if len(text) < 15:
        raise ImageReadError("照片上的字看不清楚。請在光線亮的地方、整張入鏡再拍一次。")
    return text


def get_translator() -> DocumentTranslator:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return ClaudeDocumentTranslator()
        except Exception:
            pass
    return RegexDocumentTranslator()


def build_plain_card(doc: dict[str, Any], received_date: date | None = None,
                     today: date | None = None,
                     holidays: set[date] | None = None) -> dict[str, Any]:
    """白話卡：結論／幾號前／缺什麼／不做會怎樣／下一步。

    期限兩型分流在這裡發生：
    - deadline_date 明確 → 倒數
    - deadline_rule 可解析（文到型）→ 沒收文日就反問，有就給計算式
    - 都沒有 → 導向承辦電話，絕不猜
    """
    card: dict[str, Any] = {
        "conclusion": doc.get("conclusion") or "（無法確認公文結論，請見下方原文對照）",
        "doc_type": doc.get("doc_type"),
        "issuer": doc.get("issuer"),
        "todo": doc.get("todo") or [],
        "consequence": doc.get("consequence"),
        "actions": ["我知道了", "我卡住了"],
        "disclaimer": "本翻譯僅供理解，實際內容以公文原文為準；有疑問請電洽發文機關。",
    }
    explicit = doc.get("deadline_date")
    rule = doc.get("deadline_rule")
    if explicit:
        card["deadline"] = {"type": "公告型", **countdown(date.fromisoformat(explicit), today)}
    elif rule and parse_rule(rule):
        if received_date is None:
            card["deadline"] = {"type": "文到型", "ask_received_date": True,
                                "question": "你哪一天收到這張公文？",
                                "rule_text": rule}
        else:
            result = deadline_from_received(received_date, rule, holidays)
            card["deadline"] = {"type": "文到型", "rule_text": rule, **result}
    else:
        card["deadline"] = {"type": "未知",
                            "advice": "公文裡找不到明確期限，請直接電洽發文機關確認，勿自行推算。"}
    return card
