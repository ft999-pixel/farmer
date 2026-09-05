"""LINE Login（農民端登入）。

為什麼用 LINE 而不是帳號密碼：
- 目標使用者是長輩，忘記密碼的機率極高，密碼重設流程對他們是另一道門檻
- 綁定後拿得到 LINE userId，將來有符合資格的補助可以直接推播（設計建議書 §11 的 L1 訂閱）

刻意獨立成一個檔案，不寫進 members.py：那個檔案協作頻繁，分開可避免衝突，
也讓「要不要啟用 LINE 登入」變成單純的掛載與否。

尚未設定憑證時整個功能停用（/members/line/status 會回 configured=false），
前端據此顯示說明並改走代號登入，不會出現一顆按了沒反應的按鈕。

⚠️ 需要的是「LINE Login」channel，與 Messaging API（聊天機器人）是不同的 channel，
   憑證也不同：LINE_LOGIN_CHANNEL_ID / LINE_LOGIN_CHANNEL_SECRET。
"""
from __future__ import annotations

import os
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from .members import COOKIE, SESSION_DAYS, _sign, get_member, save_member

router = APIRouter(prefix="/members/line", tags=["members"])

AUTHORIZE_URL = "https://access.line.me/oauth2/v2.1/authorize"
TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
PROFILE_URL = "https://api.line.me/v2/profile"
STATE_COOKIE = "aidstation_line_state"


def _channel_id() -> str | None:
    return os.environ.get("LINE_LOGIN_CHANNEL_ID") or None


def _channel_secret() -> str | None:
    return os.environ.get("LINE_LOGIN_CHANNEL_SECRET") or None


def is_configured() -> bool:
    return bool(_channel_id() and _channel_secret())


def _redirect_uri(request: Request) -> str:
    """回呼網址。可用 LINE_LOGIN_REDIRECT_URI 覆寫（部署後網域與本機不同）。"""
    override = os.environ.get("LINE_LOGIN_REDIRECT_URI")
    if override:
        return override
    return str(request.url_for("line_callback"))


def _member_code(line_user_id: str) -> str:
    """LINE userId 轉成會員代號。加前綴避免與農民自取的代號相撞。"""
    return f"line-{line_user_id}"


@router.get("/status")
def line_status() -> dict:
    """前端用來決定要顯示 LINE 按鈕還是設定說明。"""
    return {"configured": is_configured()}


@router.get("/login")
def line_login(request: Request):
    """導向 LINE 授權頁。state 存在 cookie 供回呼時比對，防 CSRF。"""
    if not is_configured():
        raise HTTPException(503, "尚未設定 LINE 登入，請先在 .env 填入 "
                                 "LINE_LOGIN_CHANNEL_ID 與 LINE_LOGIN_CHANNEL_SECRET。")
    state = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": _channel_id(),
        "redirect_uri": _redirect_uri(request),
        "state": state,
        "scope": "profile openid",
    }
    response = RedirectResponse(f"{AUTHORIZE_URL}?{urlencode(params)}")
    response.set_cookie(STATE_COOKIE, state, httponly=True, samesite="lax", max_age=600)
    return response


@router.get("/callback", name="line_callback")
def line_callback(request: Request, code: str = "", state: str = "",
                  aidstation_line_state: str | None = Cookie(None)):
    """LINE 導回這裡：驗 state → 換 token → 取 userId → 建立／找回會員 → 發 cookie。"""
    if not is_configured():
        raise HTTPException(503, "尚未設定 LINE 登入。")
    if not code:
        return RedirectResponse("/app/login.html?line=cancelled")
    if not state or state != aidstation_line_state:
        # state 對不上代表可能被第三方誘導登入，直接擋掉
        return RedirectResponse("/app/login.html?line=bad_state")

    try:
        with httpx.Client(timeout=15) as client:
            token = client.post(TOKEN_URL, data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(request),
                "client_id": _channel_id(),
                "client_secret": _channel_secret(),
            }).raise_for_status().json()
            profile = client.get(PROFILE_URL, headers={
                "Authorization": f"Bearer {token['access_token']}"
            }).raise_for_status().json()
    except (httpx.HTTPError, KeyError):
        return RedirectResponse("/app/login.html?line=failed")

    line_user_id = profile.get("userId")
    if not line_user_id:
        return RedirectResponse("/app/login.html?line=failed")

    member_code = _member_code(line_user_id)
    if get_member(member_code) is None:
        save_member(member_code, {})

    response = RedirectResponse("/app/profile.html?welcome=line")
    response.set_cookie(COOKIE, _sign(member_code, int(time.time()) + SESSION_DAYS * 86400),
                        httponly=True, samesite="lax", max_age=SESSION_DAYS * 86400)
    response.delete_cookie(STATE_COOKIE)
    return response
