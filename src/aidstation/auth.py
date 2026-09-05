"""帳號與統一登入：由帳號本身的角色決定去處，使用者不必自選入口。

登入方式兩種：
    帳號＋密碼  → 查帳號表，角色可能是農民或承辦人員
    LINE 登入   → 一律是農民（見 line_login.py）

角色寫在帳號上，不是讓人在畫面上勾選，也不是靠「有沒有填密碼」猜。

密碼用 stdlib 的 pbkdf2_hmac 雜湊，不存明碼，也不必為此加套件。
帳號表獨立於 members（會員的媒合資料），兩者以 username 對應：
帳號負責「你是誰、能做什麼」，members 負責「你填了什麼」。

刻意獨立成新檔，不改 members.py／admin.py 的既有端點——那兩個檔案協作頻繁。

⚠️ 承辦帳號目前由 .env 的 ADMIN_USERNAME／ADMIN_PASSWORD 帶入，
   首次啟動時建立。要多位承辦各自帳號，之後在此表新增即可，
   稽核就能追溯到人。
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel

from . import admin as admin_mod
from . import members as members_mod
from .fields import DATA_DIR

router = APIRouter(prefix="/auth", tags=["auth"])

DB_PATH = DATA_DIR / "accounts.db"
ROLE_MEMBER, ROLE_ADMIN = "member", "admin"
_USERNAME_OK = re.compile(r"^[\w一-鿿-]{2,32}$")
MIN_PASSWORD = 6
_PBKDF2_ROUNDS = 200_000


def _db_path() -> Path:
    return Path(os.environ.get("AIDSTATION_ACCOUNTS_DB") or DB_PATH)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'member',
            created_at    TEXT NOT NULL
        )""")
    return conn


# ---- 密碼雜湊 ------------------------------------------------------------

def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt),
                                 _PBKDF2_ROUNDS).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


# ---- 帳號存取 ------------------------------------------------------------

def get_account(username: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def create_account(username: str, password: str, role: str = ROLE_MEMBER) -> dict:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO accounts (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), role,
             datetime.now().isoformat(timespec="seconds")))
    return {"username": username, "role": role}


def ensure_admin_account() -> None:
    """把 .env 的承辦帳密帶進帳號表。密碼變更時一併更新，避免改了 .env 卻登不進去。"""
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        return
    username = os.environ.get("ADMIN_USERNAME", "admin")
    existing = get_account(username)
    if existing is None:
        create_account(username, password, ROLE_ADMIN)
    elif not verify_password(password, existing["password_hash"]):
        with _connect() as conn:
            conn.execute("UPDATE accounts SET password_hash = ?, role = ? WHERE username = ?",
                         (hash_password(password), ROLE_ADMIN, username))


# ---- 登入／註冊 ----------------------------------------------------------

class Credentials(BaseModel):
    username: str = ""
    password: str = ""


def _issue_session(username: str, role: str, response: Response) -> dict:
    """依角色發對應的 cookie。承辦人員同時給會員 cookie，方便他自己也查補助。"""
    if role == ROLE_ADMIN:
        response.set_cookie(
            admin_mod.COOKIE,
            admin_mod._sign(int(time.time()) + admin_mod.SESSION_HOURS * 3600),
            httponly=True, samesite="strict", max_age=admin_mod.SESSION_HOURS * 3600)
        return {"role": ROLE_ADMIN, "redirect": "admin.html", "username": username}

    if members_mod.get_member(username) is None:
        members_mod.save_member(username, {})
    response.set_cookie(
        members_mod.COOKIE,
        members_mod._sign(username, int(time.time()) + members_mod.SESSION_DAYS * 86400),
        httponly=True, samesite="lax", max_age=members_mod.SESSION_DAYS * 86400)
    return {"role": ROLE_MEMBER, "redirect": "profile.html", "username": username}


@router.post("/register")
def register(req: Credentials, response: Response) -> dict:
    """農民自行註冊。承辦帳號不從這裡開，避免有人自建管理權限。"""
    username = (req.username or "").strip()
    if not _USERNAME_OK.match(username):
        raise HTTPException(422, "帳號請用 2～32 個中英文字、數字或連字號，例如「阿明伯」。")
    if len(req.password or "") < MIN_PASSWORD:
        raise HTTPException(422, f"密碼至少要 {MIN_PASSWORD} 個字。")
    if get_account(username) is not None:
        raise HTTPException(409, "這個帳號已經有人用了，換一個或直接登入。")
    create_account(username, req.password, ROLE_MEMBER)
    return {"created": True, **_issue_session(username, ROLE_MEMBER, response)}


@router.post("/login")
def login(req: Credentials, response: Response) -> dict:
    ensure_admin_account()
    username = (req.username or "").strip()
    if not username or not req.password:
        raise HTTPException(422, "請輸入帳號和密碼。")

    account = get_account(username)
    # 帳號不存在與密碼錯誤回同一句話，避免被拿來探測哪些帳號存在
    if account is None or not verify_password(req.password, account["password_hash"]):
        raise HTTPException(401, "帳號或密碼不對。第一次使用請先註冊。")

    return _issue_session(username, account["role"], response)


@router.get("/me")
def whoami(aidstation_admin: str | None = Cookie(None),
           aidstation_member: str | None = Cookie(None)) -> dict:
    """前端用來決定顯示哪一套介面。"""
    if admin_mod._valid_token(aidstation_admin):
        return {"logged_in": True, "role": ROLE_ADMIN}
    code = members_mod._code_from_token(aidstation_member)
    if code:
        return {"logged_in": True, "role": ROLE_MEMBER, "username": code}
    return {"logged_in": False, "role": None}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(admin_mod.COOKIE)
    response.delete_cookie(members_mod.COOKIE)
    return {"ok": True}
