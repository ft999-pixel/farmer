"""FastAPI 服務：核心引擎對外介面。

啟動：uvicorn aidstation.api:app --reload（PYTHONPATH 需含 src）
之後 LINE bot 與協辦者 PWA 都打這一套 API。
"""
from __future__ import annotations

from datetime import date

try:  # 讀取專案根目錄的 .env（沒裝 python-dotenv 或沒有 .env 都不影響啟動）
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    load_dotenv(_Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import __version__, blockers
from .admin import router as admin_router
from .deadline import deadline_from_received, load_holidays
from .document import build_plain_card, get_translator
from .matching import MatchingInputError, match_profile
from .fields import load_fields
from .knowledge import load_programs
from .line_webhook import router as line_router
from .members import router as members_router
from .official_forms import router as official_forms_router
from .schemas import MatchRequest

app = FastAPI(title="農民補給站核心引擎", version=__version__)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(line_router)
app.include_router(admin_router)
app.include_router(members_router)
app.include_router(official_forms_router)

FIELDS = load_fields()
PROGRAMS = load_programs(fields=FIELDS)
HOLIDAYS = load_holidays()


class DeadlineRequest(BaseModel):
    rule: str
    received_date: str  # ISO 日期，「你哪一天收到的？」的答案


class TranslateRequest(BaseModel):
    text: str                    # 公文全文（OCR 後或直接貼上）
    received_date: str | None = None
    today: str | None = None
    category: str | None = None  # 補助類別，供卡點統計交叉分析（可不給）
    township: str | None = None


class BlockerRequest(BaseModel):
    reason: str                  # 三選項之一，或公文上的文字（會自動歸類）
    source: str = blockers.SOURCE_STUCK
    category: str | None = None
    township: str | None = None
    level: str | None = None     # 中央／縣市；不給則由發文機關推斷
    issuer: str | None = None    # 發文機關名稱，用來推斷層級


@app.get("/", include_in_schema=False)
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/app/")


# /app 整個網站（index.html／browse.html／chat.html＋fonts、img）交給 StaticFiles
@app.get("/app", include_in_schema=False)
def app_no_slash():
    """舊版 Starlette 不會自動把 /app 轉到 /app/，這裡明確轉址。"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/app/")


from fastapi.staticfiles import StaticFiles  # noqa: E402
from pathlib import Path as _WebPath  # noqa: E402
app.mount("/app", StaticFiles(directory=_WebPath(__file__).resolve().parents[2] / "web",
                              html=True), name="web")


# ---- 網頁版聊天：重用 LINE 同一套 Flow 引擎，不寫第二份邏輯 ----
from .flow import Flow, Session as FlowSession  # noqa: E402

_web_flow: Flow | None = None
_web_sessions: dict[str, FlowSession] = {}


class ChatRequest(BaseModel):
    session_id: str
    text: str = ""
    kind: str = "text"       # "text"＝對話｜"document"＝貼公文全文｜"reset"＝重新開始
    today: date | None = None  # demo 可固定日期；不影響正式呼叫的預設行為


@app.post("/chat")
def post_chat(req: ChatRequest) -> dict:
    global _web_flow
    if _web_flow is None or (req.today is not None and _web_flow.today != req.today):
        _web_flow = Flow(today=req.today)
    if req.kind == "reset":
        _web_sessions[req.session_id] = FlowSession()
        return {"text": "好，重新開始。跟我說發生什麼事？講一句話就好（例：我的檨仔攏落了了）。",
                "options": None}
    session = _web_sessions.setdefault(req.session_id, FlowSession())
    if req.kind == "document":
        reply = _web_flow.handle_document_text(session, req.text)
    else:
        reply = _web_flow.handle_text(session, req.text)
    return {"text": reply.text, "options": reply.options, "payload": reply.payload}


@app.get("/fields")
def get_fields() -> dict:
    return FIELDS


@app.get("/programs")
def get_programs() -> list[dict]:
    rows = []
    for p in PROGRAMS:
        window = p.get("window")
        if window is None:
            # New hierarchy data keeps windows on rounds. The browse endpoint
            # remains a compact summary and uses the first round as its legacy
            # representative rather than exposing a second API shape.
            for variant in getattr(p, "variants", []) or []:
                rounds = getattr(variant, "rounds", []) or []
                if rounds:
                    window = rounds[0].window
                    break
        if hasattr(window, "model_dump"):
            window = window.model_dump(mode="json", exclude_none=True)
        rows.append({"id": p["id"], "name": p["name"], "category": p.get("category"),
                     "window": window, "source": p.get("source")})
    return rows


@app.post("/match")
def post_match(req: MatchRequest) -> dict:
    try:
        return match_profile(
            PROGRAMS,
            req.profile,
            asked=req.asked,
            today=req.today,
        )
    except MatchingInputError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/translate")
def post_translate(req: TranslateRequest) -> dict:
    """公文白話化：受控欄位抽取 → 白話卡。文到型且未給收文日時會要求反問。"""
    doc = get_translator().translate(req.text)
    received = date.fromisoformat(req.received_date) if req.received_date else None
    today = date.fromisoformat(req.today) if req.today else None
    card = build_plain_card(doc, received_date=received, today=today, holidays=HOLIDAYS)
    blockers.record_from_doc(doc, category=req.category, township=req.township)
    return {"doc": doc, "card": card}


@app.post("/blockers")
def post_blocker(req: BlockerRequest) -> dict:
    """農民按「我卡住了」或回報公文卡點。寫入即去識別化，不帶身分欄位。"""
    reason = req.reason if req.reason in blockers.LABELS else blockers.classify(req.reason)
    level = req.level or blockers.classify_level(req.issuer or "")
    return blockers.record(reason, req.source, category=req.category,
                           township=req.township, level=level)


@app.get("/blockers/stats")
def get_blocker_stats(weeks: int = 8) -> dict:
    """儀表板資料：原因排行、每週趨勢、補助類別×原因交叉。"""
    return blockers.stats(weeks=max(1, min(weeks, 52)))


@app.post("/deadline")
def post_deadline(req: DeadlineRequest) -> dict:
    try:
        received = date.fromisoformat(req.received_date)
    except ValueError:
        raise HTTPException(422, "received_date 需為 ISO 日期（YYYY-MM-DD）")
    result = deadline_from_received(received, req.rule, HOLIDAYS)
    if result is None:
        return {"parsed": False,
                "advice": "無法解析期限規則，請向承辦單位確認，勿自行推算。"}
    return {"parsed": True, **result}
