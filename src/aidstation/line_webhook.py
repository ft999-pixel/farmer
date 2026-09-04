"""LINE 官方帳號 Webhook（農民主入口）。

- 簽章驗證：X-Line-Signature（HMAC-SHA256，channel secret）
- 對話邏輯全部在 flow.py，這裡只做 LINE 協定轉換
- 未設定 LINE_CHANNEL_ACCESS_TOKEN 時為 dry-run 模式：
  回覆內容直接放在 HTTP 回應中，方便本機測試與 pytest

環境變數：LINE_CHANNEL_SECRET、LINE_CHANNEL_ACCESS_TOKEN
Rich Menu 三大鍵（於 LINE 後台設定，送出文字）：
  「我要問補助」「我收到公文」「幫我檢查資格」
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import date

import httpx
from fastapi import APIRouter, HTTPException, Request

from .flow import Flow, Reply, Session

router = APIRouter()
_flow: Flow | None = None
_sessions: dict[str, Session] = {}  # MVP 記憶體版；上線改 Redis 並設 TTL

GREETING = ("你好！我是農民補給站 🌾\n"
            "遇到災損、想查補助，用一句話告訴我就好，講台語嘛會通。\n"
            "收到看不懂的公文，拍照傳給我，我翻成白話。")


def get_flow(today: date | None = None) -> Flow:
    global _flow
    if _flow is None:
        _flow = Flow(today=today)
    return _flow


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature or "")


def _to_line_message(reply: Reply) -> dict:
    msg: dict = {"type": "text", "text": reply.text}
    if reply.options:
        msg["quickReply"] = {"items": [
            {"type": "action", "action": {"type": "message", "label": o[:20], "text": o}}
            for o in reply.options[:13]  # LINE quick reply 上限 13
        ]}
    return msg


async def _reply_to_line(reply_token: str, messages: list[dict], token: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={"Authorization": f"Bearer {token}"},
            json={"replyToken": reply_token, "messages": messages},
        )


@router.post("/line/webhook")
async def line_webhook(request: Request) -> dict:
    body = await request.body()
    secret = os.environ.get("LINE_CHANNEL_SECRET", "")
    if secret and not verify_signature(body, request.headers.get("X-Line-Signature", ""), secret):
        raise HTTPException(403, "signature 驗證失敗")

    payload = await request.json()
    flow = get_flow()
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    dry_run_replies: list[dict] = []

    for event in payload.get("events", []):
        user_id = (event.get("source") or {}).get("userId", "anonymous")
        session = _sessions.setdefault(user_id, Session())
        etype = event.get("type")
        reply: Reply | None = None

        if etype == "follow":
            reply = Reply(GREETING)
        elif etype == "message":
            message = event.get("message", {})
            if message.get("type") == "text":
                text = message.get("text", "")
                if text in ("我要問補助", "幫我檢查資格"):
                    _sessions[user_id] = session = Session()
                    reply = Reply("好，跟我說發生什麼事？講一句話就好（例：我的檨仔攏落了了）。")
                elif text == "我收到公文":
                    reply = Reply("請把公文拍清楚傳給我（整張入鏡、字不要糊）。")
                else:
                    reply = flow.handle_text(session, text)
            elif message.get("type") == "image":
                # TODO：以 channel token 下載影像 → OCR → flow.handle_document_text
                # 影像不落地原則：處理完即刪，不寫入磁碟
                reply = Reply("公文影像收到了。OCR 模組接上後，這裡會回傳白話翻譯。\n"
                              "（目前開發中，可先用文字貼上公文內容測試）")
            elif message.get("type") == "audio":
                # TODO：下載音檔 → 台語 ASR（Breeze-ASR）→ handle_text
                reply = Reply("語音收到了。台語辨識模組接上後，這裡會直接聽懂。\n"
                              "（目前開發中，可先用文字輸入）")

        if reply is None:
            continue
        messages = [_to_line_message(reply)]
        if token and event.get("replyToken"):
            await _reply_to_line(event["replyToken"], messages, token)
        else:
            dry_run_replies.append({"to": user_id, "messages": messages})

    return {"ok": True, "dry_run": not bool(token),
            **({"replies": dry_run_replies} if not token else {})}
