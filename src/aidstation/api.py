"""FastAPI 服務：核心引擎對外介面。

啟動：uvicorn aidstation.api:app --reload（PYTHONPATH 需含 src）
之後 LINE bot 與協辦者 PWA 都打這一套 API。
"""
from __future__ import annotations

import base64
import binascii
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

from . import __version__, blockers, guides
from .admin import router as admin_router
from .deadline import deadline_from_received, load_holidays
from .document import ImageReadError, build_plain_card, get_translator, read_image
from .matching import MatchingInputError, match_profile
from .fields import load_fields
from .knowledge import load_programs
from .line_login import router as line_login_router
from .line_webhook import router as line_router
from .members import router as members_router
from .official_forms import router as official_forms_router
from .schemas import MatchRequest

app = FastAPI(title="農民補給站核心引擎", version=__version__)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(line_router)
app.include_router(admin_router)
app.include_router(members_router)
app.include_router(line_login_router)
app.include_router(official_forms_router)

FIELDS = load_fields()
PROGRAMS = load_programs(fields=FIELDS)
HOLIDAYS = load_holidays()


class DeadlineRequest(BaseModel):
    rule: str
    received_date: str  # ISO 日期，「你哪一天收到的？」的答案


class TranslateRequest(BaseModel):
    text: str = ""               # 公文全文（貼上）；給 image 時可留空
    image: str | None = None     # 公文照片，base64（可含 data:image/jpeg;base64, 前綴）
    received_date: str | None = None
    today: str | None = None
    category: str | None = None  # 補助類別，供卡點統計交叉分析（可不給）
    township: str | None = None


def decode_image(raw: str) -> tuple[bytes, str]:
    """把前端傳來的 data URL／裸 base64 拆成 (bytes, media_type)。影像不落地。"""
    media_type = "image/jpeg"
    if raw.startswith("data:"):
        header, _, raw = raw.partition(",")
        media_type = header[5:].split(";")[0] or media_type
    try:
        return base64.b64decode(raw, validate=True), media_type
    except (ValueError, binascii.Error):
        raise ImageReadError("照片資料讀不出來，請重新上傳一次。")


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
    image: str | None = None   # kind="document_image" 時的公文照片 base64
    kind: str = "text"         # "text"｜"document"＝貼全文｜"document_image"＝拍照｜"reset"
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
    if req.kind == "document_image":
        try:
            data, media_type = decode_image(req.image or "")
            text = read_image(data, media_type)
        except ImageReadError as exc:
            # 認不出來就直說，並給農民下一步；不回傳半猜的翻譯
            return {"text": f"{exc}\n\n看不懂的地方也可以直接打電話問承辦，他們會幫你看。",
                    "options": ["我知道了", "我卡住了"], "payload": None}
        reply = _web_flow.handle_document_text(session, text)
    elif req.kind == "document":
        reply = _web_flow.handle_document_text(session, req.text)
    else:
        reply = _web_flow.handle_text(session, req.text)
    return {"text": reply.text, "options": reply.options, "payload": reply.payload}


@app.get("/guides")
def list_guides() -> list[dict]:
    """公開的指南清單（不含內文，首頁列表用）。"""
    return [{k: g.get(k) for k in ("id", "title", "category", "read_minutes", "updated_at")}
            for g in guides.load_guides()]


@app.get("/guides/{guide_id}")
def read_guide(guide_id: str) -> dict:
    """單篇指南。內文在伺服器端轉成安全 HTML，前端不做 Markdown 解析。"""
    guide = guides.get_guide(guide_id)
    if guide is None:
        raise HTTPException(404, "找不到這篇指南")
    return {**guide, "html": guides.render_markdown(guide.get("body", ""))}


@app.get("/fields")
def get_fields() -> dict:
    return FIELDS


@app.get("/programs")
def get_programs() -> list[dict]:
    """清單：window 相容新舊兩種資料結構，並附上「找補助」頁要顯示與篩選的欄位。"""
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
        rows.append({
            "id": p["id"], "name": p["name"], "category": p.get("category"),
            "window": window, "source": p.get("source"),
            # 以下供 browse.html 顯示與篩選，取代前端寫死的 site-data.js 副本
            "display": p.get("display") or {},
            "authority": {k: (p.get("authority") or {}).get(k)
                          for k in ("agency", "office", "tel")},
            "summary": (p.get("plain") or {}).get("summary"),
        })
    return rows


@app.get("/programs/{program_id}")
def get_program(program_id: str) -> dict:
    """單筆補助的完整內容，補助詳情頁（program.html）用。

    load_programs 現在回傳 Pydantic 的 LoadedProgram，不是純 dict，
    直接回傳會序列化失敗，所以在這裡轉成 JSON 可用的形式。
    """
    program = next((p for p in PROGRAMS if p["id"] == program_id), None)
    if program is None:
        raise HTTPException(404, "找不到這筆補助")
    if hasattr(program, "model_dump"):
        return program.model_dump(mode="json", exclude_none=True)
    return program


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
    """公文白話化：（照片 → 文字 →）受控欄位抽取 → 白話卡。

    給 image 就先 OCR；文到型且未給收文日時會要求反問收文日。
    影像只在記憶體停留，處理完即丟，不寫入磁碟。
    """
    text = req.text
    if req.image:
        try:
            data, media_type = decode_image(req.image)
            text = read_image(data, media_type)
        except ImageReadError as exc:
            raise HTTPException(422, str(exc))
    if not text.strip():
        raise HTTPException(422, "請提供公文文字（text）或公文照片（image）。")
    doc = get_translator().translate(text)
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
